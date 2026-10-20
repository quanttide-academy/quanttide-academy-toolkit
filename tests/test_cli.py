import contextlib

from feishu_workflows import cli as R
from feishu_workflows.core import db
from feishu_workflows.core import lark as larkcli
from feishu_workflows.intent import collect
from tests.helpers import *


def test_cli_package_reexports():
    for name in ("entry", "main", "abort", "doctor", "selftest", "next_step", "out", "redact", "BATCH_RE", "TOKEN_RE"):
        assert hasattr(R, name), name


def test_offline_fetch_scope(env):
    _cfg, tmp = env
    c = yaml.safe_load(Path(os.environ["FEISHU_INTENT_CONFIG"]).read_text(encoding="utf-8"))
    c["scope"] = {"include_chats": []}
    Path(os.environ["FEISHU_INTENT_CONFIG"]).write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")
    rc, r = run("fetch", "b1", "--from", str(ROOT / "tests" / "fixtures" / "messages.json"))
    assert rc == 0 and r["messages"] == 0
    run("commit", "b1")
    c["scope"] = {"include_chats": [{"chat_id": "oc_demo", "external": True}]}
    Path(os.environ["FEISHU_INTENT_CONFIG"]).write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")
    rc, r = run("fetch", "b2", "--from", str(ROOT / "tests" / "fixtures" / "messages.json"))
    assert rc == 10
    m = json.loads((tmp / "w" / "b2" / "messages.json").read_text(encoding="utf-8"))["messages"]
    assert m and all(x["external_chat"] for x in m)


def test_fetch_without_scope_calls_nothing(env, monkeypatch):
    _cfg, _tmp = env
    c = yaml.safe_load(Path(os.environ["FEISHU_INTENT_CONFIG"]).read_text(encoding="utf-8"))
    c.pop("scope")
    Path(os.environ["FEISHU_INTENT_CONFIG"]).write_text(yaml.safe_dump(c, allow_unicode=True), encoding="utf-8")
    calls = []
    monkeypatch.setattr(larkcli, "call", lambda *a, **k: calls.append(a) or [{}])
    rc, r = run("fetch", "b1")
    assert rc == 20 and "未配置监听范围，请运行 setup chats" in r["reason"] and calls == []
    with contextlib.closing(db.connect(c)) as d, pytest.raises(collect.NoScope):
        collect.run(c, d, "b")
    assert calls == []
