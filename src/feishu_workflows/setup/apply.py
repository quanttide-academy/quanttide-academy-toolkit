"""首次安装向导非交互应用、迁移与预填：apply、migrate、prefill。"""

import contextlib
import json
from pathlib import Path

import yaml

from feishu_workflows import cli as run
from feishu_workflows import settings
from feishu_workflows.core import config, db
from feishu_workflows.settings import PKG
from feishu_workflows.setup.questions import SECRET_RE


def apply(ans, target=None):
    """非交互配置：合并到现有 config.yaml（没有则用模板），写入后自检。拒收任何像令牌值的输入。"""
    for k, v in ans.items():
        if (("token" in k.lower() or "secret" in k.lower()) and not k.endswith("_env")) or (
            isinstance(v, str) and k != "watch" and SECRET_RE.search(v) and not v.startswith(("ou_", "/", "~"))
        ):
            raise SystemExit(
                json.dumps(
                    {"status": "fail", "reason": f"{k} 看起来像令牌/密钥本身。只填环境变量名，不要提供令牌值。"},
                    ensure_ascii=False,
                )
            )
    p = Path(target) if target else config.config_path()
    c = (
        yaml.safe_load(p.read_text(encoding="utf-8"))
        if p.exists()
        else yaml.safe_load((PKG / "core" / "config.example.yaml").read_text(encoding="utf-8"))
    )
    if "self_open_id" in ans:
        c["self_open_id"] = ans["self_open_id"]
    if "watch" in ans:
        c["watch"] = ans["watch"]
    if "include_chats" in ans:
        c["scope"] = {
            "include_chats": [
                {"chat_id": str(x["chat_id"]), "name": x.get("name"), "external": bool(x.get("external"))}
                for x in ans["include_chats"] or []
            ]
        }
    if "roles" in ans:
        c.setdefault("user", {})["roles"] = [str(r) for r in ans["roles"] or []]
    if "display_name" in ans:
        c.setdefault("user", {})["display_name"] = ans["display_name"]
    if "push_times" in ans:
        c.setdefault("schedule", {})["push"] = list(ans["push_times"])
    if "todo_provider" in ans:
        pv = ans["todo_provider"]
        if pv not in ("markdown", "todoist", "export", "custom"):
            raise SystemExit(json.dumps({"status": "fail", "reason": "todo_provider 不支持"}, ensure_ascii=False))
        t = {"provider": pv}
        if pv == "todoist":
            t.update(token_env=ans.get("todo_token_env") or "TODOIST_API_TOKEN", project_id=ans.get("todo_project_id"))
        if pv == "export":
            t["format"] = ans.get("export_format", "csv")
        if pv == "custom":
            t["module"] = ans["todo_module"]
        c["todo"] = t
    if "followups_path" in ans:
        c["followups"] = {"path": ans["followups_path"] or None}
    if "priority_names" in ans:
        c.setdefault("labels", {})["priority_names"] = ans["priority_names"]
    c.get("labels", {}).pop("follow_label", None)
    p.write_text(yaml.safe_dump(c, allow_unicode=True, sort_keys=False), encoding="utf-8", newline="\n")
    with settings.override_config(p):
        chk = run.doctor(c)
    return {"status": "ok", "config": str(p), "self_check": chk}


def migrate(cfg_path=None, state_chats=None, dry_run=False):
    """旧配置迁移：没有 scope 时加 scope.include_chats=[]，以前自动监听过的群放进 scope.pending_chats（不监听，等用户确认）。"""
    p = Path(cfg_path) if cfg_path else config.config_path()
    c = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if c.get("scope") is not None:
        return {"status": "ok", "changed": False, "config": str(p)}
    if state_chats is None:
        with contextlib.closing(db.connect(c)) as d:
            state_chats = [
                {"chat_id": r[0], "name": r[1]}
                for r in d.execute("select chat_id,name from watched_chats where active=1")
            ]
    c["scope"] = {
        "include_chats": [],
        "pending_chats": [
            {"chat_id": x["chat_id"], "name": x.get("name"), "external": bool(x.get("external"))} for x in state_chats
        ],
    }
    if not dry_run:
        p.write_text(yaml.safe_dump(c, allow_unicode=True, sort_keys=False), encoding="utf-8", newline="\n")
    return {
        "status": "ok",
        "changed": True,
        "dry_run": dry_run,
        "config": str(p),
        "scope": c["scope"],
        "note": "pending_chats 不会被监听，请让用户逐个确认后移入 include_chats",
    }


def prefill(local_file, cfg_path=None):
    """把本地（不入库）文件里的群预填进本地 config 的 include_chats，视为已确认。真实群 ID 只存在于本地文件和本地 config。"""
    p = Path(cfg_path) if cfg_path else config.config_path()
    c = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    chats = json.loads(Path(local_file).read_text(encoding="utf-8"))
    sc = c.setdefault("scope", {})
    inc = sc.setdefault("include_chats", [])
    have = {x["chat_id"] for x in inc}
    for x in chats:
        if x["chat_id"] not in have:
            inc.append(
                {"chat_id": x["chat_id"], "name": x.get("name"), "external": bool(x.get("external")), "confirmed": True}
            )
    sc["pending_chats"] = [x for x in sc.get("pending_chats") or [] if x["chat_id"] not in {y["chat_id"] for y in inc}]
    p.write_text(yaml.safe_dump(c, allow_unicode=True, sort_keys=False), encoding="utf-8", newline="\n")
    return {"status": "ok", "config": str(p), "include_chats": len(inc)}
