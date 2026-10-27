from quanttide_academy_toolkit.intent import roles
from quanttide_academy_toolkit.intent.item import render_card
from quanttide_academy_toolkit.intent.validate_roles import check
from tests.helpers import *

CFG = {"self_open_id": "ou_me", "user": {"display_name": "小明"}, "labels": {"priority_names": PN}}
ME = {"name": "别名", "open_id": "ou_me", "basis": "role", "evidence": "组长"}
LI = {"name": "小李", "open_id": "ou_li", "basis": "quote", "evidence": "q", "message_id": "m"}


def item(**kw):
    base = {
        "no": 1,
        "title": "t",
        "kind": "task",
        "task_type": "team",
        "assignees": [LI],
        "reviewers": [],
        "consultees": [],
        "ddl_by_person": [],
        "refs": [],
    }
    base.update(kw)
    return base


def test_derive_by_open_id_only():
    assert roles.derive_actions(item(assignees=[LI, ME], reviewers=[ME], consultees=[ME]), CFG) == [
        "执行",
        "评审",
        "问询",
    ]
    assert roles.derive_actions(item(reviewers=[{**ME, "open_id": None, "name": "小明"}]), CFG) == [
        "指派"
    ]  # 同名无 open_id 不是本人 → 按规则审批
    assert roles.derive_actions(item(reviewers=[ME]), {**CFG, "self_open_id": None}) == []


def test_category_and_approver():
    assert roles.category(item(assignees=[]), CFG) == "card" and roles.derive_actions(item(assignees=[]), CFG) == [
        "指派"
    ]
    assert roles.derive_actions(item(assignees=[], reviewers=[ME]), CFG) == ["评审"]  # 有原话角色不叠加审批人
    assert roles.approver(item(), CFG)["basis"] == "rule" and roles.approver(item(reviewers=[ME]), CFG) is None
    assert (
        roles.category(item(kind="info", assignees=[]), CFG) == "info"
        and roles.derive_actions(item(kind="info", assignees=[]), CFG) == []
    )
    assert roles.category(item(kind="info", assignees=[], promoted=True), CFG) == "card"


def test_texts_and_ddl():
    it = item(
        assignees=[ME, LI],
        reviewers=[
            {"name": "甲", "open_id": None, "basis": "role", "evidence": "x"},
            {"name": "乙", "open_id": None, "basis": "role", "evidence": "y"},
        ],
        ddl_by_person=[
            {"person": "别名", "date": "2026-10-22", "basis": "a"},
            {"person": "小李", "date": "2026-10-24", "basis": "b"},
        ],
        ddl="2026-10-30",
    )
    assert (
        roles.assignees_text(it, CFG) == "小明、小李"
        and roles.reviewers_text(it, CFG) == "执行员 -> 甲 -> 乙"
        and roles.consultees_text(it, CFG) == "无"
    )
    assert (
        roles.ddl_lines(it, CFG) == ["小明 2026-10-22（a）", "小李 2026-10-24（b）"]
        and roles.self_ddl(it, CFG) == "2026-10-22"
    )
    assert roles.self_ddl(item(ddl="2026-10-30"), CFG) is None  # 指派卡：本人没有 DDL 就不填
    assert roles.self_ddl(item(assignees=[ME], ddl="2026-10-30"), CFG) == "2026-10-30"
    assert (
        roles.summary_line(it, CFG)
        == "行动：执行（按角色推断：组长） ｜ 任务类型：团队任务 ｜ 执行员：小明、小李 ｜ 评审：执行员 -> 甲 -> 乙 ｜ 咨询：无"
    )
    assert roles.assignees_text(item(assignees=[]), CFG) == "（办理人待定）"


def test_followup_follower_is_reviewer():
    cfg = {
        **CFG,
        "_followup_titles": {"F2": "活动审批"},
        "_followup_followers": {"F2": {"name": "小明", "open_id": "ou_me"}, "F3": {"name": "小明", "open_id": None}},
    }
    it = item(refs=["F2"])
    assert roles.derive_actions(it, cfg) == ["评审"] and roles.actions_text(it, cfg) == "评审（跟进清单：活动审批）"
    assert roles.reviewers_text(it, cfg) == "执行员 -> 小明"
    assert roles.derive_actions(item(refs=["F3"]), cfg) == ["指派"]  # 跟进人没有 open_id，不判为本人


def test_task_type_undetermined():
    it = item(task_type="undetermined", assignees=[])
    C = {**CFG, "user": {"display_name": "小明", "roles": ["组长"]}}
    assert (
        check(it, "#1", None, {}, C) == []
        and check(item(task_type="undetermined", assignees=[ME]), "#1", None, {}, C) == []
    )
    assert any("undetermined" in e for e in check(item(task_type="其他", assignees=[ME]), "#1", None, {}, C))
    c = render_card({**it, "summary": "s", "links": [], "subtasks": []}, CFG)
    assert "任务类型：（待定）" in c
