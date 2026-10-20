import datetime
from zoneinfo import ZoneInfo

from feishu_workflows.intent.item import to_card, to_markdown

from .base import Adapter


class MarkdownAdapter(Adapter):
    def _f(self):
        d = self.dir / "confirmed"
        d.mkdir(exist_ok=True)
        return d / (datetime.datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d") + ".md")

    def check(self):
        return True, f"仅写本地文件 {self._f().name}"

    def describe(self):
        return {"priority": True, "labels": True, "due": True, "remind": True, "comment": True, "subtasks": True}

    def create(self, item):
        eid = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        with open(self._f(), "a", encoding="utf-8", newline="\n") as f:
            f.write("\n" + to_card(item, self.cfg) + "\n")
        with open(self._f().with_suffix(".archive.md"), "a", encoding="utf-8", newline="\n") as f:
            f.write("\n" + to_markdown(item, self.cfg) + "\n")
        return eid, None

    def comment(self, eid, text):
        with open(self._f(), "a", encoding="utf-8", newline="\n") as f:
            f.write(f"  - 补充（{eid}）：{text}\n")
