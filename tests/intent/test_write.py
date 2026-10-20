import contextlib

from quanttide_academy.core import config, db
from tests.helpers import *


def test_flow_exit_codes_and_plan(env):
    cfg, tmp = env
    prepare(cfg, tmp)
    assert run("fetch", "b2")[0] == 30  # 别的批次未收尾
    assert run("validate", "b1")[0] == 0 and run("render", "b1")[0] == 0
    w = tmp / "w" / "b1"
    cards = (w / "cards.txt").read_text(encoding="utf-8")
    arc = (w / "archive.md").read_text(encoding="utf-8")
    assert "fi:" not in cards and "<!--" not in cards and "【#3】" not in cards and "仅知悉" in cards and "#3" in cards
    assert "<!-- fi:id=1 msg=om_demo_1,om_demo_5 -->" in arc and "### [#3]" in arc
    assert "13812345678" not in cards and "@" not in cards
    assert run("pushed", "b1")[0] == 0
    rc, r = run("reply", "b1", "好的")
    assert rc == 0 and r["actions"] == [] and r["ask_user"]
    rc, r = run("write", "b1")
    assert r["mode"] == "plan" and r["actions"] == []  # 未确认：计划为空
    rc, r = run("reply", "b1", "#3 写入")
    assert r["actions"] == [] and r["ask_user"]  # 仅知悉不在卡片里
    rc, r = run("reply", "b1", "#1 写入")
    assert r["actions"][0]["action"] == "confirm"
    rc, r = run("write", "b1")
    acts = r["actions"]
    assert [a["kind"] for a in acts] == ["parent"] and r["waiting_for_parent"] == 4
    p = acts[0]
    assert p["fingerprint"] == "om:om_demo_1" and p["version"] and len(p["key"]) == 16
    pl = p["payload"]
    assert (
        pl["due_date"] == "2026-10-26"
        and pl["deadline_date"] == "2026-10-28"
        and pl["labels"] == ["紧急次要"]
        and pl["priority"] == "P2"
    )
    assert (
        pl["description"].splitlines()[0]
        == "行动：执行 ｜ 任务类型：个人任务 ｜ 执行员：示例用户 ｜ 评审：无 ｜ 咨询：无"
    )
    assert "纯资讯 1 条，待你指派 0 条。" in cards and "#3 阅读新出的行业报告（来源：示例群（虚构））" in cards
    plan = json.loads((w / "writes.json").read_text(encoding="utf-8"))
    assert plan["actions"][0]["key"] == p["key"]
    assert run("mark-written", "b1", p["key"], "T100")[0] == 0
    rc, r = run("write", "b1")
    kinds = [a["kind"] for a in r["actions"]]
    assert kinds == ["subtask"] * 3 + ["reminder"]
    assert all(a["parent_ext_id"] == "T100" for a in r["actions"])
    k = [a["key"] for a in r["actions"]]
    run("mark-written", "b1", k[0], "S1")
    run("mark-written", "b1", k[1], "fail")
    rc, r = run("write", "b1")
    assert [a["key"] for a in r["actions"]] == k[1:]  # 只出未完成的
    for x in k[1:]:
        run("mark-written", "b1", x, "X")
    rc, r = run("write", "b1")
    assert r["actions"] == []
    with contextlib.closing(db.connect(config.load())) as d:
        row = d.execute("select parent_id,subs_done,status from writes where fingerprint='om:om_demo_1'").fetchone()
        assert row[0] == "T100" and json.loads(row[1]) == [0, 1, 2] and row[2] == "done"
        assert d.execute("select status from topics where fingerprint='om:om_demo_1'").fetchone()[0] == "written"
        assert d.execute("select count(*) from reply_logs where batch='b1'").fetchone()[0] == 3
    assert run("commit", "b1")[0] == 0 and run("render", "b1")[0] == 20


def test_mark_written_rechecks_version(env):
    cfg, tmp = env
    prepare(cfg, tmp)
    run("validate", "b1")
    run("render", "b1")
    run("pushed", "b1")
    run("reply", "b1", "#2 写入")
    key = run("write", "b1")[1]["actions"][0]["key"]
    t = copy.deepcopy(EX)
    t["items"][1]["ddl"] = "2026-10-24"  # 修改后内容变了
    (tmp / "w" / "b1" / "topics.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    run("validate", "b1")
    rc, r = run("mark-written", "b1", key, "T1")
    assert rc == 1 and "当前确认版本" in r["reason"]
    assert run("write", "b1")[1]["actions"] == []


def test_refs_never_create_followups(env):
    cfg, tmp = env
    fu = tmp / "fu.json"
    fu.write_text(json.dumps([{"id": "F1", "title": "秋季活动筹备（示例）"}], ensure_ascii=False), encoding="utf-8")
    c = yaml.safe_load(Path(os.environ["FEISHU_INTENT_CONFIG"]).read_text(encoding="utf-8"))
    c["followups"] = {"path": str(fu)}
    Path(os.environ["FEISHU_INTENT_CONFIG"]).write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")
    before = fu.read_text(encoding="utf-8")
    prepare(cfg, tmp)
    run("validate", "b1")
    run("render", "b1")
    run("pushed", "b1")
    run("reply", "b1", "#2 写入")
    run("write", "b1")
    with contextlib.closing(db.connect(config.load())) as d:
        assert [r[0] for r in d.execute("select ext_id from topics where origin='外部跟进'")] == [
            "F1"
        ] and fu.read_text(encoding="utf-8") == before
        assert d.execute("select origin from topics where fingerprint='om:om_demo_2'").fetchone()[0] == "识别"


def test_assign_card_todoist_plan(env):
    """指派卡：写成用户自己的任务「指派：<任务名>」；用户本人没有 DDL 就不填 deadline，执行员的 DDL 写进描述。"""
    cfg, tmp = env
    t = copy.deepcopy(EX)
    t["items"][1]["reviewers"] = []
    prepare(cfg, tmp, topics=t)
    run("validate", "b1")
    run("render", "b1")
    run("pushed", "b1")
    run("reply", "b1", "#2 写入")
    _rc, r = run("write", "b1")
    pl = next(a for a in r["actions"] if a["kind"] == "parent")["payload"]
    assert pl["content"] == "指派：跟进活动报名表收集" and pl["deadline_date"] is None
    assert (
        "小李 2026-10-23" in pl["description"]
        and "审批人：示例用户（按规则：执行员是别人）" in pl["description"].splitlines()[0]
    )
