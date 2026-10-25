import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
CASES = BACKEND.parent / "demo_cases"


def pack_inputs(case: str = "dataco_mrp") -> dict:
    """Planning inputs rebuilt from a pack alone, the way the study's object queries read them."""
    from app.services.v2.material_shortage_objects import PLANNING_INPUT_TYPES

    folder = CASES / case
    objects = [json.loads(line) for line in (folder / "objects.jsonl").read_text(encoding="utf-8").splitlines()]
    study = json.loads((folder / "study.json").read_text(encoding="utf-8"))
    inputs = {p["key"]: p["default"] for p in study["spec"]["parameters"]}
    for key, kind in PLANNING_INPUT_TYPES.items():
        inputs[key] = [{"id": o["id"], **o["properties"]} for o in objects if o["type"] == kind]
    return inputs


@pytest.fixture(scope="session")
def dataco_inputs() -> dict:
    return pack_inputs()


@pytest.fixture(scope="session")
def dataco_plan(dataco_inputs) -> dict:
    from app.services.v2.mrp_planning import plan_portfolio

    return plan_portfolio(dataco_inputs)
