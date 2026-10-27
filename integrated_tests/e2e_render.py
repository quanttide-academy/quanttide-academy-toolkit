"""离线重渲染 e2e #6–#10：按 data/e2e-scope-<范围>.json 过滤消息，用 data/work/e2e-6-10/<输出目录>/topics.json 走 fetch→validate→render。
不联网、不写 Todoist/飞书；临时库与工作目录放在临时目录，产物（messages/cards/archive/versions）拷回输出目录。
本人称呼与角色读 data/e2e-user.json，self_open_id 读 config.yaml（都不入库）。用法：python integrated_tests/e2e_render.py A|B"""

import contextlib
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import yaml

from quanttide_academy_toolkit import cli
from quanttide_academy_toolkit.intent import names
from quanttide_academy_toolkit.settings import default_data_dir

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "work" / "e2e-6-10"
OUT = {"A": BASE / "A-v3", "B": BASE / "B-v2"}
RAW = {"A": BASE / "A-v2" / "messages.json", "B": BASE / "B" / "messages.json"}
MSGS = {
    k: v / "messages-named.json" for k, v in OUT.items()
}  # 补了 sender_open_id、speaker、people 的消息（resolve 生成）


def available(scope):
    return all(
        p.exists()
        for p in (
            ROOT / "data" / f"e2e-scope-{scope}.json",
            ROOT / "data" / "e2e-user.json",
            ROOT / "config.yaml",
            MSGS[scope],
            OUT[scope] / "topics.json",
            BASE / "followups-e2e.json",
        )
    )


def resolve(scope):
    """联网只读一次：从 state.db 取发言人 open_id，按群成员 → 通讯录解析姓名（缓存 data/name_cache.json），写 messages-named.json。"""
    real = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    doc = json.loads(RAW[scope].read_text(encoding="utf-8"))
    msgs = doc["messages"]
    d = sqlite3.connect(str(ROOT / real.get("paths", {}).get("state_db", "state.db")))
    try:
        for m in msgs:
            r = d.execute("select sender from messages where message_id=?", (m["message_id"],)).fetchone()
            m["sender_open_id"] = r[0] if r else None
    finally:
        d.close()
    n = names.fill(real, msgs, default_data_dir() / "name_cache.json")
    names.departments(real, default_data_dir() / "dept_names.json")
    MSGS[scope].write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(msgs), n, len({o for m in msgs for o in m.get("people") or {}})


def _run(*a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(["feishu-workflows", *a, "--json"])
    return rc, json.loads(buf.getvalue().strip().splitlines()[-1])


def render(scope):
    real = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        fu = t / "followups.json"
        fu.write_text((BASE / "followups-e2e.json").read_text(encoding="utf-8"), encoding="utf-8")
        cfg = {
            "labels": real["labels"],
            "paths": {"data_dir": str(t / "d"), "work_dir": str(t / "w")},
            "todo": {"provider": "markdown"},
            "followups": {"path": str(fu)},
            "scope": json.loads((ROOT / "data" / f"e2e-scope-{scope}.json").read_text(encoding="utf-8")),
            "self_open_id": real["self_open_id"],
            "user": json.loads((ROOT / "data" / "e2e-user.json").read_text(encoding="utf-8")),
        }
        (t / "d").mkdir()
        for f in ("name_cache.json", "dept_names.json"):  # 只读缓存带进临时数据目录
            if (default_data_dir() / f).exists():
                shutil.copy(default_data_dir() / f, t / "d" / f)
        (t / "config.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
        old = os.environ.get("FEISHU_INTENT_CONFIG")
        os.environ["FEISHU_INTENT_CONFIG"] = str(t / "config.yaml")
        try:
            b = f"e2e-{scope}"
            rc, _ = _run("fetch", b, "--from", str(MSGS[scope]))
            if rc != 10:
                raise RuntimeError(f"fetch 退出码 {rc}")
            shutil.copy(OUT[scope] / "topics.json", t / "w" / b / "topics.json")
            rc, r = _run("validate", b)
            if rc != 0:
                raise RuntimeError(f"validate 失败：{r}")
            rc, rep = _run("render", b)
            _run("abort", b, "e2e 离线渲染结束")
            for f in ("messages.json", "cards.txt", "archive.md", "versions.json"):
                shutil.copy(t / "w" / b / f, OUT[scope] / f)
            return rep
        finally:
            if old is None:
                os.environ.pop("FEISHU_INTENT_CONFIG", None)
            else:
                os.environ["FEISHU_INTENT_CONFIG"] = old


if __name__ == "__main__":
    if sys.argv[2:3] == ["--resolve"]:
        print("消息、补上发言人、解析人数：", resolve(sys.argv[1]))
    print(json.dumps(render(sys.argv[1]), ensure_ascii=False, indent=1))
