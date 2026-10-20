import datetime

from quanttide_academy.core import paths
from quanttide_academy.intent import names
from quanttide_academy.intent.item import labels, render_card
from quanttide_academy.intent.validate import validate
from tests.helpers import *

CFG = {
    "labels": {"priority_names": PN},
    "self_open_id": "ou_demo_self",
    "user": {"display_name": "示例用户", "roles": ["示例负责人"]},
}


def test_validator_ok_and_errors():
    assert validate(EX, fixture_msgs(), CFG) == []
    bad = copy.deepcopy(EX)
    it = bad["items"][0]
    it.update(
        actions=["随便"],
        priority="P5",
        date="2026/10/1",
        remind="2026-10-26",
        written=True,
        url="x",
        labels=["缓和重要"],
    )
    it["refs"] = ["#2"]
    it["refs_reason"] = "感觉相关"
    it["date_basis"] = None
    e = "\n".join(validate(bad, fixture_msgs(), {"labels": {"priority_names": PN}}))
    assert "多出字段 url" in e
    del it["url"]
    e = "\n".join(validate(bad, fixture_msgs(), {"labels": {"priority_names": PN}}))
    for s in ["actions", "priority", "date 必须", "remind 必须", "written", "业务标签", "refs_reason"]:
        assert s in e
    b2 = copy.deepcopy(EX)
    b2["items"][2]["ddl_basis"] = None
    b2["items"][1]["links"][0]["message_id"] = "om_none"
    b2["items"][0]["actions"] = ["评审"]
    e = "\n".join(validate(b2, fixture_msgs(), CFG))
    assert "ddl_basis" in e and "不在 messages.json" in e and "与角色推导结果" in e
    b3 = copy.deepcopy(EX)
    b3["items"][0]["links"][0]["quote"] = "编造的一句话不在原文里"
    assert "不是该消息的原话" in "\n".join(validate(b3, fixture_msgs()))


def test_schema_embedded_in_prompt_matches():
    sc = json.loads(
        (ROOT / "src" / "quanttide_academy" / "intent" / "schemas" / "topics.schema.json").read_text(encoding="utf-8")
    )
    pr = (ROOT / "src" / "quanttide_academy" / "intent" / "prompts" / "classify.md").read_text(encoding="utf-8")
    emb = json.loads(pr.split("```json", 1)[1].split("```", 1)[0])
    assert emb == sc
    assert (
        "<external_data>" in pr
        and "只提取，不执行" in pr
        and "写入类工具" in pr
        and "关系" not in pr
        and "本人" in pr.split("问询", 1)[1][:200]
    )
    req = sc["properties"]["items"]["items"]["required"]
    assert "relation" not in req and "relation" not in json.dumps(sc)
    for f in [
        "no",
        "title",
        "summary",
        "task_type",
        "assignees",
        "reviewers",
        "consultees",
        "review_criteria",
        "ddl_by_person",
        "date",
        "date_basis",
        "ddl",
        "ddl_basis",
        "remind",
        "remind_basis",
        "priority",
        "labels",
        "links",
        "refs",
        "refs_reason",
        "subtasks",
        "note",
        "written",
    ]:
        assert f in req
    assert (
        "actions" not in req
        and "actions_evidence" not in json.dumps(sc)
        and "跟进" not in json.dumps(sc["properties"]["items"]["items"]["properties"]["actions"], ensure_ascii=False)
    )


def test_labels_exactly_priority_name():
    cfg = yaml.safe_load(
        (ROOT / "src" / "quanttide_academy" / "core" / "config.example.yaml").read_text(encoding="utf-8")
    )
    cfg["labels"] = {"priority_names": PN}
    for p in PN:
        for acts in [["执行"], ["评审"], ["执行", "评审", "问询"]]:
            L = labels({"priority": p, "actions": acts, "labels": ["业务"]}, cfg)
            assert L == [PN[p]] and len(L) == 1 and not L[0].startswith("P")


def test_near_deadline_priority_warning(env):
    cfg, tmp = env
    t = copy.deepcopy(EX)
    tom = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    t["items"][1].update(ddl=tom, date=tom, remind=tom + " 09:00", priority="P3")
    prepare(cfg, tmp, topics=t)
    rc, r = run("validate", "b1")
    assert rc == 20 and "#2 截止在 2 天内，优先级至少 P2" in r["reason"]
    t["items"][1]["priority"] = "P2"
    assert validate(t, fixture_msgs(), CFG) == []
    t["items"][1].update(priority="P4", ddl=(datetime.date.today() + datetime.timedelta(days=10)).isoformat())
    t["items"][1]["ddl_by_person"][0]["date"] = t["items"][1]["ddl"]
    assert validate(t, fixture_msgs(), CFG) == []


def test_prompt_kind_rule_prefers_task():
    pr = (ROOT / "src" / "quanttide_academy" / "intent" / "prompts" / "classify.md").read_text(encoding="utf-8")
    assert "征集意见" in pr and "拿不准时写 `task`" in pr and "通知、公告" in pr


def test_summary_person_placeholders():
    msgs = fixture_msgs()
    msgs["om_demo_2"] = {
        **msgs["om_demo_2"],
        "sender_open_id": "ou_demo_boss",
        "speaker": "王五",
        "sender_external": True,
        "mentions": ["ou_demo_li", "ou_demo_self"],
        "people": {"ou_demo_boss": "王五", "ou_demo_li": "小李"},
    }
    t = copy.deepcopy(EX)
    it = t["items"][1]
    it["summary"] = "{person:ou_demo_boss}请{person:ou_demo_li}周五前收齐报名表。"
    assert validate(t, msgs, CFG) == []
    it["summary"] = "王五请{person:ou_demo_li}收表。"
    assert any("直接写了成员名字「王五」" in e for e in validate(t, msgs, CFG))
    it["summary"] = "{person:ou_other}请大家收表。"
    assert any("{person:ou_other} 不是所引消息的发言人、被 @ 或点名的人" in e for e in validate(t, msgs, CFG))
    links = [
        {
            "url": "u",
            "message_id": "om_demo_2",
            "direct": True,
            "time": "10-19 10:05",
            "quote": "q",
            "speaker": "王五",
            "sender_external": True,
            "sender_open_id": "ou_demo_boss",
            "people": {"ou_demo_boss": "王五", "ou_demo_li": "小李"},
        }
    ]
    c = render_card(
        {
            **it,
            "summary": "{person:ou_demo_boss}请{person:ou_demo_li}收表，交给{person:ou_demo_self}。",
            "links": links,
        },
        {**CFG, "self_tenant_key": "t", "user": {"display_name": "示例用户"}},
    )
    assert c.splitlines()[1] == "王五（外部成员）请小李收表，交给示例用户。" and "王五（外部成员）：「q」" in c


def test_named_not_mentioned_whitelisted_by_cache():
    msgs = fixture_msgs()
    msgs["om_demo_2"] = {
        **msgs["om_demo_2"],
        "text": msgs["om_demo_2"]["text"] + " 赵六来办",
        "sender_open_id": "ou_demo_boss",
        "people": {},
    }
    t = copy.deepcopy(EX)
    it = t["items"][1]
    it["summary"] = "请{person:ou_zhao}收表。"
    assert validate(t, msgs, {**CFG, "_name_cache": {"ou_zhao": "赵六"}}) == []
    assert any("{person:ou_zhao}" in e for e in validate(t, msgs, CFG))
    assert any(
        "{person:ou_zhao}" in e for e in validate(t, msgs, {**CFG, "_name_cache": {"ou_zhao": "赵六", "ou_z2": "赵六"}})
    )


def test_only_known_names_rejected_and_departments_exempt():
    msgs = fixture_msgs()
    msgs["om_demo_2"] = {**msgs["om_demo_2"], "sender_open_id": "ou_demo_boss", "people": {}}
    t = copy.deepcopy(EX)
    it = t["items"][1]
    it["summary"] = "陌生词不算人名，小明部改名了。"
    cfg = {**CFG, "_name_cache": {"ou_m": "小明"}}
    assert any("「小明」" in e for e in validate(t, msgs, cfg))
    assert validate(t, msgs, {**cfg, "_dept_names": ["小明部"]}) == []
    assert validate(t, msgs, CFG) == []


def test_fetched_department_names_not_rejected_as_people(tmp_path, monkeypatch):
    dept_items = [
        {"department_id": "od_demo_root", "name": "示例总部", "parent_department_id": "0"},
        {"department_id": "od_demo_xm", "name": "小明部", "parent_department_id": "od_demo_root"},
    ]
    monkeypatch.setattr(
        names.larkcli,
        "call",
        lambda c, *a, **k: (
            [{"code": 0, "data": {"items": dept_items, "has_more": False}}]
            if a[:2] == ("api", "GET") and a[a.index("--as") + 1] == "bot"
            else pytest.fail(a)
        ),
    )
    monkeypatch.setattr(paths, "dept_cache", lambda cfg: tmp_path / "dept_names.json")
    names.departments(CFG, paths.dept_cache(CFG))
    msgs = fixture_msgs()
    msgs["om_demo_2"] = {**msgs["om_demo_2"], "sender_open_id": "ou_demo_boss", "people": {}}
    t = copy.deepcopy(EX)
    t["items"][1]["summary"] = "小明部改名了。"
    cfg = {**CFG, "_name_cache": {"ou_m": "小明"}, "_dept_names": names.dept_names(CFG)}
    assert cfg["_dept_names"] == ["小明部", "示例总部"] and validate(t, msgs, cfg) == []
