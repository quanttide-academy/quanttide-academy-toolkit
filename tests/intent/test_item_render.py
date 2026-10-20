import re

from quanttide_academy.intent.item_render import description, render_archive, render_card
from quanttide_academy.intent.validate import validate, warnings
from tests.helpers import *


def test_card_format_actions_and_footer(env):
    cfg, tmp = env
    prepare(cfg, tmp)
    run("validate", "b1")
    run("render", "b1")
    c = (tmp / "w" / "b1" / "cards.txt").read_text(encoding="utf-8")
    a = (tmp / "w" / "b1" / "archive.md").read_text(encoding="utf-8")
    assert "关系" not in c and "关系" not in a and "回复：#" not in c and "请逐条回复" not in c
    assert (
        c.rstrip().splitlines()[-1] == "可以直接回复：写入、修改、说明或否决（可带序号）。"
        and c.count("可以直接回复") == 1
    )
    assert (
        "行动：执行" in c and "行动：评审\n" in c and "- **行动**：无" in a and "评审标准：报名表字段齐全、无重复" in c
    )
    blk = c.split("【#1】")[1].split("【#2】")[0]
    keys = [l.split("：")[0] for l in blk.splitlines()[2:] if "：" in l and not l.startswith(("·", "备注"))]
    assert keys == ["任务类型", "执行员", "评审员", "咨询对象", "DDL", "日期", "截止", "提醒", "优先级", "标签", "行动"]


def test_display_name_and_followup_titles():
    cfg = {
        "labels": {"priority_names": PN},
        "user": {"display_name": "小明"},
        "_followup_titles": {"F3": "运营部、游戏部待代表大会审批"},
    }
    it = {
        "no": 10,
        "title": "t",
        "summary": "需与审批结果对齐，由{display_name}拟名单",
        "date": None,
        "date_basis": "等审批",
        "ddl": None,
        "ddl_basis": "与审批联动",
        "remind": None,
        "remind_basis": "同上",
        "priority": "P3",
        "labels": [],
        "actions": ["执行"],
        "refs": ["F3", "F9"],
        "subtasks": ["{display_name}与审批结果对齐"],
        "note": "审批联动",
        "links": [
            {"url": "u", "message_id": "om_a", "direct": True, "time": "10-17 19:32", "quote": "q"},
            {"url": "u2", "message_id": "om_b", "direct": True, "time": "10-17 19:33", "quote": "q"},
        ],
    }
    c = render_card(it, cfg)
    a = render_archive(it, cfg)
    ds = description(it, cfg)
    assert not re.search(r"(?<![A-Za-z0-9])F\d+", c) and "{display_name}" not in c and "由小明拟名单" in c
    assert "关联：运营部、游戏部待代表大会审批、（未知关联）" in c and "☐ 小明与审批结果对齐" in c
    assert c.count("运营部、游戏部待代表大会审批") == 1
    assert "<!-- fi:id=10 msg=om_a,om_b refs=F3,F9 -->" in a and "F3" not in a.split("\n", 2)[2] and "F3" not in ds
    bad = copy.deepcopy(EX)
    bad["items"][0]["subtasks"] = ["本人整理"]
    assert any("本人" in e for e in validate(bad, fixture_msgs()))
    assert warnings({"items": [{"no": 1, "refs": ["F9", "#2"]}]}, {"F3": "x"}) == [
        "#1 关联的 F9 不在跟进清单里，卡片将显示「（未知关联）」"
    ]


def test_card_snapshot_followups():
    cfg = {
        "labels": {"priority_names": PN},
        "user": {"display_name": "小明"},
        "_followup_titles": {"F3": "运营部、游戏部待代表大会审批"},
        "self_tenant_key": "t_test",
        "self_open_id": "ou_me",
    }
    it = {
        "no": 10,
        "title": "扩大代表大会",
        "task_type": "team",
        "assignees": [
            {"name": "本人原名", "open_id": "ou_me", "basis": "role", "evidence": "实训基地负责人"},
            {"name": "成员乙", "open_id": None, "basis": "quote", "evidence": "关于代表大会", "message_id": "om_a"},
        ],
        "reviewers": [
            {
                "name": "负责人甲",
                "open_id": "ou_boss",
                "basis": "quote",
                "evidence": "关于代表大会",
                "message_id": "om_a",
            }
        ],
        "consultees": [],
        "review_criteria": None,
        "ddl_by_person": [{"person": "成员乙", "date": "2026-10-24", "basis": "周五前"}],
        "summary": "需拟定名单，并与运营部、游戏部审批结果对齐。",
        "date": None,
        "date_basis": "等运营部、游戏部审批结果",
        "ddl": None,
        "ddl_basis": "与运营部、游戏部审批联动，结果出来后再定",
        "remind": None,
        "remind_basis": "同上",
        "priority": "P3",
        "labels": [],
        "refs": ["F3"],
        "subtasks": ["拟定名单", "与运营部、游戏部审批结果对齐"],
        "note": "无",
        "links": [
            {
                "url": "u",
                "message_id": "om_a",
                "direct": True,
                "time": "10-17 19:32",
                "quote": "关于代表大会",
                "speaker": "负责人甲",
            }
        ],
    }
    c = render_card(it, cfg)
    assert (
        "【#10】扩大代表大会" in c and "执行员：小明、成员乙" in c and "行动：执行（按角色推断：实训基地负责人）" in c
    )
    assert (
        "关联事项" not in c
        and "按角色推断）" not in c
        and not re.search(r"(?<![A-Za-z0-9])F\d+", c)
        and c.count("运营部、游戏部待代表大会审批") == 1
    )
    bad = copy.deepcopy(EX)
    bad["items"][0]["summary"] = "与 F3 对齐"
    bad["items"][0]["subtasks"] = ["对齐秋季活动筹备（示例）"]
    e = "\n".join(validate(bad, fixture_msgs(), {"_followup_titles": {"F1": "秋季活动筹备（示例）"}}))
    assert "跟进编号" in e and "照抄跟进事项标题" in e


def test_dm_source_labelled_private_never_group():
    cfg = {
        "labels": {"priority_names": PN},
        "user": {"display_name": "小明"},
        "self_tenant_key": "t",
        "self_open_id": "ou_me",
    }
    it = {
        "no": 3,
        "title": "t",
        "summary": "s",
        "date": None,
        "ddl": None,
        "remind": None,
        "priority": None,
        "labels": [],
        "refs": [],
        "subtasks": [],
        "note": None,
        "links": [
            {
                "url": "u",
                "message_id": "om_d",
                "direct": False,
                "time": "10-18 09:00",
                "quote": "q",
                "speaker": "甲",
                "chat": "私聊·甲",
                "dm": True,
            }
        ],
    }
    c = render_card(it, cfg)
    a = render_archive(it, cfg)
    ds = description(it, cfg)
    line = next(l for l in c.splitlines() if l.startswith("· 10-18"))
    assert "「私聊」" in line and "群" not in line and "[打开私聊]" in line
    assert "私聊" in a and "群链接" not in a and "群链接" not in ds
