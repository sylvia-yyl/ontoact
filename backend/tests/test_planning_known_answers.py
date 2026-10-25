"""Hand-checked answers on tiny portfolios, so the planner is tested apart from the demo data."""
from app.services.v2.mrp_planning import plan_portfolio

from portfolios import flex_line, shared_part


def by_id(result):
    return {row["id"]: row for row in result["candidate_actions"]}


def status(result):
    return {row["id"]: row["status"] for row in result["demand_events"]}


def test_shared_part_baseline_serves_the_earlier_order_first():
    result = plan_portfolio(shared_part())
    # A (due day 10) takes 6 of 10 units; B needs 8, gets the remaining 4 plus 4 from the PO on day 30.
    assert status(result) == {"dA": "on_time", "dB": "late"}
    assert result["revenue_at_risk"] == 160          # 4 x 40


def test_reallocating_the_shared_part_trades_one_line_for_the_other():
    row = by_id(plan_portfolio(shared_part()))["reallocate:Shared"]
    # B earns 20 per unit of the part (160 / 8), A earns 10 (60 / 6): B goes first, A now waits for day 30.
    assert [o["demand_id"] for o in row["protected_orders"]] == ["dB"]
    assert [o["demand_id"] for o in row["harmed_orders"]] == ["dA"]
    assert row["revenue_at_risk"] == 60
    assert row["incremental_cost"] == 0
    assert row["actions"][0]["ranked_demands"] == ["dB", "dA"]
    summary = row["impact"]["summary"]
    assert (summary["orders_better"], summary["orders_worse"], summary["product_lines"]) == (1, 1, 2)


def test_expediting_the_shared_po_protects_without_harm():
    row = by_id(plan_portfolio(shared_part()))["expedite:Shared"]
    assert [o["demand_id"] for o in row["protected_orders"]] == ["dB"]
    assert row["harmed_orders"] == []
    assert row["incremental_cost"] == 5               # 10 units x 0.5 premium
    impact = row["impact"]
    assert any(node["id"] == "supply:PO-1" and node.get("change") == "action" for node in impact["nodes"])


def test_flex_line_rescues_an_order_blocked_by_maintenance():
    result = plan_portfolio(flex_line())
    assert status(result) == {"dA": "late"}           # A line is down until day 20
    row = by_id(result)["reschedule:alternate_lines"]
    assert [o["demand_id"] for o in row["protected_orders"]] == ["dA"]
    moves = [a for a in row["actions"] if a["action_type"] == "reassign_work_order"]
    assert moves == [{"action_type": "reassign_work_order", "demand_id": "dA", "from_resource": "A line", "to_resource": "Flex line"}]
