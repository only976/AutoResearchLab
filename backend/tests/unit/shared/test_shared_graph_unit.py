import pytest

from shared.graph import (
    compute_task_stages,
    get_ancestor_chain,
    get_ancestor_path,
    get_parent_id,
    natural_task_id_key,
)


def test_get_parent_id():
    assert get_parent_id("1_2") == "1"
    assert get_parent_id("1") == "0"


def test_get_ancestor_chain():
    assert get_ancestor_chain("1_2_3") == ["1_2", "1", "0"]


def test_get_ancestor_path():
    assert get_ancestor_path("") == ""
    assert get_ancestor_path("1_2") == "0 → 1 → 1_2"


def test_natural_task_id_key_sorting():
    ids = ["1_2", "1_10", "1_1", "2", "1"]
    assert sorted(ids, key=natural_task_id_key) == ["1", "1_1", "1_2", "1_10", "2"]


def test_compute_task_stages_basic():
    tasks = [
        {"task_id": "1", "dependencies": []},
        {"task_id": "2", "dependencies": ["1"]},
        {"task_id": "3", "dependencies": ["1"]},
        {"task_id": "4", "dependencies": ["2", "3"]},
    ]
    stages = compute_task_stages(tasks)
    assert [[t["task_id"] for t in stage] for stage in stages] == [["1"], ["2", "3"], ["4"]]
    assert [t["stage"] for stage in stages for t in stage] == [1, 2, 2, 3]


def test_compute_task_stages_assigns_ids_when_missing():
    tasks = [{"title": "A"}, {"title": "B"}]
    stages = compute_task_stages(tasks)
    assert len(stages) == 1
    assert [t["task_id"] for t in stages[0]] == ["1", "2"]


def test_compute_task_stages_cycle_raises():
    tasks = [
        {"task_id": "1", "dependencies": ["2"]},
        {"task_id": "2", "dependencies": ["1"]},
    ]
    with pytest.raises(ValueError, match="Circular dependency"):
        compute_task_stages(tasks)


def test_compute_task_stages_reduce_removes_transitive_edges():
    tasks = [
        {"task_id": "1", "dependencies": []},
        {"task_id": "2", "dependencies": ["1"]},
        {"task_id": "3", "dependencies": ["1", "2"]},
    ]
    stages = compute_task_stages(tasks, reduce=True)
    # After transitive reduction, (1 -> 3) is redundant because (1 -> 2 -> 3) exists.
    by_id = {t["task_id"]: t for stage in stages for t in stage}
    assert by_id["2"]["dependencies"] == ["1"]
    assert by_id["3"]["dependencies"] == ["2"]
