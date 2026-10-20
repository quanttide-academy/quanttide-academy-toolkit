from feishu_workflows.core import config
from feishu_workflows.intent import flow_common as fc
from tests.helpers import *


def test_sanitize_text():
    t = fc.sanitize_text("@张三 电话13812345678 https://x.y/z?token=abc 看下")
    assert "（成员）" in t and "138****5678" in t and "[链接]" in t and "abc" not in t
    assert fc.sanitize_text("字" * 400, n=10).endswith("…")


def test_external_rules():
    assert fc._external({}, {"sender_tenant_key": "t1"})
    assert not fc._external({"self_tenant_key": "t1"}, {"sender_tenant_key": "t1"})
    assert fc._external({"self_tenant_key": "t1"}, {})


def test_state_files(env):
    c = config.load()
    assert fc.state(c, "b9")["stage"] == "new"
    fc.set_state(c, "b9", stage="validated")
    assert fc.state(c, "b9")["stage"] == "validated"


def test_write_messages_keeps_watch_fields_only_when_present(env):
    cfg, tmp = env
    fc.write_messages(
        cfg, "wm", [{"message_id": "m1", "text": "a", "dm": True, "target": "ou_a"}, {"message_id": "m2", "text": "b"}]
    )
    ms = json.loads((tmp / "w" / "wm" / "messages.json").read_text(encoding="utf-8"))["messages"]
    assert ms[0]["dm"] is True and ms[0]["target"] == "ou_a" and "dm" not in ms[1] and "target" not in ms[1]
