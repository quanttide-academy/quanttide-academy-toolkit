import copy

import pytest

from quanttide_academy.org import conf as C
from quanttide_academy.org import plan as P
from quanttide_academy.org import read as R
from tests.org.helpers import Fake, cfg

BIG = {
    "oc_a": {
        "name": "技术部群",
        "owner": "ou_me",
        "members": {
            "ou_me": "t",
            "ou_a1": "t",
            "ou_a2": "t",
            "ou_a3": "t",
            "ou_a4": "t",
            "ou_old": "t",
            "ou_ext": "t_other",
            "ou_k1": "t",
            "ou_k2": "t",
            "ou_k3": "t",
        },
    }
}


def fake_big(**kw):
    f = Fake(**kw)
    f.data["chats"].update(copy.deepcopy(BIG))
    f.data["members"]["od_a"] += ["ou_k1", "ou_k2", "ou_k3"]
    return f


def test_plan_deterministic_removals_first():
    f = fake_big()
    a = P.compute(cfg(), f)
    b = P.compute(cfg(), fake_big())
    assert a == b and a["plan_id"] == P.plan_id(a["items"])
    assert [(x["kind"], x["person"]) for x in a["items"]] == [("remove_member", "ou_ext"), ("remove_member", "ou_old")]
    assert a["items"][0]["external"] is True and all(x["idx"] == i for i, x in enumerate(a["items"], 1))
    t = P.render(a)
    assert t.index("🔴 移出群") < t.index("1. 群") and "{person:ou_ext}" in t


def test_adds_rename_and_subdepartments():
    f = fake_big()
    f.data["chats"]["oc_a"]["members"].pop("ou_a4")
    p = P.compute(cfg(mappings=[{"chat_id": "oc_a", "department": "od_a", "name": "技术部大群"}]), f)
    ks = [(x["kind"], x.get("person") or x.get("name")) for x in p["items"]]
    assert ("add_member", "ou_a4") in ks and ("rename", "技术部大群") in ks  # 子部门成员也算


def test_remove_ratio_circuit_breaker():
    with pytest.raises(P.PlanRefused, match="30%"):
        P.compute(cfg(), Fake())  # 夹具里 oc_a 要移出 6/10


def test_protected_never_removed_and_invariant_refuses(monkeypatch):
    for c, who in [(cfg(), "ou_me"), (cfg(protected=["ou_ext"]), "ou_ext"), (cfg(app_open_id="ou_old"), "ou_old")]:
        p = P.compute(c, fake_big())
        assert who not in {x["person"] for x in p["items"]} and p["groups"][0]["protected_kept"] >= 1
    f = fake_big()
    f.data["chats"]["oc_a"]["owner"] = "ou_old"
    assert "ou_old" not in {x["person"] for x in P.compute(cfg(), f)["items"]}  # 群主


def test_dept_read_failure_is_error_never_empty():
    with pytest.raises(R.DeptReadError):
        P.compute(cfg(), fake_big(fail_dept=True))
    f = fake_big()
    f.data["tree"] = []
    with pytest.raises(R.DeptReadError):
        P.compute(cfg(), f)


def test_mapping_and_scope_validation_ids_only():
    with pytest.raises(C.BadOrgConfig, match="allowed_departments"):
        P.compute(cfg(mappings=[{"chat_id": "oc_a", "department": "od_x"}]), fake_big())
    with pytest.raises(C.BadOrgConfig, match="收窄"):
        P.compute(cfg(allowed_departments=["od_x"]), fake_big())
    with pytest.raises(C.BadOrgConfig, match="不在部门树"):
        P.compute(cfg(allowed_departments=["od_none"]), fake_big())
    with pytest.raises(C.BadOrgConfig, match="不在部门树"):
        P.compute(cfg(mappings=[{"chat_id": "oc_a", "department": "od_none"}]), fake_big())
    with pytest.raises(C.BadOrgConfig, match="不在部门树"):
        P.compute(cfg(mappings=[{"chat_id": "oc_a", "department": "技术部"}]), fake_big())  # 名字不再匹配
    with pytest.raises(C.BadOrgConfig, match="root_department"):
        P.compute(cfg(root_department="实训基地"), fake_big())
    with pytest.raises(C.BadOrgConfig, match="root_department"):
        P.compute(cfg(root_department=None), fake_big())


def test_hold_lists_diff_with_reason_without_items():
    m = [
        {"chat_id": "oc_a", "department": "od_a"},
        {"chat_id": "oc_f", "department": "od_f", "hold": True, "hold_reason": "等组织调整"},
    ]
    p = P.compute(cfg(mappings=m), fake_big())
    assert all(x["chat_id"] != "oc_f" for x in p["items"]) and {(x["kind"], x["person"]) for x in p["held"]} == {
        ("remove_member", "ou_zz"),
        ("add_member", "ou_f2"),
    }
    t = P.render(p)
    assert "暂缓，仅展示" in t and "等组织调整" in t and "本人确认" in t and p["held_groups"] == 1
    f = fake_big()
    f.data["chats"]["oc_f"]["members"].update({"ou_f9": "t", "ou_f8": "t"})
    f.data["members"]["od_f"] += ["ou_f9", "ou_f8"]
    q = P.compute(cfg(mappings=[m[0], {"chat_id": "oc_f", "department": "od_f"}]), f)
    assert any(x["chat_id"] == "oc_f" for x in q["items"])  # 取消暂缓才生成条目


def test_batch_cap_defers_rest():
    p = P.compute(cfg(max_items=1), fake_big())
    assert len(p["items"]) == 1 and p["deferred"] == 1 and "超出本批上限" in P.render(p)
