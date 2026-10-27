"""测试公共部分：路径、合成数据、隔离配置的 env 夹具、命令行调用。"""

import contextlib
import copy
import datetime
import io
import json
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

from quanttide_academy import cli as R
from quanttide_academy.cli.doctor import freshen_fixture_dates
from quanttide_academy.intent.state import sanitize_text

__all__ = [
    "EX",
    "MSG",
    "bump_date",
    "load_topics",
    "PN",
    "ROOT",
    "SUBENV",
    "TEXT",
    "Path",
    "copy",
    "env",
    "fake_cli",
    "fake_lark_cli",
    "fixture_msgs",
    "json",
    "no_self_mention",
    "os",
    "prepare",
    "pytest",
    "run",
    "stat",
    "subprocess",
    "sys",
    "textwrap",
    "yaml",
]
ROOT = Path(__file__).resolve().parent.parent  # 仓库根目录
SUBENV = {**os.environ, "PYTHONPATH": str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")}
PN = {"P1": "紧急重要", "P2": "紧急次要", "P3": "缓和重要", "P4": "缓和次要"}


def load_topics(name="topics.json"):
    raw = json.loads((ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8"))
    return freshen_fixture_dates(raw)


def bump_date(iso, days=1):
    """把 YYYY-MM-DD 往后推一天（或若干天），避免用例写死已经过期的绝对日期。"""
    return (datetime.date.fromisoformat(iso) + datetime.timedelta(days=days)).isoformat()


EX = load_topics()
MSG = json.loads((ROOT / "tests" / "fixtures" / "messages.json").read_text(encoding="utf-8"))


@pytest.fixture
def env(tmp_path, monkeypatch):
    cfg = {
        "labels": {"priority_names": PN},
        "paths": {"data_dir": str(tmp_path / "d"), "work_dir": str(tmp_path / "w")},
        "todo": {"provider": "todoist", "token_env": "FI_TEST_TOKEN"},
        "followups": {"path": None},
        "scope": {"include_chats": [{"chat_id": "oc_demo", "name": "示例群（虚构）", "external": False}]},
        "self_tenant_key": "t_test",
        "self_open_id": "ou_demo_self",
        "user": {"display_name": "示例用户", "roles": ["示例负责人"]},
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    monkeypatch.delenv("FEISHU_WORKFLOWS_CONFIG", raising=False)
    monkeypatch.setenv("FEISHU_INTENT_CONFIG", str(p))
    monkeypatch.delenv("FI_TEST_TOKEN", raising=False)
    return cfg, tmp_path


def run(*a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = R.main(["feishu-workflows", *a, "--json"])
    return rc, json.loads(buf.getvalue().strip().splitlines()[-1])


def prepare(cfg, tmp, b="b1", topics=None, messages="messages.json"):
    assert run("fetch", b, "--from", str(ROOT / "tests" / "fixtures" / messages))[0] == 10
    (tmp / "w" / b / "topics.json").write_text(json.dumps(topics or EX, ensure_ascii=False), encoding="utf-8")


def fixture_msgs():
    return {
        m["message_id"]: {"text": sanitize_text(m["text"]), "mentions_self": m["mentions_self"]}
        for m in MSG["messages"]
    }


def no_self_mention(msgs):
    """把 om_demo_2 改回没有 @ 用户的版本（测试「原话没点到用户」）。"""
    msgs["om_demo_2"] = {
        **msgs["om_demo_2"],
        "text": sanitize_text("活动报名表请@小李 负责收集，周五前交给我。"),
        "mentions_self": False,
    }
    return msgs


TEXT = "某负责人说：明天 10:00 开会 🎉"


def fake_cli(tmp, kind):
    payload = json.dumps(
        {
            "code": 0,
            "data": {
                "chats": [{"chat_id": "oc_1", "name": "测试群😀"}],
                "items": [{"user_id": "ou_a", "member_id": "ou_a"}],
            },
        },
        ensure_ascii=False,
    )
    if kind == "cmd":
        py = tmp / "fake.py"
        py.write_text(
            f"import sys\nsys.stdout.reconfigure(encoding='utf-8')\nprint('提示行')\nprint({payload!r})\n",
            encoding="utf-8",
        )
        exe = tmp / ("lark-cli.cmd" if os.name == "nt" else "lark-cli")
        exe.write_text(
            (f'@"{sys.executable}" "{py}" %*\n')
            if os.name == "nt"
            else f'#!/bin/sh\nexec "{sys.executable}" "{py}" "$@"\n',
            encoding="utf-8",
        )
    else:
        exe = tmp / "lark-cli.py"
        exe.write_text(f"import sys\nsys.stdout.reconfigure(encoding='utf-8')\nprint({payload!r})\n", encoding="utf-8")
        if os.name != "nt":
            sh = tmp / "lark-cli2"
            sh.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{exe}" "$@"\n', encoding="utf-8")
            exe = sh
        else:
            w = tmp / "lark-cli2.cmd"
            w.write_text(f'@"{sys.executable}" "{exe}" %*\n', encoding="utf-8")
            exe = w
    if os.name != "nt":
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


def fake_lark_cli(tmp, chat_messages: dict, members: list | None = None):
    """Python 编写的跨平台假 lark-cli（经 SubprocessRunner 启动）：每次调用追加 argv 到 tmp/argv.log，只响应 GET。"""
    tmp = Path(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    log = tmp / "argv.log"
    fx = tmp / "fake_lark_data.json"
    mems = (
        members
        if members is not None
        else [{"member_id": "ou_boss", "name": "负责人甲"}, {"member_id": "ou_demo_li", "name": "小李"}]
    )
    fx.write_text(json.dumps({"chats": chat_messages, "members": mems}, ensure_ascii=False), encoding="utf-8")
    py = tmp / "fake_lark_cli.py"
    py.write_text(
        textwrap.dedent(f"""\
        import json, sys
        from pathlib import Path
        sys.stdout.reconfigure(encoding="utf-8")
        args = sys.argv[1:]
        with open({str(log)!r}, "a", encoding="utf-8") as f:
            f.write(json.dumps(args, ensure_ascii=False) + "\\n")
        if args[:2] != ["api", "GET"]:
            sys.stderr.write("only api GET allowed in fake_lark_cli\\n")
            sys.exit(2)
        data = json.loads(Path({str(fx)!r}).read_text(encoding="utf-8"))
        path = args[2]
        params = json.loads(args[args.index("--params") + 1]) if "--params" in args else {{}}
        if path == "/open-apis/im/v1/messages":
            items = data["chats"].get(params.get("container_id"), [])
            print(json.dumps({{"ok": True, "code": 0, "data": {{"items": items, "has_more": False}}}}, ensure_ascii=False))
        elif path.endswith("/members"):
            print(json.dumps({{"ok": True, "code": 0, "data": {{"items": data["members"], "has_more": False}}}}, ensure_ascii=False))
        else:
            print(json.dumps({{"ok": True, "code": 0, "data": {{"items": [], "has_more": False}}}}, ensure_ascii=False))
    """),
        encoding="utf-8",
    )
    return py, log
