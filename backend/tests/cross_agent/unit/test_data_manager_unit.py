import anyio

from db import get_idea, get_plan
def test_data_manager_loads_real_refine_plan_fixture(test_data_manager):
    sample = test_data_manager.load_refine_plan_sample("real_refine_plan_sample")
    assert sample["ideaId"]
    assert sample["planId"]
    assert isinstance((sample.get("idea") or {}).get("refined_idea"), str)
    assert isinstance((sample.get("plan") or {}).get("tasks"), list)


def test_data_manager_can_seed_refine_plan_into_db(test_data_manager):
    seeded = anyio.run(test_data_manager.seed_refine_plan_sample, "real_refine_plan_sample")
    idea_id = seeded["ideaId"]
    plan_id = seeded["planId"]

    stored_idea = anyio.run(get_idea, idea_id)
    stored_plan = anyio.run(get_plan, idea_id, plan_id)

    assert isinstance(stored_idea, dict)
    assert isinstance(stored_plan, dict)
    assert (stored_idea.get("refined_idea") or "").strip()
    assert isinstance(stored_plan.get("tasks"), list)
    assert len(stored_plan["tasks"]) >= 5
