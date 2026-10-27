import contextlib
import re

from quanttide_academy import cli as R
from quanttide_academy.core import config, db
from tests.helpers import *


def test_modify_needs_rerender_and_unnumbered(env):
    cfg, tmp = env
    prepare(cfg, tmp)
    run("validate", "b1")
    run("render", "b1")
    run("pushed", "b1")
    rc, r = run("reply", "b1", "写入")
    assert r["actions"] == [] and "序号" in r["ask_user"]
    vers = json.loads((tmp / "w" / "b1" / "versions.json").read_text(encoding="utf-8"))
    rc, r = run("reply", "b1", "写入", "--quote", f"{vers['2']['fingerprint']}@{vers['2']['version']}")
    assert r["actions"][0]["no"] == 2
    rc, r = run("reply", "b1", "#1 修改：截止改到 10-30")
    assert r["actions"][0]["action"] == "modify"
    with contextlib.closing(db.connect(config.load())) as d:
        assert R.next_step(config.load(), d, "b1")["step"] == "llm_edit"
    t = copy.deepcopy(EX)
    t["items"][0]["ddl"] = bump_date(t["items"][0]["ddl"])
    (tmp / "w" / "b1" / "topics.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    _rc, r = run("reply", "b1", "#1 写入")
    assert r["actions"] == [] and "改过" in r["ask_user"]
    run("validate", "b1")
    run("render", "b1")
    _rc, r = run("reply", "b1", "#1 写入")
    assert r["actions"][0]["action"] == "confirm"


def test_explain_and_confirm_all(env):
    cfg, tmp = env
    prepare(cfg, tmp)
    run("validate", "b1")
    run("render", "b1")
    run("pushed", "b1")
    rc, r = run("reply", "b1", "#2 说明：报名表周四就要")
    assert r["actions"][0]["action"] == "explain"
    with contextlib.closing(db.connect(config.load())) as d:
        assert d.execute("select confirmed from topics where fingerprint='om:om_demo_2'").fetchone()[0] == 0
    run("validate", "b1")
    run("render", "b1")
    rc, r = run("reply", "b1", "确认")
    assert r["actions"] == [] and r["ask_user"]
    rc, r = run("reply", "b1", "全部写入")
    lst = r["actions"][0]["pending"]
    assert [x["no"] for x in lst] == [1, 2] and "确认" in r["ask_user"]
    assert run("write", "b1")[1]["actions"] == []
    _rc, r = run("reply", "b1", "确认")
    assert sorted(a["no"] for a in r["actions"] if a["action"] == "confirm") == [1, 2]
    _rc, r = run("reply", "b1", "确认")
    assert r["actions"] == []


def test_confirm_all_invalid_after_change(env):
    cfg, tmp = env
    prepare(cfg, tmp)
    run("validate", "b1")
    run("render", "b1")
    run("pushed", "b1")
    run("reply", "b1", "全部写入")
    t = copy.deepcopy(EX)
    t["items"][0]["ddl"] = bump_date(t["items"][0]["ddl"])
    (tmp / "w" / "b1" / "topics.json").write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    run("validate", "b1")
    run("render", "b1")
    _rc, r = run("reply", "b1", "确认")
    assert r["actions"] == [] and "改过" in r["ask_user"]


def test_no_confirm_bypass(env):
    src = (ROOT / "src" / "quanttide_academy" / "cli" / "__init__.py").read_text(encoding="utf-8")
    assert 'cmd=="confirm"' not in src and "confirmed=1" not in src
    hits = []
    for p in sorted((ROOT / "src" / "quanttide_academy").rglob("*.py")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if re.search(r"set confirmed=1|confirmed_version=\?", line):
                hits.append(p.name)
    assert hits == ["reply_handle.py"]
    fl = (ROOT / "src" / "quanttide_academy" / "intent" / "reply_handle.py").read_text(encoding="utf-8")
    assert fl.count("confirmed=1,confirmed_version=?") == 1 and fl.index("confirmed=1,confirmed_version=?") > fl.index(
        "def handle_reply"
    )
    ag = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "run.py confirm" not in ag and "confirm <" not in ag
    rc, _r = run("confirm", "x", "y")
    assert rc == 2
    with contextlib.closing(db.connect(config.load())) as d:
        assert db.holder(d) is None
