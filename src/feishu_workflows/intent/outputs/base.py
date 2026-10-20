"""适配器接口。item 统一结构：
{title, note, due, remind, priority: P1-P4|None, labels: [], sources: [{chat,time,account,link,message_id}], calendar: bool}
只处理已确认条目；补评论也算写入。不支持的字段降级写进备注，不报错。"""

from feishu_workflows.core import paths


class Adapter:
    def __init__(self, tcfg, cfg):
        self.t, self.cfg = tcfg, cfg
        self.dir = paths.data_dir(cfg)
        self.dir.mkdir(parents=True, exist_ok=True)

    def check(self):
        raise NotImplementedError  # 只检查配置和连通，不写入；返回 (ok, 说明)

    def create(self, item):
        raise NotImplementedError  # 返回 (external_id, url)

    def comment(self, external_id, text):
        raise NotImplementedError

    def describe(self):
        return {"priority": False, "labels": False, "due": False, "remind": False, "comment": False, "subtasks": False}

    def degrade(self, item):
        caps = self.describe()
        extra = []
        for k, name in [("priority", "优先级"), ("labels", "标签"), ("ddl", "截止"), ("remind", "提醒")]:
            if item.get(k) and not caps.get({"ddl": "due"}.get(k, k)):
                extra.append(f"{name}：{item[k] if not isinstance(item[k], list) else '、'.join(item[k])}")
        return "\n".join([item.get("note") or ""] + extra).strip()
