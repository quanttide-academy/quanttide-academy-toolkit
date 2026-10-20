from quanttide_academy.intent.outputs.todoist import PartialWrite, TodoistAdapter
from tests.helpers import *


def test_todoist_resume_no_duplicates(tmp_path, monkeypatch):
    cfg = {"paths": {"data_dir": str(tmp_path)}, "labels": {"priority_names": PN}}
    monkeypatch.setenv("FI_TOK", "x")
    a = TodoistAdapter({"provider": "todoist", "token_env": "FI_TOK"}, cfg)
    calls = []
    state = {"fail": True}

    def fake(method, path, data=None):
        if data and "parent_id" in data:
            n = sum(1 for c in calls if "parent_id" in c)
            if n == 1 and state["fail"]:
                state["fail"] = False
                raise OSError("boom")
        calls.append(data)
        return {"id": f"T{len(calls)}"}

    a._req = fake
    item = {
        "no": 1,
        "title": "t",
        "fingerprint": "fp1",
        "priority": "P3",
        "relation": "需执行",
        "subtasks": ["a", "b", "c"],
        "links": [],
    }
    with pytest.raises(PartialWrite):
        a.create(dict(item))
    pid, _ = a.create(dict(item))
    parents = [c for c in calls if "parent_id" not in c]
    subs = [c["content"] for c in calls if "parent_id" in c]
    assert len(parents) == 1 and subs == ["a", "b", "c"] and pid == "T1"
    a.create(dict(item))
    assert len(calls) == 4
