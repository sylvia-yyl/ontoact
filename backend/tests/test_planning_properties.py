"""Properties that must hold on any portfolio, checked on random ones."""
import json
from collections import defaultdict

import pytest

from app.services.v2.mrp_planning import Plan, plan_portfolio

from portfolios import applied, random_portfolio

SEEDS = range(40)
WRITE_BACK = {"expedite_supply_commitment", "reschedule_supply_commitment", "reassign_work_order", "reprioritize_allocation",
              "set_product_line_policy", "reschedule_work_orders"}


@pytest.mark.parametrize("seed", SEEDS)
def test_same_inputs_give_the_same_plan(seed):
    inputs = random_portfolio(seed)
    assert json.dumps(plan_portfolio(inputs), sort_keys=True) == json.dumps(plan_portfolio(inputs), sort_keys=True)


@pytest.mark.parametrize("seed", SEEDS)
def test_no_source_gives_more_than_it_has(seed):
    plan = Plan(random_portfolio(seed))
    result, _ = plan.evaluate(sim_policy={"replan": True, "expedite": [row["id"] for row in plan.raw["supply_commitments"]]})
    given = defaultdict(float)
    for row in result["allocations"]:
        given[row["source_id"]] += row["quantity"]
    capacity = {row["id"]: row["quantity"] for row in plan.raw["inventory"] + plan.raw["supply_commitments"]}
    assert all(given[source] <= capacity[source] + 1e-6 for source in given)


@pytest.mark.parametrize("seed", SEEDS)
def test_candidate_accounting_is_consistent(seed):
    result = plan_portfolio(random_portfolio(seed))
    for row in result["candidate_actions"]:
        protected = {o["demand_id"] for o in row["protected_orders"]}
        harmed = {o["demand_id"] for o in row["harmed_orders"]}
        assert not protected & harmed
        assert row["revenue_protected"] == pytest.approx(result["revenue_at_risk"] - row["revenue_at_risk"])
        impact = row["impact"]
        ids = {node["id"] for node in impact["nodes"]}
        assert all(edge["source"] in ids and edge["target"] in ids for edge in impact["edges"])
        summary = impact["summary"]
        assert summary["orders_better"] + summary["orders_worse"] == summary["orders_changed"]
        # Every order that became on time or late is in the impact graph with the right direction.
        changes = {node["id"].removeprefix("order:"): node.get("change") for node in impact["nodes"] if node["kind"] == "CustomerOrder"}
        assert all(changes.get(order) == "better" for order in protected)
        assert all(changes.get(order) == "worse" for order in harmed)


@pytest.mark.parametrize("seed", SEEDS)
def test_applying_a_candidate_reproduces_its_prediction(seed):
    """Write the actions back to the inputs, re-plan from scratch: the new baseline is what the candidate predicted."""
    inputs = random_portfolio(seed)
    for row in plan_portfolio(inputs)["candidate_actions"]:
        if not row["applicable"] or not {a["action_type"] for a in row["actions"]} <= WRITE_BACK:
            continue
        after = plan_portfolio(applied(inputs, row))
        assert after["revenue_at_risk"] == pytest.approx(row["revenue_at_risk"]), row["id"]
        assert after["totals"]["projected_revenue"] == pytest.approx(row["quarter_revenue_after"]), row["id"]
