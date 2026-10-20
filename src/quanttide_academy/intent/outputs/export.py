"""通用导出：format = csv | ics | webhook。webhook 签名密钥只从环境变量读（todo.secret_env）。"""

import csv
import hashlib
import hmac
import json
import urllib.request
import uuid
from urllib.parse import urlsplit

from quanttide_academy.intent.item import description
from quanttide_academy.settings import secret

from .base import Adapter


def csv_safe(v):
    v = str(v or "")
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v


def ics_esc(v):
    return (
        str(v or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r", "")
        .replace("\n", "\\n")
    )


class ExportAdapter(Adapter):
    def describe(self):
        f = self.t.get("format", "csv")
        return {
            "priority": f != "ics",
            "labels": f != "ics",
            "due": True,
            "remind": f == "webhook",
            "comment": f == "webhook",
        }

    def _path(self, ext):
        return self.dir / self.t.get("file", f"confirmed.{ext}")

    def check(self):
        f = self.t.get("format", "csv")
        if f == "webhook":
            if not self.t.get("url"):
                return False, "缺 todo.url"
            u = urlsplit(self.t["url"])
            return True, f"将 POST 到 {u.scheme}://{u.hostname}/***（不在 check 中发送）"
        return True, f"写本地文件 {self._path(f)}"

    def create(self, item):
        f = self.t.get("format", "csv")
        eid = uuid.uuid4().hex[:12]
        if f == "csv":
            p = self._path("csv")
            new = not p.exists()
            with open(p, "a", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh)
                if new:
                    w.writerow(["id", "title", "priority", "labels", "due", "subtasks", "description"])
                w.writerow(
                    [
                        csv_safe(x)
                        for x in [
                            eid,
                            item["title"],
                            item.get("priority") or "",
                            "、".join(item.get("labels") or []),
                            item.get("ddl") or "",
                            "\n".join("- [ ] " + t for t in item.get("subtasks", [])),
                            description(item, self.cfg),
                        ]
                    ]
                )
        elif f == "ics":
            if not item.get("ddl"):
                return None, "无日期，ICS 跳过"
            d = item["ddl"].replace("-", "")
            desc = ics_esc(description(item, self.cfg) + "\n子任务：\n" + "\n".join(item.get("subtasks", [])))
            with open(self._path("ics"), "a", encoding="utf-8", newline="\n") as fh:
                fh.write(
                    f"BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:{eid}\nDTSTART;VALUE=DATE:{d}\nSUMMARY:{ics_esc(item['title'])}\nDESCRIPTION:{desc}\nEND:VEVENT\nEND:VCALENDAR\n"
                )
        else:
            self._post({"type": "create", "id": eid, "item": item})
        return eid, None

    def comment(self, eid, text):
        if self.t.get("format") != "webhook":
            raise NotImplementedError("该格式不支持评论")
        self._post({"type": "comment", "id": eid, "text": text})

    def _post(self, payload):
        b = json.dumps(payload, ensure_ascii=False).encode()
        h = {"Content-Type": "application/json"}
        sec = secret(self.t.get("secret_env"))
        if sec:
            h["X-Signature"] = hmac.new(sec.encode(), b, hashlib.sha256).hexdigest()
        urllib.request.urlopen(urllib.request.Request(self.t["url"], data=b, headers=h, method="POST"), timeout=30)
