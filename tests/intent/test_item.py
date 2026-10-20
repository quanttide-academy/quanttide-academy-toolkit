from feishu_workflows.intent import item
from feishu_workflows.intent.item import render_card
from tests.helpers import *


def test_item_reexports():
    for name in (
        "FIELDS",
        "card_version",
        "description",
        "esc",
        "labels",
        "person_text",
        "render_archive",
        "render_card",
        "resolve",
        "role_block",
        "sanitize_quote",
        "speaker_text",
        "task_title",
        "to_card",
        "to_markdown",
    ):
        assert hasattr(item, name), name


def test_tenant_set_and_empty_behaviors(env):
    cfg, tmp = env
    it = {
        "no": 1,
        "title": "t",
        "summary": "s",
        "priority": "P2",
        "labels": [],
        "actions": ["执行"],
        "subtasks": [],
        "date": None,
        "date_basis": "x",
        "ddl": None,
        "ddl_basis": "x",
        "remind": None,
        "remind_basis": "x",
        "links": [
            {
                "url": "u1",
                "message_id": "a",
                "direct": True,
                "time": "1",
                "quote": "q1",
                "speaker": "负责人甲",
                "sender_external": False,
            },
            {
                "url": "u2",
                "message_id": "b",
                "direct": True,
                "time": "2",
                "quote": "q2",
                "speaker": "负责人甲",
                "sender_external": True,
            },
        ],
    }
    ev = [
        l
        for l in render_card(it, {"labels": {"priority_names": PN}, "self_tenant_key": "t_mine"}).splitlines()
        if l.startswith("· ")
    ]
    assert "负责人甲：「q1」" in ev[0] and "负责人甲（外部成员）：「q2」" in ev[1]
    ev2 = [
        l
        for l in render_card(it, {"labels": {"priority_names": PN}, "self_tenant_key": ""}).splitlines()
        if l.startswith("· ")
    ]
    assert len(ev2) == 2 and all("负责人甲（外部成员）：" in l for l in ev2)
    c = yaml.safe_load(Path(os.environ["FEISHU_INTENT_CONFIG"]).read_text(encoding="utf-8"))
    c["user"]["display_name"] = "小明"
    Path(os.environ["FEISHU_INTENT_CONFIG"]).write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")
    prepare(cfg, tmp)
    m = json.loads((tmp / "w" / "b1" / "messages.json").read_text(encoding="utf-8"))["messages"]
    assert m[0]["mentions"] == ["ou_demo_self"] and m[0]["mentions_self"] is True and m[1]["mentions_self"] is True
    run("validate", "b1")
    run("render", "b1")
    cards = (tmp / "w" / "b1" / "cards.txt").read_text(encoding="utf-8")
    assert (
        "ou_demo" not in cards
        and "〔我〕" not in cards
        and "请（小明） 把新成员" in cards
        and "请（成员） 负责" in cards
    )


def test_tenant_unset_treats_all_external_and_warns(env):
    cfg, tmp = env
    c = yaml.safe_load(Path(os.environ["FEISHU_INTENT_CONFIG"]).read_text(encoding="utf-8"))
    c.pop("self_tenant_key")
    Path(os.environ["FEISHU_INTENT_CONFIG"]).write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")
    prepare(cfg, tmp)
    rc, r = run("validate", "b1")
    assert rc == 0 and any("self_tenant_key" in w for w in r["warnings"])
    run("render", "b1")
    cards = (tmp / "w" / "b1" / "cards.txt").read_text(encoding="utf-8")
    ev = [l for l in cards.splitlines() if l.startswith("· ") and "「" in l]
    assert ev and all("外部成员" in l for l in ev)


def test_tenant_set_but_message_lacks_tenant_is_external(env):
    _cfg, tmp = env
    m = copy.deepcopy(MSG)
    m["messages"][0]["sender_tenant_key"] = "t_test"
    src = tmp / "m.json"
    src.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    run("fetch", "b1", "--from", str(src))
    (tmp / "w" / "b1" / "topics.json").write_text(json.dumps(EX, ensure_ascii=False), encoding="utf-8")
    w = json.loads((tmp / "w" / "b1" / "messages.json").read_text(encoding="utf-8"))["messages"]
    assert w[0]["sender_tenant_key"] == "t_test" and w[0]["sender_external"] is False
    assert w[1]["sender_tenant_key"] is None and w[1]["sender_external"] is True
    run("validate", "b1")
    run("render", "b1")
    c = (tmp / "w" / "b1" / "cards.txt").read_text(encoding="utf-8")
    ev = [l for l in c.splitlines() if l.startswith("· ") and "「" in l]
    assert any("10-19 10:00" in l and "外部成员" not in l for l in ev)
    assert all("外部成员" in l for l in ev if "10-19 10:00" not in l)
