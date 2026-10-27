import time

from quanttide_academy_toolkit.intent.reply_parse import parse_reply
from tests.helpers import *


def name_cache(tmp, m):
    (tmp / "d").mkdir(parents=True, exist_ok=True)
    (tmp / "d" / "name_cache.json").write_text(
        json.dumps({k: {"name": v, "at": int(time.time())} for k, v in m.items()}, ensure_ascii=False), encoding="utf-8"
    )


def test_promote_pending_item(env):
    cfg, tmp = env
    prepare(cfg, tmp)
    run("validate", "b1")
    run("render", "b1")
    run("pushed", "b1")
    rc, r = run("reply", "b1", "升格 #3")
    assert r["actions"] == [] and "须" in r["ask_user"] or "需要同时指定办理人" in r["ask_user"]
    rc, r = run("reply", "b1", "升格 #1 我来办")
    assert r["actions"] == [] and "不是纯资讯" in r["ask_user"]
    rc, r = run("reply", "b1", "升格 #3 我来办")
    assert rc == 0 and r["actions"][0]["action"] == "promote", r
    cards = (tmp / "w" / "b1" / "cards.txt").read_text(encoding="utf-8")
    assert "【#3】" in cards and "纯资讯 0 条" in cards and "执行员：示例用户" in cards
    assert parse_reply("升格 #3 办理人：张三")[0] == [{"action": "promote", "no": 3, "assignee": "张三"}]
    run("pushed", "b1")
    rc, r = run("reply", "b1", "#3 写入")
    assert r["actions"][0]["action"] == "confirm"


def test_promote_to_other_person_jerry_reviews(env):
    cfg, tmp = env
    prepare(cfg, tmp)
    run("validate", "b1")
    run("render", "b1")
    run("pushed", "b1")
    _rc, r = run("reply", "b1", "升格 #3 由张三负责")
    assert r["actions"] and r["actions"][0]["assignee"] == "张三"
    cards = (tmp / "w" / "b1" / "cards.txt").read_text(encoding="utf-8")
    blk = cards.split("【#3】")[1]
    assert (
        "执行员：张三" in blk
        and "评审员：执行员 -> 示例用户" in blk
        and "行动：评审" in blk
        and "任务类型：个人任务" in blk
    )
    t = json.loads((tmp / "w" / "b1" / "topics.json").read_text(encoding="utf-8"))["items"][2]
    assert (
        t["assignees"][0]["basis"] == "reply"
        and t["reviewers"][0]["basis"] == "reply"
        and t["reviewers"][0]["open_id"] == "ou_demo_self"
    )


def test_promote_with_self_stated_role(env):
    assert parse_reply("升格 #3 张三，我咨询")[0] == [
        {"action": "promote", "no": 3, "assignee": "张三", "self_role": "问询"}
    ]
    assert parse_reply("升格 #3 办理人：张三 我来执行")[0][0]["self_role"] == "执行"
    cfg, tmp = env
    prepare(cfg, tmp)
    run("validate", "b1")
    run("render", "b1")
    run("pushed", "b1")
    run("reply", "b1", "升格 #3 张三，我咨询")
    blk = (tmp / "w" / "b1" / "cards.txt").read_text(encoding="utf-8").split("【#3】")[1]
    assert "咨询对象：示例用户" in blk and "评审员：无" in blk and "行动：问询" in blk


def test_assign_and_reassign_bump_version(env):
    assert parse_reply("指派 #2 张三")[0] == [{"action": "assign", "no": 2, "assignee": "张三"}]
    assert parse_reply("改派 #2 给王五")[0] == [{"action": "reassign", "no": 2, "assignee": "王五"}]
    assert parse_reply("指派 #2")[0] == []
    cfg, tmp = env
    t = copy.deepcopy(EX)
    t["items"][1]["reviewers"] = []
    name_cache(tmp, {"ou_zs": "张三", "ou_ww": "王五"})
    prepare(cfg, tmp, topics=t)
    run("validate", "b1")
    run("render", "b1")
    run("pushed", "b1")
    assert "回复「指派 #序号 姓名」" in (tmp / "w" / "b1" / "cards.txt").read_text(encoding="utf-8")
    v0 = json.loads((tmp / "w" / "b1" / "versions.json").read_text(encoding="utf-8"))["2"]["version"]
    _rc, r = run("reply", "b1", "指派 #2 张三")
    a = r["actions"][0]
    assert a["action"] == "assign" and a["old_version"] == v0 and a["version"] != v0
    blk = (tmp / "w" / "b1" / "cards.txt").read_text(encoding="utf-8").split("【#2】")[1].split("【#3】")[0]
    assert "执行员：张三" in blk and "行动：指派" in blk
    it = json.loads((tmp / "w" / "b1" / "topics.json").read_text(encoding="utf-8"))["items"][1]
    assert it["assignees"][0]["basis"] == "reply" and it["assignees"][0]["open_id"] == "ou_zs"
    run("pushed", "b1")
    _rc, r2 = run("reply", "b1", "改派 #2 王五")
    assert r2["actions"][0]["version"] not in (v0, a["version"])
    _rc, r3 = run("reply", "b1", "指派 #3 张三")
    assert r3["actions"] == [] and "升格" in r3["ask_user"]
    _rc, r4 = run("reply", "b1", "升格 #2 张三")
    assert r4["actions"] == [] and "不是纯资讯" in r4["ask_user"]


def test_assign_unresolved_or_ambiguous_asks(env):
    cfg, tmp = env
    t = copy.deepcopy(EX)
    t["items"][1]["reviewers"] = []
    name_cache(tmp, {"ou_a": "张三", "ou_b": "张三"})
    prepare(cfg, tmp, topics=t)
    run("validate", "b1")
    run("render", "b1")
    run("pushed", "b1")
    before = (tmp / "w" / "b1" / "topics.json").read_text(encoding="utf-8")
    _rc, r = run("reply", "b1", "指派 #2 张三")
    assert r["actions"] == [] and "对上了 2 位成员" in r["ask_user"]
    _rc, r = run("reply", "b1", "指派 #2 李四")
    assert r["actions"] == [] and "找不到「李四」" in r["ask_user"]
    assert (tmp / "w" / "b1" / "topics.json").read_text(encoding="utf-8") == before


def test_assign_self_removes_approver(env):
    cfg, tmp = env
    t = copy.deepcopy(EX)
    t["items"][1]["reviewers"] = []
    prepare(cfg, tmp, topics=t)
    run("validate", "b1")
    run("render", "b1")
    run("pushed", "b1")
    blk = lambda: (tmp / "w" / "b1" / "cards.txt").read_text(encoding="utf-8").split("【#2】")[1].split("【#3】")[0]
    assert "审批人：" in blk()
    _rc, r = run("reply", "b1", "指派 #2 我")
    assert r["actions"][0]["action"] == "assign"
    b = blk()
    assert "审批人：" not in b and "执行员：示例用户" in b and "行动：执行" in b
