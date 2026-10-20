"""生成各系统定时任务模板（只生成文本；安装需使用者确认）。触发时间按本机时区由北京时间换算。"""

import datetime
import sys
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from feishu_workflows.settings import TZ_NAME


def local_times(bj_times, local_tz=None):
    today = datetime.date.today()
    res = []
    for t in bj_times:
        h, m = map(int, t.split(":"))
        dt = datetime.datetime(today.year, today.month, today.day, h, m, tzinfo=ZoneInfo(TZ_NAME)).astimezone(local_tz)
        res.append((dt.hour, dt.minute))
    return res


def command(batch_expr="auto"):
    return [sys.executable, "-m", "feishu_workflows.cli", "fetch", batch_expr]


def cron(times):
    cmd = " ".join(f'"{c}"' for c in command())
    return "\n".join(f"{m} {h} * * * {cmd}" for h, m in times)


def launchd(times, label="com.feishu-intent.fetch"):
    args = "".join(f"<string>{escape(c)}</string>" for c in command())
    cal = "".join(
        f"<dict><key>Hour</key><integer>{h}</integer><key>Minute</key><integer>{m}</integer></dict>" for h, m in times
    )
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict><key>Label</key><string>{label}</string><key>ProgramArguments</key><array>{args}</array><key>StartCalendarInterval</key><array>{cal}</array></dict></plist>\n'


def schtasks(times):
    c = command()
    trig = "".join(
        f"<CalendarTrigger><StartBoundary>2026-01-01T{h:02d}:{m:02d}:00</StartBoundary><ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>"
        for h, m in times
    )
    return f'<?xml version="1.0" encoding="UTF-16"?>\n<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><Triggers>{trig}</Triggers><Actions><Exec><Command>{escape(c[0])}</Command><Arguments>{escape(" ".join(chr(34) + x + chr(34) for x in c[1:]))}</Arguments></Exec></Actions></Task>\n'


def for_platform(times, plat=None):
    plat = plat or sys.platform
    if plat.startswith("win"):
        return "schtasks", schtasks(times), "schtasks /Create /TN feishu-intent /XML <文件路径>"
    if plat == "darwin":
        return (
            "launchd",
            launchd(times),
            "保存到 ~/Library/LaunchAgents/com.feishu-intent.fetch.plist 后执行 launchctl load <该文件>",
        )
    return "cron", cron(times), "执行 crontab -e，把上面几行追加进去"
