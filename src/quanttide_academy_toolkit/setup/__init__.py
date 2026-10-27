#!/usr/bin/env python3
"""首次安装向导：问答后生成 config.yaml。密钥只记环境变量名，不写明文。"""

import json
import sys
from pathlib import Path

import yaml

from quanttide_academy_toolkit.core import config
from quanttide_academy_toolkit.intent import collect, outputs
from quanttide_academy_toolkit.settings import PKG, ROOT
from quanttide_academy_toolkit.setup.apply import apply, migrate, prefill
from quanttide_academy_toolkit.setup.questions import QUESTIONS, SECRET_RE, ask

__all__ = ["QUESTIONS", "SECRET_RE", "apply", "ask", "interactive", "main", "migrate", "prefill"]


def interactive():
    c = yaml.safe_load((PKG / "core" / "config.example.yaml").read_text(encoding="utf-8"))
    c["self_open_id"] = ask("你的飞书 open_id（lark-cli 用你本人账号登录后可查）")
    c["watch"] = []
    while True:
        n = ask("要监听的人的名字（留空结束）")
        if not n:
            break
        accs = {}
        while True:
            o = ask(f"  {n} 的 open_id（留空结束）")
            if not o:
                break
            accs[o] = ask("  这个账号的备注", "内部")
        c["watch"].append({"name": n, "accounts": accs})
    c["schedule"]["push"] = ask("每天几点推送（逗号分隔）", "12:00,18:00").split(",")
    if ask("确认过的条目要写进待办软件吗？(y/n)", "n").lower() != "y":
        c["todo"] = {"provider": "markdown", "file": "confirmed.md"}
    else:
        p = ask("用哪个：todoist / export / custom", "todoist")
        if p == "todoist":
            c["todo"] = {
                "provider": "todoist",
                "token_env": ask("Todoist 令牌所在的环境变量名", "TODOIST_API_TOKEN"),
                "project_id": ask("项目 ID（留空=收件箱）") or None,
            }
        elif p == "export":
            f = ask("格式 csv / ics / webhook", "csv")
            c["todo"] = {"provider": "export", "format": f}
            if f == "webhook":
                c["todo"].update(url=ask("webhook URL"), secret_env=ask("签名密钥的环境变量名（可留空）") or None)
        else:
            c["todo"] = {"provider": "custom", "module": ask("适配器类路径，如 mypkg.adapter.MyAdapter")}
    c["calendar"] = {
        "provider": ask("日历写到哪里：none / ics（google 目前只支持 bot 连接器模式，向导不提供）", "none")
    }
    fp = ask("外部跟进清单路径（没有就留空）")
    c["followups"] = {"path": fp or None}
    ok, msg = outputs.load(c).check()
    print("连通检查：", ok, msg)
    (ROOT / "config.yaml").write_text(
        yaml.safe_dump(c, allow_unicode=True, sort_keys=False), encoding="utf-8", newline="\n"
    )
    print("已写入 config.yaml")
    print("第一期只支持由 bot 触发；本地自动运行属于第二期，向导暂不生成定时任务。")


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    cfgarg = a[a.index("--config") + 1] if "--config" in a else None
    if a[:1] == ["migrate"]:
        print(json.dumps(migrate(cfgarg, dry_run="--dry-run" in a), ensure_ascii=False))
    elif a[:1] == ["prefill"]:
        print(json.dumps(prefill(a[1], cfgarg), ensure_ascii=False))
    elif a[:1] == ["chats"]:
        cs = collect.list_chats(config.load())
        print(json.dumps({"chats": [{**c, "selected": False} for c in cs]}, ensure_ascii=False))
    elif a[:1] == ["questions"]:
        print(json.dumps({"questions": QUESTIONS}, ensure_ascii=False))
    elif a[:1] == ["apply"] or a[:1] == ["--answers"]:
        print(
            json.dumps(
                apply(
                    json.loads(Path(a[1]).read_text(encoding="utf-8")),
                    a[3] if len(a) > 3 and a[2] == "--config" else None,
                ),
                ensure_ascii=False,
            )
        )
    else:
        interactive()


if __name__ == "__main__":
    main()
