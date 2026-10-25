"""Scenario run execution on an in-process worker pool.

Runs are queued by the API and executed on a small thread pool inside the
backend process.  A Postgres advisory lock keeps one executor per run; runs
left ``running`` by a stopped process are marked failed at startup and can be
retried as a new attempt.
"""
import os
from datetime import datetime, timezone
from time import monotonic
from hashlib import sha256
from contextlib import contextmanager

from sqlalchemy import text
from concurrent.futures import ThreadPoolExecutor

from app.models.user import User

def _now():
    return datetime.now(timezone.utc)

def _duration_ms(started_at, completed_at):
    """Subtract timestamps consistently across PostgreSQL and SQLite round trips."""
    if not started_at or not completed_at:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    return max(0, int((completed_at - started_at).total_seconds() * 1000))

def _commit_stage(db, stage, status, *, summary=None, error=None):
    stage.status = status
    if summary is not None:
        stage.summary_json = summary
    if error is not None:
        stage.error_json = error
    if status == "running":
        stage.started_at = _now()
    if status in {"completed", "failed", "cancelled"}:
        stage.completed_at = _now()
        if stage.started_at:
            stage.duration_ms = _duration_ms(stage.started_at, stage.completed_at)

@contextmanager
def _execution_lock(db, run_id):
    """Session advisory lock survives stage commits and releases on worker death."""
    if db.get_bind().dialect.name != "postgresql":
        yield True
        return
    key = int.from_bytes(sha256(run_id.encode()).digest()[:8], "big", signed=True)
    with db.get_bind().connect() as connection:
        acquired = connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar()
        try:
            yield acquired
        finally:
            if acquired:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})


def reconcile_interrupted_runs():
    """Make abandoned attempts explicitly retryable; never touch a live executor."""
    from app.database import SessionLocal
    from app.models.v2.scenario import ScenarioRun, ScenarioRunStage
    with SessionLocal() as db:
        for run in db.query(ScenarioRun).filter_by(status="running").all():
            with _execution_lock(db, run.id) as acquired:
                if not acquired:
                    continue
                error = {"code": "worker_interrupted", "message": "The run stopped before completion; retry creates a new attempt."}
                for stage in db.query(ScenarioRunStage).filter_by(run_id=run.id, status="running").all():
                    _commit_stage(db, stage, "failed", error=error)
                run.status = "failed"
                run.error_json = error
                run.completed_at = _now()
                db.commit()


_POOL = ThreadPoolExecutor(max_workers=int(os.getenv("SCENARIO_RUN_WORKERS", "2")), thread_name_prefix="scenario-run")


def submit_run(run_id: str):
    """Queue a run on the in-process pool; the caller has already committed it."""
    return _POOL.submit(run_scenario, run_id)


def run_scenario(run_id: str):
    from app.database import SessionLocal
    with SessionLocal() as lock_session:
        with _execution_lock(lock_session, run_id) as acquired:
            if acquired:
                return _execute_run(run_id)


def _execute_run(run_id: str):
    from app.database import SessionLocal
    from app.models.v2.scenario import ScenarioRun

    db = SessionLocal()
    started = monotonic()
    try:
        run = db.get(ScenarioRun, run_id)
        if not run or run.status in {"completed", "failed", "cancelled"}:
            return
        if run.run_plan_id:
            return _execute_study_run(db, run, started)
        # Every run is compiled from a published study; anything else is not executable.
        run.status = "failed"; run.error_json = {"code": "run_plan_missing", "message": "Run has no compiled study plan"}
        run.completed_at = _now(); db.commit()
    finally:
        db.close()


def _resolve_node_inputs(node, plan, outputs):
    values = {}
    for name, binding in (node.get("inputs") or {}).items():
        if isinstance(binding, dict) and set(binding) == {"parameter"}:
            key = binding["parameter"]
            if key not in plan["parameters"]:
                raise ValueError(f"parameter binding is unavailable: {key}")
            values[name] = plan["parameters"][key]
        elif isinstance(binding, dict) and set(binding) == {"from"}:
            endpoint = binding["from"]
            source, port = endpoint.split(".", 1)
            if source not in outputs or port not in outputs[source]:
                raise ValueError(f"node output binding is unavailable: {endpoint}")
            values[name] = outputs[source][port]
        else:
            values[name] = binding
    for edge in plan["edges"]:
        source_endpoint = edge["source"]
        target_endpoint = edge["target"]
        source, source_port = source_endpoint.split(".", 1)
        target, target_port = target_endpoint.split(".", 1)
        if target != node["key"]:
            continue
        if source not in outputs or source_port not in outputs[source]:
            raise ValueError(f"edge source output is unavailable: {source_endpoint}")
        values[target_port] = outputs[source][source_port]
    return values


def _execute_study_node(db, run, plan, node, inputs, graph_snapshot):
    from app.models.v2.logic_asset import LogicAsset
    from app.models.v2.query_view import QueryDataView
    from app.services.v2.logic_assets import execute

    kind = node["kind"]
    config = node.get("config") or {}
    outputs = {}
    if kind == "object_query":
        from app.models.user import User
        from app.schemas.v2.object_query import BaseObjectSet, ExecutionContext, LoadObjectSetRequest, PropertyRef, ReadOptions, TypeRef
        from app.services.v2.graph.falkordb_service import FalkorDBService
        from app.services.v2.object_query.core import FalkorReadAdapter, QueryCore, QueryPolicy
        from app.services.v2.object_query.metadata import load_sql_metadata
        view = db.get(QueryDataView, plan["data_view_id"])
        if not view or view.status != "ready":
            raise RuntimeError("Pinned data view is unavailable")
        graph = FalkorDBService()
        if not graph.available:
            raise RuntimeError("Ontology graph is unavailable")
        user = db.get(User, run.created_by)
        if not user or not user.is_active:
            raise PermissionError("Run principal is no longer active")
        metadata = load_sql_metadata(db, plan["ontology_id"])
        from app.services.v2.object_query.core import metadata_digest
        if metadata_digest(metadata) != plan["ontology_metadata_digest"]:
            raise RuntimeError("Ontology metadata changed after this run plan was compiled")
        request = LoadObjectSetRequest(
            expression=BaseObjectSet(kind="base", type_ref=TypeRef(api_name=config["type"])),
            read=ReadOptions(
                select=[PropertyRef(api_name=field) for field in config["select"]],
                page_size=200,
                materialization_limit=min(plan["budgets"]["max_objects"], 10_000),
            ),
            context=ExecutionContext(
                ontology_id=plan["ontology_id"],
                revision_policy="pinned" if plan.get("ontology_metadata_revision_id") else "latest",
                revision_id=plan.get("ontology_metadata_revision_id"),
                consistency="snapshot",
                metadata_digest=plan["ontology_metadata_digest"],
                data_view_id=plan["data_view_id"],
                scenario_id=plan["scenario_id"],
                scenario_revision=plan["scenario_revision"],
            ),
        )
        core = QueryCore(
            metadata,
            FalkorReadAdapter(graph._graph(view.graph_key), graph_ontology_id=view.graph_key,
                              max_objects=plan["budgets"]["max_objects"]),
            QueryPolicy(principal=run.created_by),
        )
        selected, loaded = core.materialize(
            request,
            max_pages=max(1, (plan["budgets"]["max_objects"] + 199) // 200),
        )
        if loaded.completeness != "complete":
            raise RuntimeError("Object Query did not return a complete snapshot result")
        selected = [item.model_dump(mode="json") for item in selected]
        port = next(iter(node.get("outputs") or {"objects": "object_set"}))
        outputs[port] = selected
    elif kind in {"function", "time_series"}:
        implementation = node.get("implementation") or {}
        asset = db.query(LogicAsset).filter_by(
            ontology_id=run.result_manifest["provenance"]["ontology_id"],
            asset_key=implementation.get("key"), version=implementation.get("version"), status="published",
        ).first()
        if not asset:
            raise ValueError("Pinned Logic Asset is unavailable")
        contract = {
            "asset_key": asset.asset_key,
            "name": asset.name,
            "kind": asset.kind,
            "implementation": asset.implementation,
            "version": asset.version,
            "input_schema": asset.input_schema,
            "output_schema": asset.output_schema,
            "bindings": asset.bindings or {},
            "executor_type": asset.executor_type,
            "config": asset.config or {},
        }
        execution = execute(contract, inputs, ontology_id=asset.ontology_id)
        returned = execution["output"]
        for port, output_key in (node.get("outputs") or {}).items():
            if output_key in returned:
                outputs[port] = returned[output_key]
        outputs["result"] = returned
    elif kind == "action_preview":
        from app.models.user import User
        from app.models.v2.action import OntologyActionType
        from app.services.v2.function_binding import function_resolver
        from app.services.v2.graph.falkordb_service import FalkorDBService
        from app.services.v2.object_query.core import FalkorReadAdapter
        from app.services.v2.scenario_actions import compile_actions

        implementation = node.get("implementation") or {}
        action_type = db.query(OntologyActionType).filter_by(
            ontology_id=plan["ontology_id"], id=implementation.get("key"),
            version=int(implementation.get("version", -1)), action_category="scenario",
            enabled=True, status="published",
        ).first()
        if not action_type:
            raise ValueError("Pinned scenario Action is unavailable")
        view = db.get(QueryDataView, plan["data_view_id"])
        graph = FalkorDBService()
        user = db.get(User, run.created_by)
        if not view or view.status != "ready" or not graph.available or not user or not user.is_active:
            raise RuntimeError("Pinned Action preview context is unavailable")
        snapshot = FalkorReadAdapter(
            graph._graph(view.graph_key), graph_ontology_id=view.graph_key
        ).read(plan["ontology_id"])
        edits = compile_actions(
            plan["ontology_id"], plan["scenario_id"],
            [{"action_type_id": action_type.id, "parameters": inputs}],
            {action_type.id: action_type}, snapshot, actor=user,
            function_resolver=function_resolver(db, plan["ontology_id"]),
        )
        edit_rows = [item.model_dump(mode="json") for item in edits]
        edit_count = sum(item.get("op") != "invoke_action" for item in edit_rows)
        configured_outputs = node.get("outputs") or {"preview": "edits", "count": "edit_count"}
        available = {"edits": edit_rows, "edit_count": edit_count, "action_count": 1}
        outputs = {port: available[source] for port, source in configured_outputs.items() if source in available}
    elif kind == "aggregate_metric":
        operation = config.get("operation", "count")
        value = config.get("value")
        if value is None:
            value = next(iter(inputs.values()), [])
        if operation == "count":
            result = len(value) if isinstance(value, (list, dict, str)) else int(value is not None)
        else:
            values = value if isinstance(value, list) else [value]
            if not values or any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in values):
                raise ValueError("Aggregate input must be a non-empty numeric list")
            result = {"sum": sum(values), "mean": sum(values) / len(values),
                      "min": min(values), "max": max(values)}.get(operation)
            if result is None:
                raise ValueError("Unsupported aggregate operation")
        port = next(iter(node.get("outputs") or {"value": "number"}))
        outputs[port] = result
    elif kind == "compare":
        operation = config.get("operation", "delta")
        values = list(inputs.values())
        if len(values) < 2 or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values[:2]):
            raise ValueError("Compare node requires two numeric inputs")
        left, right = values[:2]
        result = {"delta": right - left, "ratio": (right / left if left else None),
                  "equal": left == right}.get(operation)
        if operation not in {"delta", "ratio", "equal"}:
            raise ValueError("Unsupported compare operation")
        port = next(iter(node.get("outputs") or {"value": "number"}))
        outputs[port] = result
    else:
        raise RuntimeError(f"Unsupported compiled node kind: {kind}")
    return outputs, graph_snapshot


def _execute_study_run(db, run, started):
    """Execute a compiled, immutable Study DAG and persist bounded artifacts."""
    import json
    from app.models.v2.scenario import ScenarioRunArtifact, ScenarioRunStage
    from app.models.v2.scenario_study import RunPlan
    from app.services.v2.scenario_studies import stable_hash

    plan_row = db.get(RunPlan, run.run_plan_id)
    if not plan_row:
        run.status = "failed"
        run.error_json = {"code": "run_plan_missing", "message": "Compiled run plan is unavailable"}
        run.completed_at = _now()
        db.commit()
        return
    plan = plan_row.plan_json
    nodes = {node["key"]: node for node in plan["nodes"]}
    from app.services.v2.authorization_service import AuthorizationContext, resolve_projection
    principal = db.get(User, run.created_by)
    if not principal or not principal.is_active:
        run.status = "failed"
        run.error_json = {"code": "permission_denied", "message": "Run principal is no longer active"}
        run.completed_at = _now()
        db.commit()
        return
    requested_fields = sorted({
        field
        for node in plan["nodes"] if node["kind"] == "object_query"
        for field in node.get("config", {}).get("select", [])
    })
    permission = resolve_projection(db, AuthorizationContext(
        ontology_id=plan["ontology_id"],
        principal_id=principal.id,
        principal_role=principal.role,
        metadata_revision_id=plan.get("ontology_metadata_revision_id"),
        requested_fields=tuple(requested_fields),
    ), principal.role)
    if not permission.allowed or permission.permission_digest != plan["permission_projection_digest"]:
        run.status = "failed"
        run.error_json = {"code": "permission_projection_changed", "message": "Permissions changed after this run plan was compiled"}
        run.completed_at = _now()
        db.commit()
        return
    stages = db.query(ScenarioRunStage).filter_by(run_id=run.id).order_by(ScenarioRunStage.sequence).all()
    if len(stages) != len(plan["topological_order"]):
        run.status = "failed"
        run.error_json = {"code": "run_stage_manifest_mismatch", "message": "Run stages do not match the compiled plan"}
        run.completed_at = _now()
        db.commit()
        return

    run.status = "running"
    run.started_at = run.started_at or _now()
    run.current_stage = stages[0].stage_key if stages else "complete"
    run.result_manifest = {"provenance": {
        "ontology_id": db.get(RunPlan, run.run_plan_id).plan_json.get("ontology_id", ""),
        "run_plan_id": plan_row.id,
        "plan_hash": plan_row.plan_hash,
        "study_version_id": plan_row.study_version_id,
        "scenario_id": plan_row.scenario_id,
        "scenario_revision": plan_row.scenario_revision,
        "data_view_id": plan_row.data_view_id,
        "metadata_digest": plan_row.ontology_metadata_digest,
        "permission_projection_digest": plan_row.permission_projection_digest,
    }, "nodes": {}, "metrics": [], "completeness": "exact"}
    # The ontology identity is part of the pinned data view rather than an
    # independently editable Run field.
    from app.models.v2.query_view import QueryDataView
    pinned_view = db.get(QueryDataView, plan_row.data_view_id)
    if pinned_view:
        run.result_manifest["provenance"]["ontology_id"] = pinned_view.ontology_id
    db.commit()

    outputs = {}
    graph_snapshot = None
    artifact_bytes = 0
    for index, stage in enumerate(stages):
        node_key = plan["topological_order"][index]
        node = nodes[node_key]
        db.refresh(run)
        if run.cancel_requested:
            _commit_stage(db, stage, "cancelled", error={"code": "cancelled", "message": "Run was cancelled"})
            run.status = "cancelled"
            run.current_stage = "cancelled"
            run.completed_at = _now()
            run.duration_ms = int((monotonic() - started) * 1000)
            db.commit()
            return
        if monotonic() - started > plan["budgets"]["max_wall_seconds"]:
            error = {"code": "run_timeout", "message": "Study exceeded its configured wall-time budget", "node_key": node_key}
            _commit_stage(db, stage, "failed", error=error)
            run.status = "failed"
            run.error_json = error
            run.current_stage = stage.stage_key
            run.completed_at = _now()
            run.duration_ms = int((monotonic() - started) * 1000)
            db.commit()
            return
        stage.status = "running"
        stage.started_at = _now()
        stage.summary_json = {"node_key": node_key, "kind": node["kind"]}
        run.current_stage = stage.stage_key
        run.progress = int(index * 100 / max(len(stages), 1))
        db.commit()
        try:
            bound = _resolve_node_inputs(node, plan, outputs)
            node_outputs, graph_snapshot = _execute_study_node(db, run, plan, node, bound, graph_snapshot)
            serialized = json.dumps(node_outputs, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
            artifact_bytes += len(serialized)
            if artifact_bytes > plan["budgets"]["max_artifact_bytes"]:
                raise ValueError("Study output exceeded the total artifact size budget")
            digest = stable_hash(node_outputs)
            outputs[node_key] = node_outputs
            manifest = {"node_key": node_key, "kind": node["kind"], "outputs": node_outputs,
                        "content_digest": digest, "run_plan_id": plan_row.id,
                        "data_view_id": plan_row.data_view_id,
                        "scenario_revision": plan_row.scenario_revision}
            existing_artifact = db.query(ScenarioRunArtifact).filter_by(
                run_id=run.id, artifact_type=f"node:{node_key}"
            ).first()
            if existing_artifact:
                existing_artifact.manifest_json = manifest
                existing_artifact.content_digest = digest
                existing_artifact.data_view_id = plan_row.data_view_id
            else:
                db.add(ScenarioRunArtifact(run_id=run.id, artifact_type=f"node:{node_key}",
                    data_view_id=plan_row.data_view_id, manifest_json=manifest, content_digest=digest))
            run.result_manifest["nodes"][node_key] = {"kind": node["kind"], "outputs": node_outputs,
                "content_digest": digest, "completeness": "exact"}
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(run, "result_manifest")
            stage.status = "completed"
            stage.completed_at = _now()
            stage.duration_ms = _duration_ms(stage.started_at, stage.completed_at)
            stage.summary_json = {"node_key": node_key, "kind": node["kind"], "content_digest": digest,
                                  "output_ports": sorted(node_outputs)}
            run.progress = int((index + 1) * 100 / max(len(stages), 1))
            db.commit()
        except Exception as exc:
            stage.status = "failed"
            stage.completed_at = _now()
            stage.duration_ms = _duration_ms(stage.started_at, stage.completed_at)
            stage.error_json = {"code": "node_execution_failed", "message": str(exc), "node_key": node_key}
            run.status = "failed"
            run.error_json = {"code": "node_execution_failed", "message": str(exc), "node_key": node_key}
            run.completed_at = _now()
            run.duration_ms = int((monotonic() - started) * 1000)
            db.commit()
            return

    metric_results = []
    for metric in plan["metrics"]:
        node_key, port = metric["source"].split(".", 1)
        if node_key not in outputs or port not in outputs[node_key]:
            run.status = "failed"
            run.error_json = {"code": "metric_output_missing", "message": "Declared metric output is unavailable", "metric_key": metric["key"]}
            run.completed_at = _now()
            db.commit()
            return
        value = outputs[node_key][port]
        valid_metric = {
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "decimal": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "duration": isinstance(value, (int, float)) and not isinstance(value, bool),
        }[metric["type"]]
        if not valid_metric or isinstance(value, float) and not __import__("math").isfinite(value):
            run.status = "failed"
            run.error_json = {"code": "metric_type_mismatch", "message": "Metric output does not match its declared type", "metric_key": metric["key"]}
            run.completed_at = _now()
            db.commit()
            return
        metric_results.append({"key": metric["key"], "label": metric.get("label") or metric["key"],
            "type": metric["type"], "direction": metric["direction"], "unit": metric.get("unit") or "",
            "value": value, "completeness": "exact",
            "provenance": {"node_key": node_key, "node_digest": run.result_manifest["nodes"][node_key]["content_digest"]}})
    constraint_results = []
    for constraint in plan["constraints"]:
        node_key, port = constraint["expression_ref"].split(".", 1)
        observed = outputs[node_key][port]
        config = constraint["config"]
        operator = config["operator"]
        if operator == "between":
            satisfied = isinstance(observed, (int, float)) and not isinstance(observed, bool) and config["minimum"] <= observed <= config["maximum"]
        elif operator in {"lt", "lte", "gt", "gte"}:
            expected = config["value"]
            if isinstance(observed, bool) or isinstance(expected, bool) or not isinstance(observed, (int, float)) or not isinstance(expected, (int, float)):
                run.status = "failed"
                run.error_json = {"code": "constraint_type_mismatch", "message": "Constraint comparison requires numeric values", "constraint_key": constraint["key"]}
                run.completed_at = _now()
                db.commit()
                return
            satisfied = {"lt": observed < expected, "lte": observed <= expected,
                         "gt": observed > expected, "gte": observed >= expected}[operator]
        else:
            expected = config["value"]
            satisfied = observed == expected if operator == "eq" else observed != expected
        constraint_results.append({"key": constraint["key"], "severity": constraint["severity"],
            "observed": observed, "operator": operator, "satisfied": bool(satisfied),
            "source": constraint["expression_ref"]})
    run.result_manifest["metrics"] = metric_results
    run.result_manifest["constraints"] = constraint_results
    run.result_manifest["constraints_satisfied"] = all(item["satisfied"] or item["severity"] == "soft" for item in constraint_results)
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(run, "result_manifest")
    run.output_digest = stable_hash(run.result_manifest)
    run.status = "completed"
    run.current_stage = "complete"
    run.progress = 100
    run.completed_at = _now()
    run.duration_ms = int((monotonic() - started) * 1000)
    db.commit()


