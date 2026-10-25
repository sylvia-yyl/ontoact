"""The numbers the README shows, recomputed from the committed DataCo pack."""
import json

import pytest

from app.services.v2.mrp_planning import plan_portfolio

from conftest import CASES
from portfolios import applied


def candidates(result):
    return {row["id"]: row for row in result["candidate_actions"]}


def lines_of(orders, inputs):
    line = {row["id"]: row["product_line"] for row in inputs["demands"]}
    return sorted({line[o["demand_id"]] for o in orders})


def test_pack_size(dataco_inputs):
    manifest = json.loads((CASES / "dataco_mrp" / "MANIFEST.json").read_text(encoding="utf-8"))
    assert (manifest["objects"], manifest["links"]) == (1181, 1639)
    assert len(dataco_inputs["demands"]) == 402


def test_baseline_totals(dataco_plan):
    totals = dataco_plan["totals"]
    assert totals["projected_revenue"] == pytest.approx(1262974.02)
    assert totals["revenue_gap"] == pytest.approx(-594149.67)
    assert totals["otif"] == pytest.approx(0.4453)
    assert totals["at_risk"] == 223
    assert len(dataco_plan["candidate_actions"]) == 21


def test_steel_reallocation_helps_the_trainer_and_hurts_two_other_lines(dataco_plan, dataco_inputs):
    row = candidates(dataco_plan)["reallocate:Cold-rolled Steel Sheet"]
    assert row["quarter_revenue_delta"] == pytest.approx(52913.56)
    assert row["incremental_cost"] == 0
    assert (len(row["protected_orders"]), len(row["harmed_orders"])) == (10, 16)
    assert lines_of(row["protected_orders"], dataco_inputs) == ["RIP"]
    # Kayaks use no steel: they slip because the trainers now built take shared shipping cartons first.
    assert lines_of(row["harmed_orders"], dataco_inputs) == ["KAYAK", "SAFE"]
    assert row["impact"]["summary"]["product_lines"] == 3


def test_fixing_the_safe_line_also_rescues_trainers(dataco_plan, dataco_inputs):
    row = candidates(dataco_plan)["combined:SAFE"]
    assert row["quarter_revenue_delta"] == pytest.approx(190117.13)
    assert lines_of(row["protected_orders"], dataco_inputs) == ["RIP", "SAFE"]
    line = {r["id"]: r["product_line"] for r in dataco_inputs["demands"]}
    assert sum(1 for o in row["protected_orders"] if line[o["demand_id"]] == "RIP") == 52
    assert row["harmed_orders"] == []


def test_supplier_outage_case(dataco_inputs):
    cases = json.loads((CASES / "dataco_mrp" / "cases.json").read_text(encoding="utf-8"))
    outage = next(case for case in cases if case["key"] == "supplier_outage")
    inputs = json.loads(json.dumps(dataco_inputs))
    pos = {row["id"]: row for row in inputs["supply_commitments"]}
    for edit in outage["edits"]:
        assert pos[edit["object_id"]][edit["property"]] == edit["expected_old_value"]
        pos[edit["object_id"]][edit["property"]] = edit["value"]
    result = plan_portfolio(inputs)
    assert len(outage["edits"]) == 179
    assert result["totals"]["otif"] == pytest.approx(0.2711)
    assert result["totals"]["at_risk"] == 293
    best = result["candidate_actions"][0]
    assert best["id"] == "combined:SAFE"
    assert best["quarter_revenue_delta"] == pytest.approx(159522.23)
    assert best["incremental_cost"] == pytest.approx(68259.45)


def test_applying_dataco_candidates_reproduces_their_prediction(dataco_plan, dataco_inputs):
    for cid in ("reallocate:Cold-rolled Steel Sheet", "reschedule:alternate_lines", "expedite:Cold-rolled Steel Sheet"):
        row = candidates(dataco_plan)[cid]
        after = plan_portfolio(applied(dataco_inputs, row))
        assert after["revenue_at_risk"] == pytest.approx(row["revenue_at_risk"]), cid
        assert after["totals"]["projected_revenue"] == pytest.approx(row["quarter_revenue_after"]), cid
