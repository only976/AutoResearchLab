from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FixtureDataManager:
    """Central manager for loading and seeding canonical test data fixtures."""

    def __init__(self, fixtures_root: Path):
        self.fixtures_root = fixtures_root.resolve()

    def fixture_path(self, fixture_name: str) -> Path:
        name = fixture_name if fixture_name.endswith(".json") else f"{fixture_name}.json"
        return self.fixtures_root / name

    def load_json_fixture(self, fixture_name: str) -> dict[str, Any]:
        path = self.fixture_path(fixture_name)
        if not path.exists():
            raise FileNotFoundError(f"Missing fixture file: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def load_refine_plan_sample(self, fixture_name: str = "real_refine_plan_sample") -> dict[str, Any]:
        payload = self.load_json_fixture(fixture_name)
        if not payload.get("ideaId") or not payload.get("planId"):
            raise ValueError(f"Invalid refine/plan fixture: {fixture_name}")
        if not isinstance(payload.get("idea"), dict) or not isinstance(payload.get("plan"), dict):
            raise ValueError(f"Invalid refine/plan fixture payload shape: {fixture_name}")
        return payload

    async def seed_refine_plan_sample(self, fixture_name: str = "real_refine_plan_sample") -> dict[str, Any]:
        from db import save_idea, save_plan

        payload = self.load_refine_plan_sample(fixture_name)
        idea_id = str(payload["ideaId"])
        plan_id = str(payload["planId"])
        idea_data = dict(payload.get("idea") or {})
        plan_data = dict(payload.get("plan") or {})

        await save_idea(idea_data, idea_id)
        await save_plan(plan_data, idea_id, plan_id)

        return {
            "ideaId": idea_id,
            "planId": plan_id,
            "idea": idea_data,
            "plan": plan_data,
        }
