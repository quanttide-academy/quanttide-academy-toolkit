"""Todoist：父任务=标题+DDL+优先级+标签；复选框=子任务（不设日期）；DDL 依据、链接、关联、备注写进描述。
令牌只从环境变量读取（todo.token_env）；没有令牌时为 connector 模式，只返回映射结果，由 bot 用 Todoist 连接器写入。"""

import datetime
import json
import urllib.request

from feishu_workflows.core import db
from feishu_workflows.intent import roles
from feishu_workflows.intent.item import description, labels, resolve, task_title
from feishu_workflows.settings import secret

from .base import Adapter


class PartialWrite(RuntimeError):
    def __init__(self, pid, done):
        super().__init__(f"父任务 {pid} 已建，子任务未写全")
        self.pid, self.done = pid, done


PRI = {"P1": 4, "P2": 3, "P3": 2, "P4": 1}


class TodoistAdapter(Adapter):
    def describe(self):
        return {
            "priority": True,
            "labels": True,
            "due": True,
            "ddl": True,
            "remind": False,
            "comment": True,
            "subtasks": True,
        }

    def _tok(self):
        return secret(self.t.get("token_env", "TODOIST_API_TOKEN"))

    def map(self, item):
        """日期→due，截止→deadline，提醒→reminder；标签按 item.labels() 推导；全部依据写描述。"""
        parent = {
            "content": task_title(item, self.cfg),
            "description": description(item, self.cfg),
            "labels": labels(item, self.cfg),
        }
        if item.get("priority"):
            parent["priority"] = PRI[item["priority"]]
        if item.get("date"):
            parent["due_date"] = item["date"]
        dl = roles.self_ddl(item, self.cfg)
        if dl:
            parent["deadline_date"] = dl  # 只放本人的 DDL；其他人的写进描述
        if self.t.get("project_id"):
            parent["project_id"] = self.t["project_id"]
        return {
            "parent": parent,
            "reminder": item.get("remind"),
            "subtasks": [{"content": s} for s in resolve(item, self.cfg)["subtasks"]],
        }

    def _req(self, method, path, data=None):
        r = urllib.request.Request(
            "https://api.todoist.com/rest/v2" + path,
            method=method,
            data=json.dumps(data).encode("utf-8") if data else None,
            headers={"Authorization": "Bearer " + self._tok(), "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(r, timeout=30) as resp:
            return json.loads(resp.read() or b"null")

    def check(self):
        if not self._tok():
            return True, "未设令牌环境变量：connector 模式，由 bot 的 Todoist 连接器写入"
        try:
            self._req("GET", "/projects")
            return True, "REST 连通"
        except Exception as e:
            return False, f"Todoist 连不上：{type(e).__name__}"  # noqa: BLE001

    def create(self, item):
        """非原子写入的续写：父任务 id 和已完成子任务序号落库到 writes 表；重试时不再建父任务、不重复子任务。"""
        m = self.map(item)
        if not self._tok():
            return None, json.dumps(m, ensure_ascii=False)
        fp = item.get("fingerprint") or ("title:" + item["title"])
        d = db.connect(self.cfg)

        def ts():
            return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        def save(pid, done, st):
            with d:
                d.execute(
                    """insert into writes(fingerprint,provider,parent_id,subs_done,status,updated_at) values(?,?,?,?,?,?) on conflict(fingerprint) do update set provider=excluded.provider,
                parent_id=excluded.parent_id,subs_done=excluded.subs_done,status=excluded.status,updated_at=excluded.updated_at""",
                    (fp, "todoist", pid, json.dumps(sorted(done)), st, ts()),
                )

        try:
            r = d.execute("select parent_id,subs_done,status from writes where fingerprint=?", (fp,)).fetchone()
            pid = r[0] if r else None
            done = set(json.loads(r[1] or "[]")) if r else set()
            if r and r[2] == "done":
                return pid, None
            if not pid:
                pid = self._req("POST", "/tasks", m["parent"])["id"]
                save(pid, done, "partial")  # 先落库父任务 id
            for i, s in enumerate(m["subtasks"]):
                if i in done:
                    continue
                try:
                    self._req("POST", "/tasks", {**s, "parent_id": pid})
                except Exception as e:
                    save(pid, done, "partial")
                    raise PartialWrite(pid, sorted(done)) from e
                done.add(i)
                save(pid, done, "partial")
            save(pid, done, "done")
        finally:
            d.close()
        if m["reminder"]:
            item["_note_reminder"] = "REST 模式不写提醒，已写入描述"
        return pid, None

    def comment(self, eid, text):
        if not self._tok():
            return {"task_id": eid, "content": text}
        return self._req("POST", "/comments", {"task_id": eid, "content": text})
