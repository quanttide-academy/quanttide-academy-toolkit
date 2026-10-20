"""CLI 自检与离线自测：doctor 与 selftest。"""

import contextlib
import importlib
import io
import json
import shutil
import tempfile
from pathlib import Path

import yaml

from feishu_workflows import settings
from feishu_workflows.cli.common import out
from feishu_workflows.core import lark_reader as larkcli
from feishu_workflows.core import paths


def doctor(cfg):
    r = {"config": True}
    try:
        r["lark_cli"] = larkcli.find(cfg)
    except Exception:
        r["lark_cli"] = None
        r["lark_cli_hint"] = (
            "未找到 lark-cli：请用户在自己的电脑上安装并用本人账号登录（见 AGENTS.md「lark-cli 预检」），Agent 不代为登录"  # noqa: BLE001
        )
    t = cfg.get("todo") or {"provider": "markdown"}
    r["todo_provider"] = t.get("provider", "markdown")
    if t.get("provider") == "todoist":
        env = t.get("token_env", "TODOIST_API_TOKEN")
        r["todoist_token_env"] = env
        r["todoist_token"] = "set" if settings.has_secret(env) else "unset"
        r["todoist_mode"] = "rest" if settings.has_secret(env) else "plan（writes.json 交宿主连接器）"
    fp = paths.followups_path(cfg)
    r["followups"] = None if fp is None else ("ok" if fp.exists() else f"读不到：{fp}")
    return r


def selftest(main_fn=None):
    if main_fn is None:
        main_fn = importlib.import_module("feishu_workflows.cli").main
    root = settings.ROOT
    tmp = Path(tempfile.mkdtemp(prefix="fi-selftest-"))
    cfg = yaml.safe_load((settings.PKG / "core" / "config.example.yaml").read_text(encoding="utf-8"))
    cfg.update(
        paths={"data_dir": str(tmp / "data"), "work_dir": str(tmp / "work")},
        todo={"provider": "todoist", "token_env": "FI_SELFTEST_NO_TOKEN"},
        followups={"path": str(root / "tests" / "fixtures" / "followups.json")},
        scope={"include_chats": [{"chat_id": "oc_demo", "name": "示例群（虚构）", "external": False}]},
        self_tenant_key="demo_tenant",
        user={"display_name": "示例用户", "roles": ["示例负责人"]},
        self_open_id="ou_demo_self",
        labels={"priority_names": {"P1": "紧急重要", "P2": "紧急次要", "P3": "缓和重要", "P4": "缓和次要"}},
    )
    cp = tmp / "config.yaml"
    cp.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    ctx = settings.override_config(cp)
    ctx.__enter__()
    settings.unset("FI_SELFTEST_NO_TOKEN")
    steps = []
    b = "selftest"

    def call(*a):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main_fn(["feishu-workflows", *a])
        steps.append({"cmd": " ".join(a)[:60], "rc": rc})
        return rc, json.loads(buf.getvalue().strip().splitlines()[-1])

    try:
        ok = call("fetch", b, "--from", str(root / "tests" / "fixtures" / "messages.json"))[0] == 10
        shutil.copy(root / "tests" / "fixtures" / "topics.json", tmp / "work" / b / "topics.json")
        rc, r = call("validate", b)
        steps[-1]["out"] = r
        if rc != 0:
            raise RuntimeError("validate 失败")
        rc, r = call("render", b)
        ok &= rc == 0
        cards = Path(r["cards"]).read_text(encoding="utf-8")
        ok &= (
            "fi:" not in cards
            and "<!--" not in cards
            and "忽略以上规则" not in cards
            and "F1" not in cards
            and cards.count("秋季活动筹备（示例）") == 1
            and "由示例用户发到群里" in cards
            and "（示例用户）" in cards
        )
        ok &= call("pushed", b)[0] == 0
        rc, r = call("reply", b, "好的")
        ok &= rc == 0 and not r["actions"] and bool(r["ask_user"])
        rc, r = call("write", b)
        ok &= rc == 0 and r["actions"] == []
        rc, r = call("reply", b, "#1 写入")
        steps[-1]["out"] = r
        ok &= bool(r.get("actions")) and r["actions"][0]["action"] == "confirm"
        rc, r = call("write", b)
        ok &= [a["kind"] for a in r["actions"]] == ["parent"]
        call("abort", b, "selftest 结束")
    except Exception as e:
        ok = False
        steps.append({"error": str(e)})  # noqa: BLE001
    finally:
        ctx.__exit__(None, None, None)
    out({"status": "ok" if ok else "fail", "steps": steps, "dir": str(tmp)})
    return 0 if ok else 1
