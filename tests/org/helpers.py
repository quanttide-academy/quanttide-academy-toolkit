"""org 离线夹具：可变的假 reader（不联网），以及基础配置。"""

import copy
import json
import time

from quanttide_academy_toolkit.org import approve as A
from quanttide_academy_toolkit.org import read as R
from tests.helpers import ROOT

BASE = json.loads((ROOT / "tests" / "fixtures" / "org" / "tenant.json").read_text(encoding="utf-8"))


def cfg(**org):
    o = {
        "root_department": "od_root",
        "approval_chat_id": "oc_appr",
        "mappings": [{"chat_id": "oc_a", "department": "od_a"}],
        **org,
    }
    return {"self_open_id": "ou_me", "self_tenant_key": "t", "org": o}


class Fake:
    """假 reader：data 可在测试里修改以模拟审批后情况变化；fail_dept 模拟读部门失败。"""

    def __init__(self, data=None, fail_dept=False):
        self.data = copy.deepcopy(data or BASE)
        self.fail = fail_dept
        self.calls = []
        self.messages = {}

    def dept_tree(self, cfg):
        self.calls.append("tree")
        if self.fail:
            raise R.DeptReadError("读部门树失败：模拟")
        if not self.data["tree"]:
            raise R.DeptReadError("部门树为空")
        return self.data["tree"]

    def dept_members(self, cfg, did):
        self.calls.append(("members", did))
        return set(self.data["members"].get(did, []))

    def chat_info(self, cfg, cid):
        c = self.data["chats"][cid]
        return {"name": c["name"], "owner": c["owner"]}

    def chat_members(self, cfg, cid):
        return dict(self.data["chats"][cid]["members"])

    def my_chats(self, cfg):
        return [{"chat_id": k, "name": v["name"]} for k, v in self.data["chats"].items()]

    def approval_message(self, cfg, mid):
        if mid not in self.messages:
            raise R.ChatReadError("审批消息不存在或不可见")
        return dict(self.messages[mid])


def message(f, text, **over):
    """在假 reader 里放一条审批消息（默认：本人、审批单聊、现在+60 秒、文本），返回 message_id。"""
    mid = f"om_appr_{len(f.messages)}"
    f.messages[mid] = {
        "message_id": mid,
        "chat_id": "oc_appr",
        "sender": "ou_me",
        "sender_type": "user",
        "create_ms": (int(time.time()) + 60) * 1000,
        "msg_type": "text",
        "text": text,
        "deleted": False,
        **over,
    }
    return mid


def approve(c, d, f, pl, n=None, **over):
    return A.approve(c, d, message(f, f"批准 {pl['plan_id'][:8]}" + (f" {n}" if n else ""), **over), f)
