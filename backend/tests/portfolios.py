"""Planning inputs that have nothing to do with the demo data: hand-built and random."""
from __future__ import annotations

import copy
import random

POLICY = {"id": "Standard", "capacity_factor": 1.0, "pull_in_days": 0, "conversion_factor": 1.0, "exclude_low_confidence": False}


def base(**extra) -> dict:
    return {"scenario_time": "2020-01-06T00:00:00Z", "horizon_weeks": 12, "quarter_start": 0, "quarter_end": 84,
            "policy_definitions": [dict(POLICY)], "reservations": [], "supply_options": [], "fixed_tasks": [], **extra}


def line(code: str) -> dict:
    return {"id": code, "name": f"{code} line", "policy": "Standard", "conversion_cost": 0, "resource": f"{code} line"}


def shared_part() -> dict:
    """Two lines share 10 units of one part.

    A (due day 10) needs 6 and earns 10 per unit of the part; B (due day 12) needs 8
    and earns 20 per unit.  Ten more units arrive on day 30, or on day 5 if expedited.
    """
    return base(
        product_lines=[line("A"), line("B")],
        items=[{"id": "A Assembly", "kind": "assembly", "product_line": "A", "unit_cost": 0},
               {"id": "B Assembly", "kind": "assembly", "product_line": "B", "unit_cost": 0},
               {"id": "Shared", "kind": "part", "product_line": None, "unit_cost": 1, "critical": True}],
        boms=[{"parent_item": "A Assembly", "component_item": "Shared", "quantity_per": 1},
              {"parent_item": "B Assembly", "component_item": "Shared", "quantity_per": 2}],
        inventory=[{"id": "LOT-1", "item": "Shared", "location": "Plant", "quantity": 10}],
        supply_commitments=[{"id": "PO-1", "item": "Shared", "quantity": 10, "available_at": 30, "expedite_available_at": 5,
                             "expedite_unit_premium": 0.5, "unit_cost": 1, "supplier": "S1", "status": "active"}],
        demands=[{"id": "dA", "item": "A Assembly", "product_line": "A", "quantity": 6, "due_at": 10, "unit_revenue": 10,
                  "processing_days": 1, "resource": "A line"},
                 {"id": "dB", "item": "B Assembly", "product_line": "B", "quantity": 4, "due_at": 12, "unit_revenue": 40,
                  "processing_days": 1, "resource": "B line"}])


def flex_line() -> dict:
    """Line A is blocked until day 20; its order may move to a flex line."""
    return base(
        product_lines=[line("A")],
        items=[{"id": "A Assembly", "kind": "assembly", "product_line": "A", "unit_cost": 0},
               {"id": "Part", "kind": "part", "product_line": "A", "unit_cost": 1}],
        boms=[{"parent_item": "A Assembly", "component_item": "Part", "quantity_per": 1}],
        inventory=[{"id": "LOT-1", "item": "Part", "location": "Plant", "quantity": 10}],
        supply_commitments=[],
        fixed_tasks=[{"id": "MAINT", "resource": "A line", "start": 0, "finish": 20}],
        demands=[{"id": "dA", "item": "A Assembly", "product_line": "A", "quantity": 5, "due_at": 10, "unit_revenue": 10,
                  "processing_days": 2, "resource": "A line", "alternate_resources": ["Flex line"]}])


def random_portfolio(seed: int) -> dict:
    """A random portfolio: lines with private and shared parts, stock, late POs, maintenance and flex lines."""
    rng = random.Random(seed)
    lines = [line(code) for code in rng.sample(["L1", "L2", "L3", "L4"], rng.randint(2, 4))]
    shared = [f"S{index}" for index in range(rng.randint(1, 3))]
    items, boms, inventory, commitments, demands, tasks = [], [], [], [], [], []
    for row in lines:
        code = row["id"]
        items.append({"id": f"{code} Assembly", "kind": "assembly", "product_line": code, "unit_cost": 0})
        own = [f"{code}:P{index}" for index in range(rng.randint(1, 3))]
        for part in own:
            items.append({"id": part, "kind": "part", "product_line": code, "unit_cost": rng.randint(1, 9), "critical": rng.random() < 0.5})
        for part in own + rng.sample(shared, rng.randint(1, len(shared))):
            boms.append({"parent_item": f"{code} Assembly", "component_item": part, "quantity_per": rng.randint(1, 3)})
        if rng.random() < 0.5:
            tasks.append({"id": f"MAINT-{code}", "resource": f"{code} line", "start": rng.randint(0, 20), "finish": rng.randint(25, 45)})
    for part in shared:
        items.append({"id": part, "kind": "part", "product_line": None, "unit_cost": rng.randint(1, 5), "critical": True})
    for row in items:
        if row["kind"] != "part":
            continue
        inventory.append({"id": f"LOT-{row['id']}", "item": row["id"], "location": "Plant", "quantity": rng.randint(0, 60)})
        for index in range(rng.randint(1, 3)):
            arrive = rng.randint(5, 70)
            po = {"id": f"PO-{row['id']}-{index}", "item": row["id"], "quantity": rng.randint(5, 60), "available_at": arrive,
                  "unit_cost": row["unit_cost"], "supplier": rng.choice(["X", "Y", "Z"]), "status": "active", "confidence": rng.choice([0.6, 0.95])}
            if rng.random() < 0.5 and arrive > 10:
                po.update(expedite_available_at=rng.randint(1, arrive - 1), expedite_unit_premium=round(rng.uniform(0.1, 2), 2))
            commitments.append(po)
    for index in range(rng.randint(8, 30)):
        code = rng.choice(lines)["id"]
        demand = {"id": f"D{index:03d}", "item": f"{code} Assembly", "product_line": code, "quantity": rng.randint(1, 15),
                  "due_at": rng.randint(3, 80), "unit_revenue": rng.randint(5, 80), "processing_days": round(rng.uniform(0.5, 4), 2),
                  "resource": f"{code} line", "priority": rng.randint(1, 3)}
        if rng.random() < 0.3:
            demand["alternate_resources"] = ["Flex line"]
        demands.append(demand)
    policies = [dict(POLICY), {**POLICY, "id": "Fast", "capacity_factor": 1.4, "conversion_factor": 1.2}]
    return base(product_lines=lines, items=items, boms=boms, inventory=inventory, supply_commitments=commitments,
                demands=demands, fixed_tasks=tasks, policy_definitions=policies)


def applied(inputs: dict, candidate: dict) -> dict:
    """The inputs after the candidate's actions are written back, as its compiled Ontology edits would."""
    out = copy.deepcopy(inputs)
    pos = {row["id"]: row for row in out["supply_commitments"]}
    demands = {row["id"]: row for row in out["demands"]}
    for action in candidate["actions"]:
        kind = action["action_type"]
        if kind == "expedite_supply_commitment":
            pos[action["commitment_id"]]["available_at"] = action["available_at"]
        elif kind == "reschedule_supply_commitment":
            pos[action["commitment_id"]]["available_at"] = action["available_at"]
        elif kind == "reassign_work_order":
            demands[action["demand_id"]].update(resource=action["to_resource"], alternate_resources=[action["from_resource"]])
        elif kind == "reprioritize_allocation":
            for rank, demand_id in enumerate(action["ranked_demands"], start=1):
                demands[demand_id]["allocation_rank"] = rank
        elif kind == "set_product_line_policy":
            next(row for row in out["product_lines"] if row["id"] == action["product_line"])["policy"] = action["policy"]
        elif kind != "reschedule_work_orders":
            raise AssertionError(f"no write-back rule for {kind}")
    return out
