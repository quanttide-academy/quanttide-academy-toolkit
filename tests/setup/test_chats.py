import contextlib
import io

from quanttide_academy_toolkit.setup import main

from tests.helpers import *


def test_chats_without_config_lists_chats(tmp_path, monkeypatch):
    """首次使用、还没有 config.yaml 时也要能列出群，不能直接抛 FileNotFoundError。

    setup questions 里 include_chats 那条的说明要求先跑 `feishu-workflows-setup chats --json`，
    所以这一步必须能在配置文件还不存在的时候跑通。
    """
    monkeypatch.setenv("FEISHU_WORKFLOWS_CONFIG", str(tmp_path / "missing.yaml"))
    monkeypatch.delenv("FEISHU_INTENT_CONFIG", raising=False)

    seen = []

    def fake_list_chats(cfg):
        seen.append(cfg)
        return [{"chat_id": "oc_demo", "name": "示例群", "external": False}]

    monkeypatch.setattr("quanttide_academy_toolkit.setup.collect.list_chats", fake_list_chats)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        main(["chats"])

    assert json.loads(buf.getvalue())["chats"] == [
        {"chat_id": "oc_demo", "name": "示例群", "external": False, "selected": False}
    ]
    assert seen == [{}]
