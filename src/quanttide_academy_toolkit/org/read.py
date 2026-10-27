"""org 只读层：部门树与部门成员用应用身份（--as bot），群信息与群成员用用户身份；全部 GET，经 core/lark。
读不到部门（接口报错或返回空）一律抛 DeptReadError，绝不当成部门为空。"""

import json

from quanttide_academy_toolkit.core import lark as larkcli


class DeptReadError(RuntimeError):
    pass


class ChatReadError(RuntimeError):
    pass


def _items(pages):
    return [x for p in pages for x in (p.get("data") or {}).get("items") or []]


def dept_tree(cfg) -> list:
    """[{id, name, parent}]（open_department_id）。"""
    try:
        pages = larkcli.call(
            cfg,
            "api",
            "GET",
            "/open-apis/contact/v3/departments/0/children",
            "--as",
            "bot",
            "--page-all",
            "--params",
            json.dumps({"fetch_child": True, "page_size": 50, "department_id_type": "open_department_id"}),
        )
    except larkcli.LarkError as e:
        raise DeptReadError(f"读部门树失败：{e}") from e
    out = [
        {"id": d.get("open_department_id"), "name": d.get("name"), "parent": d.get("parent_department_id")}
        for d in _items(pages)
        if d.get("open_department_id")
    ]
    if not out:
        raise DeptReadError("部门树为空：按读取失败处理，不当成没有部门")
    return out


def dept_members(cfg, did) -> set:
    """部门直属成员 open_id（应用身份）。"""
    try:
        pages = larkcli.call(
            cfg,
            "api",
            "GET",
            "/open-apis/contact/v3/users/find_by_department",
            "--as",
            "bot",
            "--page-all",
            "--params",
            json.dumps(
                {
                    "department_id": did,
                    "department_id_type": "open_department_id",
                    "user_id_type": "open_id",
                    "page_size": 50,
                }
            ),
        )
    except larkcli.LarkError as e:
        raise DeptReadError(f"读部门成员失败：{e}") from e
    return {u["open_id"] for u in _items(pages) if u.get("open_id")}


def chat_info(cfg, cid) -> dict:
    try:
        r = larkcli.call(
            cfg, "api", "GET", f"/open-apis/im/v1/chats/{cid}", "--as", "user", "--params", '{"user_id_type":"open_id"}'
        )
    except larkcli.LarkError as e:
        raise ChatReadError(f"读群信息失败：{e}") from e
    d = r[0].get("data") or {}
    return {"name": d.get("name"), "owner": d.get("owner_id"), "tenant_key": d.get("tenant_key")}


def chat_members(cfg, cid) -> dict:
    """{open_id: tenant_key}（用户身份）。"""
    try:
        pages = larkcli.call(
            cfg,
            "api",
            "GET",
            f"/open-apis/im/v1/chats/{cid}/members",
            "--as",
            "user",
            "--page-all",
            "--params",
            '{"member_id_type":"open_id","page_size":100}',
        )
    except larkcli.LarkError as e:
        raise ChatReadError(f"读群成员失败：{e}") from e
    return {x["member_id"]: x.get("tenant_key") for x in _items(pages) if x.get("member_id")}


def approval_message(cfg, message_id) -> dict:
    """审批消息（应用身份 GET 单条消息）：返回 {message_id, chat_id, sender, sender_type, create_ms, msg_type, text, deleted}。"""
    try:
        r = larkcli.call(
            cfg,
            "api",
            "GET",
            f"/open-apis/im/v1/messages/{message_id}",
            "--as",
            "bot",
            "--params",
            '{"user_id_type":"open_id"}',
        )
    except larkcli.LarkError as e:
        raise ChatReadError(f"读审批消息失败：{e}") from e
    it = next(iter(_items(r)), None)
    if not it:
        raise ChatReadError("审批消息不存在或不可见")
    try:
        body = json.loads((it.get("body") or {}).get("content") or "{}")
    except ValueError:
        body = {}
    s = it.get("sender") or {}
    return {
        "message_id": it.get("message_id"),
        "chat_id": it.get("chat_id"),
        "sender": s.get("id"),
        "sender_type": s.get("sender_type"),
        "create_ms": int(it.get("create_time") or 0),
        "msg_type": it.get("msg_type"),
        "text": body.get("text") if isinstance(body, dict) else None,
        "deleted": bool(it.get("deleted")),
    }


def my_chats(cfg) -> list:
    """本人所在的群（用户身份，只读快捷命令）：[{chat_id, name}]。"""
    try:
        r = larkcli.call(cfg, "im", "+chat-list", "--as", "user")
    except larkcli.LarkError as e:
        raise ChatReadError(f"读群列表失败：{e}") from e
    return [{"chat_id": c["chat_id"], "name": c.get("name")} for c in (r[0].get("data") or {}).get("chats") or []]
