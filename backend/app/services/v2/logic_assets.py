"""Deterministic local logic binding registry.

Each asset has the same contract: typed inputs, a versioned implementation,
structured output, and an auditable trace.  These are deliberately local
implementations so they can be tested without an LLM or external service.
"""
from __future__ import annotations
from .logic_contracts import normalize_contract, normalize_units, validate_payload

ASSET_DEFINITIONS = [
    {"asset_key":"material_shortage_decision_v1","name":"Material shortage impact and revenue risk","kind":"what_if","implementation":"material_shortage_decision_v1","description":"Deterministic time-phased allocation across BOM, reservations, inventory and supply commitments with an auditable impact path and evaluated candidate actions.","input_schema":{"required":["demands","supply_options","boms","inventory","reservations","supply_commitments","scenario_time"]},"output_schema":{"fields":["feasible","shortages","demand_impacts","allocations","schedule","candidate_actions","revenue_at_risk","kpis","stranded_inventory","impact_path","completeness"]},"bindings":{"ontology_fields":["customer_order","item","bom_line","inventory_balance","reservation","supply_commitment","resource"]}},
    {"asset_key":"mrp_planning_v1","name":"Portfolio MRP planning and actions","kind":"what_if","implementation":"mrp_planning_v1","description":"Portfolio MRP over product lines: planning policies, quarter revenue/cost/OTIF, weekly material coverage, planned orders and evaluated actions (expedite, rework, defer POs, policy switch).","input_schema":{"required":["scenario_time", "horizon_weeks", "quarter_start", "quarter_end", "product_lines", "policy_definitions", "items", "demands", "boms", "inventory", "reservations", "supply_commitments", "supply_options", "fixed_tasks"]},"output_schema":{"fields":["scenario_time", "quarter", "totals", "portfolio", "policies", "demand_events", "demand_by_month", "coverage", "candidate_actions", "projected_revenue", "revenue_at_risk", "completeness"]},"bindings":{"ontology_fields":["product_line","planning_policy","item_master","customer_order","bom_line","inventory_lot","supply_commitment","supply_option"]}},
]

def _schema(asset_key: str, properties: dict, required: list[str], *, output: bool = False) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:logic:{asset_key}:{'output' if output else 'input'}:1.0.0",
        "type": "object", "properties": properties, "required": required,
        "additionalProperties": False,
    }

_CONTRACTS = {
    "material_shortage_decision_v1": (_schema("material_shortage_decision_v1", {"demands":{"type":"array","minItems":1,"maxItems":500},"supply_options":{"type":"array","maxItems":5000},"boms":{"type":"array","maxItems":2000},"inventory":{"type":"array"},"reservations":{"type":"array"},"supply_commitments":{"type":"array"},"fixed_tasks":{"type":"array","maxItems":5000},"scenario_time":{"type":"string"}}, ["demands","supply_options","boms","inventory","reservations","supply_commitments","scenario_time"]), _schema("material_shortage_decision_v1", {"feasible":{"type":"boolean"},"shortages":{"type":"array"},"demand_impacts":{"type":"array"},"allocations":{"type":"array"},"schedule":{"type":"array"},"candidate_actions":{"type":"array"},"revenue_at_risk":{"type":"number"},"kpis":{"type":"object"},"stranded_inventory":{"type":"array"},"impact_path":{"type":"object"},"completeness":{"type":"string","enum":["exact","partial"]}}, ["feasible","shortages","demand_impacts","allocations","schedule","candidate_actions","revenue_at_risk","kpis","stranded_inventory","impact_path","completeness"], output=True)),
    "mrp_planning_v1": (_schema("mrp_planning_v1", {"scenario_time": {"type": "string"}, "horizon_weeks": {"type": "number", "minimum":1,"maximum":104}, "quarter_start": {"type": "number"}, "quarter_end": {"type": "number"}, "product_lines": {"type": "array"}, "policy_definitions": {"type": "array"}, "items": {"type": "array"}, "demands": {"type": "array"}, "boms": {"type": "array"}, "inventory": {"type": "array"}, "reservations": {"type": "array"}, "supply_commitments": {"type": "array"}, "supply_options": {"type": "array"}, "fixed_tasks": {"type": "array"}}, ["scenario_time", "horizon_weeks", "quarter_start", "quarter_end", "product_lines", "policy_definitions", "items", "demands", "boms", "inventory", "reservations", "supply_commitments", "supply_options", "fixed_tasks"]), _schema("mrp_planning_v1", {"scenario_time": {"type": "string"}, "quarter": {"type": "object"}, "totals": {"type": "object"}, "portfolio": {"type": "array"}, "policies": {"type": "array"}, "demand_events": {"type": "array"}, "demand_by_month": {"type": "array"}, "coverage": {"type": "object"}, "candidate_actions": {"type": "array"}, "projected_revenue": {"type": "number"}, "revenue_at_risk": {"type": "number"}, "completeness": {"type": "string"}}, ["scenario_time", "quarter", "totals", "portfolio", "policies", "demand_events", "demand_by_month", "coverage", "candidate_actions", "projected_revenue", "revenue_at_risk", "completeness"], output=True)),
}
for _asset in ASSET_DEFINITIONS:
    _asset["interface_key"] = f"manufacturing.{_asset['asset_key'].removesuffix('_v1')}"
    _asset["interface_version"] = "1.0.0"
    _asset["executor_type"] = "local"
    _asset["input_schema"], _asset["output_schema"] = _CONTRACTS[_asset["asset_key"]]

EXECUTORS = {}


def _material_shortage_decision(inputs):
    from .material_shortage import material_shortage_decision
    return material_shortage_decision(inputs)


EXECUTORS["material_shortage_decision_v1"] = _material_shortage_decision


def _mrp_planning(inputs):
    from .mrp_planning import plan_portfolio
    return plan_portfolio(inputs)


EXECUTORS["mrp_planning_v1"] = _mrp_planning


def execute(asset: dict, inputs: dict, *, metadata=None, snapshot=None, ontology_id=None, through_action=False) -> dict:
    from .function_contracts import SolverOutcome, execution_class, hydrate_domain, validate_domain, validate_edits, fail
    from .object_query.logic_binding import reject_page_binding
    reject_page_binding(asset, inputs)
    asset = normalize_contract(asset)
    kind = execution_class(asset)
    if kind == 'edit' and not through_action:
        fail('execution', 'Edit-producing Functions must execute through an Action')
    impl=asset.get("implementation") or asset.get("asset_key")
    from .user_functions import IMPLEMENTATION as USER_FUNCTION
    if impl != USER_FUNCTION and impl not in EXECUTORS: raise ValueError(f"No local implementation is registered for {impl}")
    normalized, unit_trace = normalize_units(asset["input_schema"], inputs)
    validate_payload(asset["input_schema"], normalized, "input")
    validate_domain(asset['input_schema'], normalized, metadata=metadata, snapshot=snapshot, ontology_id=ontology_id)
    if snapshot is not None:
        normalized = hydrate_domain(asset['input_schema'], normalized, snapshot=snapshot, ontology_id=ontology_id)
    if impl == USER_FUNCTION:
        from .user_functions import run as run_user_function
        output = run_user_function(asset.get("config") or {}, normalized)  # isolated runner, never in-process
    else:
        output=EXECUTORS[impl](normalized)
    validate_payload(asset["output_schema"], output, "output")
    from .decision_output import is_decision, validate_decision
    for value in (output.values() if isinstance(output, dict) else ()):
        if is_decision(value):
            validate_decision(value)  # a malformed decision result fails the run, not the workspace
    solver = output.get('solver') if isinstance(output, dict) else None
    if kind == 'edit' and isinstance(solver, dict) and solver.get('status') not in ('optimal', 'feasible'):
        raise SolverOutcome(solver)
    validate_domain(asset['output_schema'], output, metadata=metadata, snapshot=snapshot, ontology_id=ontology_id)
    if kind == 'edit':
        validate_edits(asset, output, ontology_id)
    return {"asset_key":asset.get("asset_key"),"interface_key":asset.get("interface_key"),"version":asset.get("version","1.0.0"),"implementation":impl,"inputs_bound":list(normalized),"output":output,"trace":[{"stage":"bind","field_count":len(normalized)}, *unit_trace, {"stage":"execute","implementation":impl},{"stage":"validate","status":"passed"}]}
