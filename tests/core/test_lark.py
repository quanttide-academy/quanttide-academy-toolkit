from quanttide_academy_toolkit import settings
from quanttide_academy_toolkit.core import lark as larkcli
from tests.helpers import *


@pytest.mark.parametrize("kind", ["cmd", "script"])
def test_larkcli_utf8(tmp_path, kind):
    exe = fake_cli(tmp_path, kind)
    objs = larkcli.call({"lark_cli": {"path": str(exe)}}, "im", "+chat-list")
    assert objs[0]["data"]["chats"][0]["name"] == "测试群😀"


def test_larkcli_failure(tmp_path):
    py = tmp_path / "bad.py"
    py.write_text("import sys\nsys.stderr.write('token expired');sys.exit(2)\n", encoding="utf-8")
    exe = tmp_path / ("bad.cmd" if os.name == "nt" else "bad")
    exe.write_text(
        (f'@"{sys.executable}" "{py}" %*\n') if os.name == "nt" else f'#!/bin/sh\nexec "{sys.executable}" "{py}"\n',
        encoding="utf-8",
    )
    if os.name != "nt":
        exe.chmod(0o755)
    with pytest.raises(larkcli.LarkError):
        larkcli.call({"lark_cli": {"path": str(exe)}}, "im", "+chat-list")


def test_injectable_runner_ok_code_and_extract_json():
    calls = []

    class FakeRunner:
        def __init__(self, out):
            self.out = out

        def run(self, cfg, args, timeout=120):
            calls.append(args)
            return self.out

    r1 = larkcli.call({}, "im", "+chat-list", runner=FakeRunner('{"data":{"chats":[{"chat_id":"oc_bare"}]}}'))
    assert r1 == [{"data": {"chats": [{"chat_id": "oc_bare"}]}}] and calls[-1] == ["im", "+chat-list"]
    noisy = 'notice: start\n{"ok":true,"code":0,"data":{"items":[1,2]}}\ntrailer line'
    assert larkcli.call({}, "api", "GET", "/open-apis/im/v1/messages", runner=FakeRunner(noisy))[0]["data"][
        "items"
    ] == [1, 2]
    with pytest.raises(larkcli.LarkError, match="飞书接口错误"):
        larkcli.call({}, "im", "+chat-list", runner=FakeRunner('{"ok":false,"error":"unauthorized"}'))
    with pytest.raises(larkcli.LarkError, match="99991663"):
        larkcli.call({}, "im", "+chat-list", runner=FakeRunner('{"ok":true,"code":99991663,"msg":"bad token"}'))


def test_page_all_max_pages_and_has_more_error(monkeypatch):
    monkeypatch.setenv("FEISHU_WORKFLOWS_MAX_PAGES", "2")
    assert settings.max_pages({}) == 2
    two_pages = '{"code":0,"data":{"items":[1],"has_more":false}}\n{"code":0,"data":{"items":[2],"has_more":false}}'
    assert (
        len(larkcli.call({}, "api", "GET", "/open-apis/im/v1/messages", "--page-all", runner=lambda a: two_pages)) == 2
    )
    three_pages = two_pages + '\n{"code":0,"data":{"items":[3],"has_more":false}}'
    with pytest.raises(larkcli.LarkError, match="max_pages=2"):
        larkcli.call({}, "api", "GET", "/open-apis/im/v1/messages", "--page-all", runner=lambda a: three_pages)
    unfinished = '{"code":0,"data":{"items":[1],"has_more":true,"page_token":"nxt"}}'
    with pytest.raises(larkcli.LarkError, match="has_more=true"):
        larkcli.call(
            {"lark_cli": {"max_pages": 5}},
            "api",
            "GET",
            "/open-apis/im/v1/messages",
            "--page-all",
            runner=lambda a: unfinished,
        )
    with pytest.raises(ValueError, match="max_pages"):
        settings.max_pages({"max_pages": 0})
