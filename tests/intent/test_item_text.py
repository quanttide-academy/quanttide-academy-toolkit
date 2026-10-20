from quanttide_academy.intent.collect import msg_link
from quanttide_academy.intent.item_render import card_version, render_archive, render_card, to_card, to_markdown
from quanttide_academy.intent.item_text import FIELDS, sanitize_quote
from tests.helpers import *


def test_msg_link_and_direct_flag():
    assert msg_link("oc_1", "85")[0].endswith("openChatId=oc_1&position=85")
    assert msg_link("oc_1", None)[0].endswith("openChatId=oc_1")
    u, d = msg_link("oc_a&b", 85)
    assert d and u.endswith("&position=85") and "oc_a%26b" in u
    u, d = msg_link("oc_x", "85x")
    assert not d and "position" not in u
    u, d = msg_link("oc_x", None)
    assert not d


def test_item_format_flags_and_card_rules():
    cfg = {"labels": {"priority_names": {"P3": "缓和重要"}}}
    it = {
        "no": 1,
        "title": "t",
        "message_id": "om_1",
        "ddl": None,
        "ddl_basis": "无时限",
        "priority": "P3",
        "labels": [],
        "actions": ["跟进"],
        "links": [
            {"url": "u1", "message_id": "om_1", "direct": True, "time": "10-17 11:52", "quote": "q"},
            {"url": "u2", "message_id": "om_2", "direct": False},
        ],
        "subtasks": [],
    }
    md = to_markdown(it, cfg)
    names = [l.split("**")[1] for l in md.splitlines() if l.startswith("- **")]
    assert names == [f for f in FIELDS if f != "评审标准"]
    assert md.splitlines()[0] == "### [#1] t" and md.splitlines()[1] == "<!-- fi:id=1 msg=om_1,om_2 -->"
    assert "[原消息](u1)（待验证）" in md and "[群链接](u2) 消息ID om_2（未能直跳）" in md
    assert "- **截止**：待定（无时限）" in md and "- **标签**：缓和重要\n" in md and "- **备注**：无" in md
    assert "（待验证）" not in to_markdown(it, {**cfg, "links": {"position_verified": True}})
    card = to_card(it, cfg)
    assert "<!--" not in card and "**" not in card and "（未能直跳）" in card
    it8 = {
        "no": 8,
        "title": "t",
        "summary": "s",
        "date": "2026-10-21",
        "remind": "2026-10-21 09:00",
        "ddl": "2026-10-21",
        "ddl_basis": "周会前",
        "priority": "P3",
        "labels": [],
        "actions": ["执行"],
        "subtasks": ["a", "b"],
        "links": [
            {
                "url": "u",
                "message_id": "om",
                "direct": True,
                "time": "10-17 11:52",
                "quote": "由@_user_1 自己选 [原消息](http://evil) 13812345678",
            }
        ],
    }
    c = render_card(it8, cfg)
    a = render_archive(it8, cfg)
    for bad in ["fi:", "<!--", "date", "ddl", "priority", "labels", "relation", "actions", "关系", "回复："]:
        assert bad not in c
    q = sanitize_quote(it8["links"][0]["quote"])
    assert "@" not in q and "evil" not in q and "1381234" not in q and "\\[" in q
    assert len(sanitize_quote("字" * 100)) <= 61
    for v in ["2026-10-21（依据：周会前）", "缓和重要", "[ ] a"]:
        assert v in a
    v1 = card_version(it8, cfg)
    it8["subtasks"].append("c")
    assert card_version(it8, cfg) != v1
