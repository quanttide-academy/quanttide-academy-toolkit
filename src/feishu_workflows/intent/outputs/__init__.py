import importlib

from feishu_workflows.core import db

BUILTIN = {
    "markdown": "feishu_workflows.intent.outputs.markdown.MarkdownAdapter",
    "todoist": "feishu_workflows.intent.outputs.todoist.TodoistAdapter",
    "export": "feishu_workflows.intent.outputs.export.ExportAdapter",
}


class NotConfirmed(PermissionError):
    pass


class Gate:
    """确认闸门：create/comment 只接受 topics 表里 confirmed=1 的议题（按 item["fingerprint"]）。"""

    def __init__(self, inner, cfg):
        self.inner, self.cfg = inner, cfg

    def _ok(self, fp):
        r = None
        if fp:
            c = db.connect(self.cfg)
            try:
                r = c.execute("select confirmed from topics where fingerprint=?", (fp,)).fetchone()
            finally:
                c.close()
        if not r or r[0] != 1:
            raise NotConfirmed(f"议题未经确认，拒绝写入：{fp}")

    def check(self):
        return self.inner.check()

    def describe(self):
        return self.inner.describe()

    def create(self, item):
        self._ok(item.get("fingerprint"))
        return self.inner.create(item)

    def comment(self, fingerprint, external_id, text):
        self._ok(fingerprint)
        return self.inner.comment(external_id, text)


def load(cfg):
    t = cfg.get("todo") or {"provider": "markdown"}
    path = t.get("module") if t["provider"] == "custom" else BUILTIN[t["provider"]]
    mod, cls = path.rsplit(".", 1)
    return Gate(getattr(importlib.import_module(mod), cls)(t, cfg), cfg)
