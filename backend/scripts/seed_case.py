"""Load a demo case pack into a running OntoAct backend.

    python scripts/seed_case.py dataco_mrp
    python scripts/seed_case.py container_scheduling --api http://backend:8000

A pack (``demo_cases/<case>/``) holds the ontology, its objects and links, the
study, optional Functions and Action types, and an optional app definition.
Objects and links are written straight to SQL and the graph (there is no bulk
object API); everything else goes through the HTTP API the way a user would.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.models.entity import Entity  # noqa: E402
from app.models.entity_instance import EntityInstance  # noqa: E402
from app.models.relation import Relation  # noqa: E402
from app.services.v2.graph.falkordb_service import FalkorDBService  # noqa: E402

CASES = Path(os.getenv("DEMO_CASES_DIR", Path(__file__).resolve().parents[2] / "demo_cases"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def read_pack(case: str) -> dict:
    folder = CASES / case
    manifest = json.loads((folder / "MANIFEST.json").read_text(encoding="utf-8"))
    for name, meta in manifest["files"].items():
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != meta["sha256"]:
            raise SystemExit(f"{case}/{name} does not match MANIFEST.json")
    ontology = json.loads((folder / "ontology.json").read_text(encoding="utf-8"))
    names = [link["api_name"] for link in ontology["link_types"]]
    if len(names) != len(set(names)):
        raise SystemExit(f"{case}: link names must be unique (a query resolves a link by name and direction)")
    app_path = folder / "app.json"
    cases_path = folder / "cases.json"
    return {"cases": json.loads(cases_path.read_text(encoding="utf-8")) if cases_path.exists() else [],
            "folder": folder, "manifest": manifest,
            "ontology": ontology,
            "objects": _jsonl(folder / "objects.jsonl"), "links": _jsonl(folder / "links.jsonl"),
            "study": json.loads((folder / "study.json").read_text(encoding="utf-8")),
            "app": json.loads(app_path.read_text(encoding="utf-8")) if app_path.exists() else None}


def load_objects(ontology_id: str, pack: dict) -> tuple[int, int]:
    """Write object types, instances and links; ids are namespaced per ontology."""
    graph = FalkorDBService()
    if not graph.available:
        raise SystemExit("The graph database is unavailable")
    prefix = f"{ontology_id[:8]}:"
    with SessionLocal() as db:
        entities = {}
        for spec in pack["ontology"]["object_types"]:
            entity = Entity(ontology_id=ontology_id, name_cn=spec["api_name"], name_en=spec["api_name"],
                            canonical_id=f"ontology:{spec['api_name']}", type="EntityType",
                            properties={"property_definitions": spec["properties"], "key_property": spec.get("key_property")})
            db.add(entity)
            db.flush()
            entities[spec["api_name"]] = entity
        for spec in pack["ontology"]["link_types"]:
            db.add(Relation(ontology_id=ontology_id, source_entity=entities[spec["source"]].id, target_entity=entities[spec["target"]].id,
                            type=spec["api_name"], properties={"api_name": spec["api_name"], "via": spec["via"], "cardinality": "many"}))
        # A link whose target type has no business key refers to the target by object id, so that id gets the prefix too.
        keyed = {spec["api_name"] for spec in pack["ontology"]["object_types"] if spec.get("key_property")}
        id_refs = {(spec["source"], spec["via"]) for spec in pack["ontology"]["link_types"] if spec["target"] not in keyed}
        nodes = []
        for row in pack["objects"]:
            object_id = prefix + row["id"]
            props = dict(row["properties"])
            for source_type, prop in id_refs:
                if row["type"] == source_type and props.get(prop):
                    props[prop] = prefix + props[prop]
            db.add(EntityInstance(id=object_id, entity_id=entities[row["type"]].id, ontology_id=ontology_id,
                                  row_identity=object_id, row_data=props))
            nodes.append({"id": object_id, "entity_type": row["type"], "properties": props})
        db.commit()
    graph.upsert_instances(ontology_id, nodes)
    links = [{"type": link["type"], "source": prefix + link["source"], "target": prefix + link["target"]} for link in pack["links"]]
    graph.upsert_relations(ontology_id, links)
    return len(nodes), len(links)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case")
    parser.add_argument("--api", default=os.getenv("ONTOACT_API", "http://localhost:8000"))
    args = parser.parse_args()
    pack = read_pack(args.case)

    with httpx.Client(base_url=args.api, timeout=300) as client:
        def ok(response):
            if response.is_error:
                raise SystemExit(f"{response.request.method} {response.request.url.path} -> {response.status_code}: {response.text[:500]}")
            body = response.json()
            return body.get("data", body) if isinstance(body, dict) and "data" in body else body

        meta = pack["ontology"]
        body = {"name": meta["name"], "domain": meta["domain"], "description": meta["description"]}
        created = client.post("/api/v1/ontologies", json=body)
        if created.status_code == 409:  # names are unique; a re-seed gets its own ontology
            created = client.post("/api/v1/ontologies", json={**body, "name": f"{meta['name']} ({datetime.now():%Y-%m-%d %H:%M:%S})"})
        oid = ok(created)["id"]
        objects, links = load_objects(oid, pack)
        api = f"/api/v2/ontologies/{oid}"

        study_pack = pack["study"]
        if study_pack.get("builtin_functions"):
            ok(client.post(f"{api}/logic-assets/seed"))
        for function in study_pack.get("user_functions", []):
            source = (pack["folder"] / function["source_file"]).read_text(encoding="utf-8")
            ok(client.post(f"{api}/logic-assets/user-functions",
                           json={**{k: v for k, v in function.items() if k != "source_file"}, "source": source}))
        for action in study_pack.get("action_types", []):
            created_action = ok(client.post(f"{api}/scenario-action-types", json=action))
            ok(client.post(f"{api}/scenario-action-types/{created_action['id']}:publish"))

        study = ok(client.post(f"{api}/scenario-study-definitions",
                               json={"name": study_pack["name"], "description": study_pack.get("description", ""), "draft_spec": study_pack["spec"]}))
        version = ok(client.post(f"{api}/scenario-study-definitions/{study['id']}:publish",
                                 json={"expected_etag": study["etag"], "change_note": "Initial version"}))
        view = ok(client.post(f"{api}/object-query/data-views",
                              json={"source_ontology_id": oid, "source_manifest_digest": pack["manifest"]["files"]["objects.jsonl"]["sha256"]}))

        def run_case(name, kind, edits=()):
            """Create a scenario (with the case's edits), bind it to a case and wait for its run."""
            scenario = ok(client.post(f"{api}/scenarios", json={"name": name, "base_view_id": view["view_id"]}))
            if edits:
                ok(client.post(f"{api}/scenarios/{scenario['id']}/revisions", json={
                    "base_revision": 0, "expected_etag": scenario["etag"], "client_request_id": f"seed-{args.case}-{name}",
                    "edits": [{"op": "set_property", "target": {"ontology_id": oid, "concrete_type": row["object_type"],
                                                                "object_id": f"{oid[:8]}:{row['object_id']}"},
                               "property": row["property"], "value": row["value"], "expected_old_value": row.get("expected_old_value"),
                               "sequence": index}
                              for index, row in enumerate(edits)]}))
            case = ok(client.post(f"{api}/scenario-study-definitions/{study['id']}/cases",
                                  json={"study_version": version["version"], "scenario_id": scenario["id"], "name": name, "case_kind": kind}))
            ok(client.post(f"{api}/scenario-study-definitions/{study['id']}/cases/{case['id']}:compile"))
            run = ok(client.post(f"{api}/scenario-study-definitions/{study['id']}/cases/{case['id']}/runs",
                                 json={"expected_etag": case["etag"], "client_request_id": f"seed-{args.case}-{name}"}))
            started = time.monotonic()
            while True:
                state = ok(client.get(f"{api}/scenario-study-runs/{run['id']}"))
                if state["status"] in ("completed", "failed", "cancelled") or time.monotonic() - started > 300:
                    break
                time.sleep(1)
            if state["status"] != "completed":
                raise SystemExit(f"{name} run {state['status']}: {state.get('error')}")
            return case, run, time.monotonic() - started

        # What-if cases run first: an app source without a case shows the study's latest run, which is then the baseline.
        case_ids = {}
        for spec in pack["cases"]:
            what_if, _, _ = run_case(spec["name"], "candidate", spec["edits"])
            case_ids[spec["key"]] = what_if["id"]
        case, run, run_seconds = run_case("Baseline", "baseline")
        case_ids["baseline"] = case["id"]

        app_id = None
        if pack["app"]:
            definition = pack["app"]
            for source in definition.get("data_sources", []):
                if "study_id" in source:
                    source["study_id"] = study["id"]
                if source.get("case"):
                    source["case_id"] = case_ids[source.pop("case")]
            app = ok(client.post(f"{api}/workshop-apps", json={"name": definition.pop("name", meta["name"]),
                                                                "description": meta["description"], "definition": definition}))
            app_id = app["id"]
        print(json.dumps({"case": args.case, "ontology": oid, "objects": objects, "links": links, "study": study["id"],
                          "run": run["id"], "run_seconds": round(run_seconds, 2),
                          "cases": sorted(case_ids), "app": app_id}))
        if app_id:
            print(f"Open /apps/workshop/{app_id}?ontology={oid}")


if __name__ == "__main__":
    main()
