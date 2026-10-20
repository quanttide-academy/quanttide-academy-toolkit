from feishu_workflows.intent import flow_reply
from tests.helpers import *


def test_flow_reply_reexports():
    for name in (
        "LIST",
        "NUM",
        "_lookup",
        "_nums",
        "assign",
        "handle_reply",
        "parse_reply",
        "pending_cards",
        "promote",
    ):
        assert hasattr(flow_reply, name), name


def test_other_assignee_card_and_info_list(env):
    """v3：执行员是别人且用户无原话角色 → 出卡、行动「指派」、用户为审批人；纯资讯进仅知悉，只给标题和来源群。"""
    cfg, tmp = env
    t = copy.deepcopy(EX)
    t["items"][1]["reviewers"] = []
    prepare(cfg, tmp, topics=t)
    run("validate", "b1")
    _rc, r = run("render", "b1")
    cards = (tmp / "w" / "b1" / "cards.txt").read_text(encoding="utf-8")
    blk = cards.split("【#2】")[1].split("【#3】")[0]
    assert (
        "行动：指派（按规则：执行员是别人）" in blk
        and "审批人：示例用户（按规则：执行员是别人）" in blk
        and "执行员：小李" in blk
    )
    assert "纯资讯 1 条，待你指派 1 条。" in cards and r["info"] == 1 and r["to_assign"] == 1 and "【#3】" not in cards
    assert (
        next(x for x in cards.splitlines() if x.startswith("· #3 "))
        == "· #3 阅读新出的行业报告（来源：示例群（虚构））"
    )


def test_pending_assignee_task_gets_card(env):
    cfg, tmp = env
    t = copy.deepcopy(EX)
    t["items"][1].update(assignees=[], reviewers=[], consultees=[], ddl_by_person=[], task_type="undetermined")
    prepare(cfg, tmp, topics=t)
    assert run("validate", "b1")[0] == 0
    run("render", "b1")
    blk = (tmp / "w" / "b1" / "cards.txt").read_text(encoding="utf-8").split("【#2】")[1]
    assert "执行员：（办理人待定）" in blk and "行动：指派（按规则：办理人待定）" in blk
