"""org 写操作：全仓库唯一的飞书写入点。只接受「已批准计划里的某一条」（plan_id + 序号），自己从 state.db 取条目，不接受任意请求。
每条写之前、之后各记一行 org_ops；幂等键 = sha256(plan_id|序号|条目)，已成功的条目重放时跳过。org.enabled 为 false 时不构造写客户端。"""

import hashlib
import json
import subprocess

from feishu_workflows.core.lark import find
from feishu_workflows.org import conf as C
from feishu_workflows.org.plan import EXTRA_KINDS

DEFAULT_KINDS = {"add_member", "remove_member", "set_admin", "unset_admin", "rename"}


class WriteRefused(RuntimeError):
    pass


class WriterDisabled(WriteRefused):
    pass


def request(it):
    """条目 → 写请求（方法、路径、参数、请求体）。"""
    c = it["chat_id"]
    p = it.get("person")
    q = {"member_id_type": "open_id"}
    return {
        "add_member": ("POST", f"/open-apis/im/v1/chats/{c}/members", q, {"id_list": [p]}),
        "remove_member": ("DELETE", f"/open-apis/im/v1/chats/{c}/members", q, {"id_list": [p]}),
        "set_admin": ("POST", f"/open-apis/im/v1/chats/{c}/managers/add_managers", q, {"manager_ids": [p]}),
        "unset_admin": ("POST", f"/open-apis/im/v1/chats/{c}/managers/delete_managers", q, {"manager_ids": [p]}),
        "rename": ("PATCH", f"/open-apis/im/v1/chats/{c}", {}, {"name": it.get("name")}),
        "transfer": ("PATCH", f"/open-apis/im/v1/chats/{c}", {"user_id_type": "open_id"}, {"owner_id": p}),
        "create": ("POST", "/open-apis/im/v1/chats", {}, {"name": it.get("name")}),
        "disband": ("DELETE", f"/open-apis/im/v1/chats/{c}", {}, None),
    }[it["kind"]]


def _real_runner(cfg):
    if not C.load(cfg).enabled:
        raise WriterDisabled("org.enabled 为 false：不构造写客户端")
    exe = find(cfg)

    def run(req):
        m, path, q, body = req
        args = [exe, "api", m, path, "--as", "user", "--params", json.dumps(q)] + (
            ["--data", json.dumps(body, ensure_ascii=False)] if body is not None else []
        )
        r = subprocess.run(
            args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, check=False
        )
        if r.returncode != 0:
            raise WriteRefused(f"写入失败，退出码 {r.returncode}")
        return {"ok": True}

    return run


def op_key(pid, it):
    return hashlib.sha256(
        f"{pid}|{it['idx']}|{json.dumps(it, ensure_ascii=False, sort_keys=True)}".encode()
    ).hexdigest()


def execute(cfg, d, plan_id, idx, guard, runner=None):
    """guard：{held_chats, protected}，由 apply 现场算出。返回 {"replayed": bool, "result": ...}。"""
    r = d.execute(
        "select items_json,approved_items,status from org_plans where plan_id=? and is_deleted=0", (plan_id,)
    ).fetchone()
    if not r or r[2] not in ("approved", "applying"):
        raise WriteRefused("计划未批准，拒绝写入")
    if idx not in json.loads(r[1] or "[]"):
        raise WriteRefused(f"第 {idx} 条未获批准，拒绝写入")
    it = next((x for x in json.loads(r[0]) if x["idx"] == idx), None)
    if it is None:
        raise WriteRefused("计划里没有这一条")
    oc = C.load(cfg)
    if it["kind"] not in DEFAULT_KINDS and not (it["kind"] in EXTRA_KINDS and oc.allow.get(it["kind"])):
        raise WriteRefused(f"动作 {it['kind']} 未在 config 中打开")
    if it["kind"] == "add_member" and it.get("external"):
        raise WriteRefused("外部成员不能被拉进内部群")
    if it["chat_id"] in guard["held_chats"]:
        raise WriteRefused("该群标了暂缓，拒绝写入")
    if it["kind"] in ("remove_member", "unset_admin", "transfer") and it.get("person") in guard["protected"]:
        raise WriteRefused("保护名单里的人不能被移出或撤销管理员")
    key = op_key(plan_id, it)
    req = request(it)
    dig = hashlib.sha256(json.dumps(req, ensure_ascii=False).encode()).hexdigest()[:16]
    if d.execute("select 1 from org_ops where op_key=? and phase='after' and result='ok'", (key,)).fetchone():
        return {"replayed": True, "result": "ok"}
    run = runner or _real_runner(cfg)
    with d:
        d.execute(
            "insert or ignore into org_ops(plan_id,idx,op_key,phase,request_digest) values(?,?,?,'before',?)",
            (plan_id, idx, key, dig),
        )
    try:
        run(req)
        res = "ok"
    except Exception as e:
        res = f"error: {type(e).__name__}"  # noqa: BLE001  不记响应内容，避免泄露
    with d:
        d.execute(
            "insert into org_ops(plan_id,idx,op_key,phase,request_digest,result) values(?,?,?,'after',?,?) on conflict(op_key,phase) do update set result=excluded.result",
            (plan_id, idx, key, dig, res),
        )
    if res != "ok":
        raise WriteRefused(f"第 {idx} 条写入失败：{res}")
    return {"replayed": False, "result": res}
