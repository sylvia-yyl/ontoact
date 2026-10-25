"""Build the dataco_mrp pack from the DataCo CSV: real demand, rule-derived supply.

    python scripts/build_dataco_pack.py <path-to>/DataCoSupplyChainDataset.csv
    python scripts/build_dataco_pack.py <csv> --variant independent --out /tmp/pack

Real (DataCo Smart Supply Chain, Mendeley Data doi:10.17632/8gx2fvg2k6.5,
CC BY 4.0): products, list prices, order dates, quantities, markets, customer
segments and scheduled shipping days for five high-volume assembled products.
Cancelled and suspected-fraud orders are dropped; customer identity columns
are never read.

Notional (no public source exists): BOMs, on-hand stock, purchase orders,
line capacity, supplier disruptions and one quality hold.  They are derived
by fixed rules from the real demand (e.g. PO volume = real demand x coverage
factor) with a fixed seed, so the pack is reproducible.  The planning model
computes every KPI, risk and action from these inputs; nothing here encodes
an answer.

Variants:
  independent  every product line owns its parts and its line (the first pack)
  coupled      lines share scarce materials and a flex line, so an action on
               one line can help or hurt another
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.services.v2.material_shortage_objects import CODED_TYPES, OBJECT_TYPES, PLANNING_INPUT_TYPES, fixture_objects  # noqa: E402

SOURCE_SHA256 = "fa6d022ed437155e1a2f0378710602848703c8a7f203f7ff5d77805bf8480aa6"
SEED = 20161003
PLANNING_DATE = date(2016, 10, 3)          # a Monday inside the real data window
HORIZON_WEEKS = 52
QUARTER = (date(2016, 10, 3), date(2017, 1, 2))
SITES = ("Plant A", "Plant B")
SUPPLIERS = ("Northwind Components", "Apex Precision", "Coastal Plastics")

# Real DataCo product -> line code and BOM. Part: (name, qty per unit, share of price, lead days).
PRODUCTS = {
    "Diamondback Women's Serene Classic Comfort Bi": ("BIKE", "Comfort Bike", {
        "Frame Module": [("Aluminum Frame", 1, .12, 42), ("Suspension Fork", 1, .05, 28), ("Headset", 1, .01, 21)],
        "Drivetrain Module": [("Crankset", 1, .03, 28), ("Chain", 1, .01, 14), ("Rear Derailleur", 1, .03, 35), ("Shifter", 1, .02, 28), ("Pedal", 2, .005, 14)],
        "Wheel Module": [("Wheelset", 1, .07, 35), ("Tire", 2, .01, 21), ("Inner Tube", 2, .003, 14)],
        "Cockpit Module": [("Handlebar", 1, .01, 21), ("Grip", 2, .002, 14), ("Saddle", 1, .015, 21), ("Brake Set", 1, .025, 28)],
        "Pack Module": [("Shipping Carton", 1, .006, 14), ("Hardware Kit", 1, .004, 14)]}),
    "Field & Stream Sportsman 16 Gun Fire Safe": ("SAFE", "Gun Fire Safe", {
        "Body Module": [("Steel Body Panel", 1, .14, 35), ("Door Panel", 1, .07, 35), ("Fireboard Lining", 4, .02, 28), ("Hinge Set", 1, .01, 21)],
        "Lock Module": [("Combination Lock", 1, .05, 42), ("Locking Bolt", 6, .004, 21), ("Handle", 1, .01, 21)],
        "Interior Module": [("Gun Rack", 1, .02, 21), ("Interior Carpet", 1, .01, 14)],
        "Pack Module": [("Shipping Crate", 1, .01, 14), ("Hardware Kit", 1, .004, 14)]}),
    "Pelican Sunstream 100 Kayak": ("KAYAK", "Sit-in Kayak", {
        "Hull Module": [("HDPE Hull", 1, .2, 42), ("Drain Plug", 1, .002, 14), ("Deck Bungee", 1, .004, 14)],
        "Outfit Module": [("Seat", 1, .04, 28), ("Footrest", 2, .006, 21), ("Carry Handle", 2, .003, 14), ("Paddle", 1, .03, 21)],
        "Pack Module": [("Shipping Carton", 1, .01, 14)]}),
    "Perfect Fitness Perfect Rip Deck": ("RIP", "Rip Deck Trainer", {
        "Frame Module": [("Steel Rail", 1, .12, 28), ("Bushing", 4, .006, 14), ("Wheel", 4, .01, 21)],
        "Grip Module": [("Handle Grip", 2, .02, 14), ("Hardware Kit", 1, .004, 14)],
        "Pack Module": [("Shipping Carton", 1, .02, 14)]}),
    "O'Brien Men's Neoprene Life Vest": ("VEST", "Neoprene Life Vest", {
        "Shell Module": [("Neoprene Shell", 1, .12, 28), ("Foam Panel", 4, .015, 21), ("Zipper", 1, .01, 21)],
        "Strap Module": [("Buckle", 3, .006, 14), ("Webbing", 1, .01, 14), ("Safety Label", 1, .002, 14)],
        "Pack Module": [("Poly Bag", 1, .003, 14)]}),
}
POLICIES = {
    "Optimized": {"capacity_factor": 1.0, "pull_in_days": 0, "conversion_factor": 1.0, "exclude_low_confidence": False},
    "Cash Preserving": {"capacity_factor": 0.85, "pull_in_days": 0, "conversion_factor": 0.92, "exclude_low_confidence": False},
    "Grey Swan": {"capacity_factor": 1.0, "pull_in_days": 0, "conversion_factor": 1.0, "exclude_low_confidence": True},
    "Max": {"capacity_factor": 1.4, "pull_in_days": 30, "conversion_factor": 1.18, "exclude_low_confidence": False},
}
INITIAL_POLICY = {"BIKE": "Optimized", "SAFE": "Optimized", "KAYAK": "Optimized", "RIP": "Cash Preserving", "VEST": "Grey Swan"}
SEGMENT_PRIORITY = {"Corporate": 3, "Home Office": 2, "Consumer": 1}

# Shared parts are drawn from one pool by every line that uses them.
#   name: (unit cost, lead days, supplier, coverage of horizon demand, on-hand share)
# Coverage below 1 or a disruption makes the pool scarce, so the lines compete for it.
VARIANTS = {
    "independent": {
        "replace": {}, "add": {},
        "shared": {"Shipping Carton": None, "Hardware Kit": None},     # shared but plentiful
        "disrupted": {("BIKE", "Aluminum Frame"), ("BIKE", "Rear Derailleur"), ("SAFE", "Combination Lock")},
        "flex": None,
    },
    "coupled": {
        # One steel sheet replaces the safe's panels and the trainer's rail; one foam
        # sheet and one buckle serve the vest and the kayak's outfitting.
        "replace": {("SAFE", "Steel Body Panel"): ("Cold-rolled Steel Sheet", 6), ("SAFE", "Door Panel"): ("Cold-rolled Steel Sheet", 2),
                    ("RIP", "Steel Rail"): ("Cold-rolled Steel Sheet", 1),
                    ("VEST", "Foam Panel"): ("Closed-cell Foam Sheet", 4), ("VEST", "Buckle"): ("Side-release Buckle", 3)},
        "add": {("KAYAK", "Outfit Module"): [("Closed-cell Foam Sheet", 2), ("Side-release Buckle", 2)]},
        "shared": {"Cold-rolled Steel Sheet": (9.5, 35, "Summit Metals", 0.95, 0.04),
                   "Closed-cell Foam Sheet": (2.4, 21, "Coastal Plastics", 0.98, 0.08),
                   "Side-release Buckle": (0.3, 14, "Northwind Components", 1.0, 0.06),
                   "Shipping Carton": (2.0, 14, "Coastal Plastics", 0.98, 0.06),
                   "Hardware Kit": (1.2, 14, "Northwind Components", 0.98, 0.06)},
        "disrupted": {("BIKE", "Aluminum Frame"), ("BIKE", "Rear Derailleur"), ("SAFE", "Combination Lock"),
                      (None, "Cold-rolled Steel Sheet")},
        # Plant B's flex line can build bikes and kayaks; contract work already holds some of it.
        "flex": {"resource": "FLEX line", "lines": ("BIKE", "KAYAK"), "booked": [(0, 21), (49, 63)]},
    },
}
REWORK = {("BIKE", "Rear Derailleur"): "Returned Derailleur"}        # refurbish returned parts
QUALITY_HOLD = ("SAFE", 14, 56)                                      # fire-rating retest blocks the line (days)

# Business-key references, materialized as links.  (source type, property, target type, link name)
# Link names are unique: a query resolves a link by name and direction.
LINKS = [
    ("CustomerOrder", "item", "ItemMaster", "ORDERS"),
    ("CustomerOrder", "product_line", "ProductLine", "FOR_PRODUCT_LINE"),
    ("BOMLine", "parent_item", "ItemMaster", "PARENT_ITEM"),
    ("BOMLine", "component_item", "ItemMaster", "COMPONENT_ITEM"),
    ("InventoryLot", "item", "ItemMaster", "STOCK_OF"),
    ("SupplyCommitment", "item", "ItemMaster", "SUPPLIES"),
    ("SupplyOption", "item", "ItemMaster", "CAN_SUPPLY"),
    ("Reservation", "demand_id", "CustomerOrder", "RESERVED_FOR"),
    ("ItemMaster", "product_line", "ProductLine", "PART_OF_LINE"),
    ("ProductLine", "policy", "PlanningPolicy", "USES_POLICY"),
]


def _day(value: date) -> int:
    return (value - PLANNING_DATE).days


def build(csv_path, variant: str = "coupled") -> dict:
    import pandas as pd

    config = VARIANTS[variant]
    shared = config["shared"]
    disrupted = config["disrupted"]
    columns = ["Product Name", "Product Price", "Order Item Quantity", "order date (DateOrders)", "Market",
               "Days for shipment (scheduled)", "Order Status", "Customer Segment"]
    frame = pd.read_csv(csv_path, encoding="latin-1", usecols=columns)
    frame = frame[frame["Product Name"].isin(PRODUCTS) & ~frame["Order Status"].isin(["CANCELED", "SUSPECTED_FRAUD"])].copy()
    frame["due"] = pd.to_datetime(frame["order date (DateOrders)"]).dt.normalize() + pd.to_timedelta(frame["Days for shipment (scheduled)"], unit="D")
    end = PLANNING_DATE + timedelta(weeks=HORIZON_WEEKS)
    frame = frame[(frame["due"].dt.date >= PLANNING_DATE) & (frame["due"].dt.date < end)]
    frame["month"] = frame["due"].dt.to_period("M")
    # One demand event = one product, one market, one month of real orders.
    grouped = frame.groupby(["Product Name", "Market", "month"]).agg(
        quantity=("Order Item Quantity", "sum"), due=("due", "max"), price=("Product Price", "first"),
        orders=("Order Item Quantity", "size"), segment=("Customer Segment", lambda s: s.mode().iloc[0]))
    rng = random.Random(SEED)
    lines, items, boms, demands, inventory, commitments, options = [], [], [], [], [], [], []
    weekly = frame.groupby("Product Name")["Order Item Quantity"].sum() / HORIZON_WEEKS
    for product, (code, label, modules) in PRODUCTS.items():
        price = float(frame.loc[frame["Product Name"] == product, "Product Price"].iloc[0])
        rate = round(float(weekly[product]) * 1.15, 1)                 # lines are planned 15% above average demand
        lines.append({"id": code, "name": label, "source_product": product, "policy": INITIAL_POLICY[code], "unit_price": round(price, 2),
                      "weekly_rate": rate, "conversion_cost": round(price * 0.12, 2), "resource": f"{code} line"})
        top = f"{code} Assembly"
        items.append({"id": top, "kind": "assembly", "product_line": code, "unit_cost": 0})
        for module, parts in modules.items():
            module_id = f"{code}:{module}"
            items.append({"id": module_id, "kind": "module", "product_line": code, "unit_cost": 0})
            boms.append({"parent_item": top, "component_item": module_id, "quantity_per": 1})
            merged = defaultdict(int)
            specs = {}
            for name, qty, share, lead in parts:
                name, qty = config["replace"].get((code, name), (name, qty))
                merged[name] += qty
                specs.setdefault(name, (share, lead))
            for name, qty in config["add"].get((code, module), []):
                merged[name] += qty
                specs.setdefault(name, (0, 0))
            for name, qty in merged.items():
                pid = name if name in shared else f"{code}:{name}"
                boms.append({"parent_item": module_id, "component_item": pid, "quantity_per": qty})
                if any(row["id"] == pid for row in items):
                    continue
                share, lead = specs[name]
                spec = shared.get(name)
                unit_cost = spec[0] if spec else round(price * share, 2)
                items.append({"id": pid, "kind": "part", "name": name, "product_line": None if name in shared else code,
                              "unit_cost": unit_cost, "lead_time_days": spec[1] if spec else lead,
                              "critical": ((None if name in shared else code), name) in disrupted})
    flex = config["flex"]
    for (product, market, month), row in grouped.iterrows():
        code = PRODUCTS[product][0]
        line = next(item for item in lines if item["id"] == code)
        demand = {"id": f"DE-{code}-{market[:3].upper()}-{month.strftime('%y%m')}", "item": f"{code} Assembly", "product_line": code,
                  "customer": market, "quantity": int(row["quantity"]), "due_at": _day(row["due"].date()),
                  "priority": SEGMENT_PRIORITY.get(row["segment"], 1), "unit_revenue": round(float(row["price"]), 2),
                  "processing_days": round(int(row["quantity"]) / line["weekly_rate"] * 7, 2), "resource": f"{code} line",
                  "source_orders": int(row["orders"])}
        if flex and code in flex["lines"]:
            demand["alternate_resources"] = [flex["resource"]]
        demands.append(demand)
    demands.sort(key=lambda row: (row["due_at"], row["id"]))

    child = defaultdict(list)
    for row in boms:
        child[row["parent_item"]].append((row["component_item"], row["quantity_per"]))

    def leaves(item, qty):
        if item not in child:
            yield item, qty
            return
        for comp, per in child[item]:
            yield from leaves(comp, qty * per)

    need = defaultdict(float)
    for demand in demands:
        for pid, qty in leaves(demand["item"], demand["quantity"]):
            need[pid] += qty
    cost = {row["id"]: row for row in items}
    for pid, total in sorted(need.items()):
        code, name = pid.split(":", 1) if ":" in pid else (None, pid)
        is_disrupted = (code, name) in disrupted
        spec = shared.get(name) if code is None else None
        if spec:
            cover, onhand = spec[3], int(total * spec[4])
            if is_disrupted:
                cover = min(cover, 0.92)
        else:
            cover = 0.92 if is_disrupted else rng.uniform(1.05, 1.2)
            onhand = int(total * (0.03 if is_disrupted else rng.uniform(0.08, 0.16)))
        for index, site in enumerate(SITES):
            inventory.append({"id": f"LOT-{pid}-{site}", "item": pid, "location": site, "quantity": onhand // 2 if index == 0 else onhand - onhand // 2})
        remaining, pos = max(0, int(total * cover) - onhand), rng.randrange(10, 16)
        for po in range(pos):
            arrive = 7 + po * (HORIZON_WEEKS * 7 - 21) // pos + rng.randrange(0, 5)
            late = is_disrupted and arrive < 16 * 7      # the disruption hits the next ~16 weeks of deliveries
            if spec:
                supplier = spec[2]
            else:
                supplier = "Summit Metals" if is_disrupted else rng.choice(SUPPLIERS)
            row = {"id": f"PO-{len(commitments) + 1:05d}", "item": pid, "quantity": max(1, remaining // pos),
                   "supplier": supplier, "available_at": arrive + (35 if late else 0), "status": "active",
                   "unit_cost": cost[pid]["unit_cost"], "confidence": 0.6 if late else 0.95}
            if late:
                row.update(expedite_available_at=arrive, expedite_unit_premium=round(cost[pid]["unit_cost"] * 0.3, 2))
            commitments.append(row)
        if (code, name) in REWORK:
            donor = f"{code}:{REWORK[(code, name)]}"
            items.append({"id": donor, "kind": "part", "name": REWORK[(code, name)], "product_line": code, "unit_cost": 0, "lead_time_days": 0})
            inventory.append({"id": f"LOT-{donor}-returns", "item": donor, "location": SITES[0], "quantity": int(total * 0.15)})
            options.append({"id": f"RW-{pid}", "supplier": "In-house rework", "item": pid, "quantity": int(total * 0.15), "lead_time": 10,
                            "unit_cost": round(cost[pid]["unit_cost"] * 0.35, 2), "qualified": True, "consumes_item": donor})
    hold_line, hold_start, hold_end = QUALITY_HOLD
    fixed_tasks = [{"id": f"HOLD-{hold_line}-RETEST", "resource": f"{hold_line} line", "start": hold_start, "finish": hold_end}]
    if flex:
        fixed_tasks += [{"id": f"BOOKED-FLEX-{index + 1}", "resource": flex["resource"], "start": start, "finish": finish}
                        for index, (start, finish) in enumerate(flex["booked"])]
    notional = "BOM, stock, POs, capacity, supplier disruption, quality hold"
    if variant == "coupled":
        notional = "BOM with shared materials, stock, POs, line and flex capacity, supplier disruptions, quality hold"
    return {"scenario_time": f"{PLANNING_DATE.isoformat()}T00:00:00Z", "horizon_weeks": HORIZON_WEEKS,
            "quarter_start": _day(QUARTER[0]), "quarter_end": _day(QUARTER[1]),
            "product_lines": lines, "policy_definitions": [{"id": key, **value} for key, value in POLICIES.items()],
            "items": items, "demands": demands, "boms": boms, "inventory": inventory, "reservations": [],
            "supply_commitments": commitments, "supply_options": options, "fixed_tasks": fixed_tasks,
            "provenance": {"real": f"DataCo Smart Supply Chain (doi:10.17632/8gx2fvg2k6.5, CC BY 4.0), sha256 {SOURCE_SHA256}",
                           "notional": f"{notional} (fixed rules, seed {SEED})"}}


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8", newline="\n")


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _links(nodes: list[dict]) -> list[dict]:
    by_key = {}
    for node in nodes:
        key = node["properties"].get("code", node["id"])
        by_key[(node["entity_type"], key)] = node["id"]
        by_key[(node["entity_type"], node["id"])] = node["id"]
    links, missing = [], 0
    for source_type, prop, target_type, name in LINKS:
        for node in nodes:
            if node["entity_type"] != source_type or node["properties"].get(prop) in (None, ""):
                continue
            target = by_key.get((target_type, node["properties"][prop]))
            if target is None:
                missing += 1
                continue
            links.append({"type": name, "source": node["id"], "target": target})
    if missing:
        raise SystemExit(f"{missing} references do not resolve to an object")
    return links


def write_pack(fixture: dict, folder: Path) -> dict:
    """Write ontology, objects, links and MANIFEST; study.json and app.json are kept as they are."""
    nodes = fixture_objects(fixture, id_prefix="", input_types=PLANNING_INPUT_TYPES)
    links = _links(nodes)
    folder.mkdir(parents=True, exist_ok=True)
    _write_json(folder / "ontology.json", {
        "name": "DataCo Quarterly Planning",
        "domain": "Manufacturing",
        "description": "Quarterly revenue, demand risk, material coverage and recovery actions for five product lines.",
        "object_types": [{"api_name": name, "key_property": "code" if name in CODED_TYPES else None,
                          "properties": [{"id": key, "type": kind} for key, kind in props.items()]}
                         for name, props in OBJECT_TYPES.items()],
        "link_types": [{"api_name": name, "source": source, "target": target, "via": prop} for source, prop, target, name in LINKS],
    })
    _write_jsonl(folder / "objects.jsonl", [{"id": n["id"], "type": n["entity_type"], "properties": n["properties"]} for n in nodes])
    _write_jsonl(folder / "links.jsonl", links)
    files = {}
    for path in sorted(folder.iterdir()):
        if path.name != "MANIFEST.json":
            files[path.name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
    _write_json(folder / "MANIFEST.json", {
        "case": "dataco_mrp", "objects": len(nodes), "links": len(links),
        "sources": {"demand": fixture["provenance"]["real"], "supply": fixture["provenance"]["notional"]},
        "license": "Demand rows: CC BY 4.0 (DataCo Smart Supply Chain). Rule-generated supply: same terms as this repository.",
        "pack_version": 1, "exported": date.today().isoformat(), "files": files})
    return {"objects": len(nodes), "links": len(links)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="coupled")
    parser.add_argument("--out", type=Path, default=BACKEND.parent / "demo_cases" / "dataco_mrp")
    args = parser.parse_args()
    digest = hashlib.sha256(args.csv.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise SystemExit(f"unexpected source checksum {digest}")
    print(write_pack(build(args.csv, args.variant), args.out))


if __name__ == "__main__":
    main()
