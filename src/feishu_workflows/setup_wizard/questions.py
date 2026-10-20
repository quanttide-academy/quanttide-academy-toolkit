"""首次安装向导问题表与输入工具：QUESTIONS、SECRET_RE、ask。"""

import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass  # 仅清理：stdout 不支持 reconfigure（如被测试捕获替换）时沿用原编码，不影响结果


def ask(q, d=""):
    a = input(f"{q}{f' [{d}]' if d else ''}: ").strip()
    return a or d


QUESTIONS = [
    {
        "key": "self_open_id",
        "question": "你本人的飞书 open_id 是什么？",
        "explanation": "用来判断哪些消息点了你的名字。用户在自己电脑上登录 lark-cli 后可查到；Agent 不代为登录。",
        "options": None,
        "default": None,
    },
    {
        "key": "display_name",
        "question": "你希望卡片里怎么称呼你？",
        "explanation": "卡片的摘要、子任务和备注里用这个称呼指代你，例如「小鲍」这类称呼。",
        "options": None,
        "default": None,
    },
    {
        "key": "roles",
        "question": "你在这些群里担任什么角色？（可多个，如「实训基地负责人」）",
        "explanation": "消息没有 @ 你、也没点你名字时，只能按角色推断某件事该你做，卡片会注明「按角色推断」。",
        "options": None,
        "default": [],
    },
    {
        "key": "include_chats",
        "question": "要监听哪些群？（勾选，默认一个都不选）",
        "explanation": '先运行 feishu-workflows-setup chats --json 列出你已加入的群，让用户勾选；外部群请标 external=true。程序只监听勾选的群；检测到新的部门群只会提示建议，不会自动加入。格式：[{"chat_id":"oc_xxx","name":"群名","external":false}]',
        "options": "feishu-workflows-setup chats --json",
        "default": [],
    },
    {
        "key": "watch",
        "question": "要监听谁的发言？每人给名字和一个或多个 open_id（可备注内部/外部账号）。",
        "explanation": '只拉取这些人在你所在群里的发言，只读。格式：[{"name":"张总","accounts":{"ou_xxx":"内部"}}]',
        "options": None,
        "default": None,
    },
    {
        "key": "push_times",
        "question": "每天几点给你推送待确认卡片？（北京时间）",
        "explanation": "第一期由宿主 Agent 按这个时间触发。",
        "options": None,
        "default": ["12:00", "18:00"],
    },
    {
        "key": "todo_provider",
        "question": "确认过的条目写到哪里？",
        "explanation": "markdown=只存本地文件；todoist=写 Todoist；export=导出 csv/ics/webhook；custom=自定义适配器。",
        "options": ["markdown", "todoist", "export", "custom"],
        "default": "markdown",
    },
    {
        "key": "todo_token_env",
        "question": "Todoist 令牌放在哪个环境变量里？（只告诉我变量名，不要把令牌发给我）",
        "explanation": "没设这个变量时，程序输出 writes.json，由你的 Agent 用自己的 Todoist 连接器写。只在 todo_provider=todoist 时问。",
        "options": None,
        "default": "TODOIST_API_TOKEN",
    },
    {
        "key": "todo_project_id",
        "question": "写到 Todoist 的哪个项目？（留空=收件箱）",
        "explanation": "只在 todo_provider=todoist 时问。",
        "options": None,
        "default": None,
    },
    {
        "key": "export_format",
        "question": "导出成什么格式？",
        "explanation": "只在 todo_provider=export 时问。",
        "options": ["csv", "ics", "webhook"],
        "default": "csv",
    },
    {
        "key": "followups_path",
        "question": "有没有已在跟进的事项清单（Markdown 表格）？有就给文件路径。",
        "explanation": "用于去重：清单里有的不再重复推送。留空跳过。",
        "options": None,
        "default": None,
    },
    {
        "key": "priority_names",
        "question": "待办软件里四个优先级标签分别叫什么？",
        "explanation": "程序只给每条任务加一个优先级标签，名字必须和待办软件里现有标签完全一致。",
        "options": None,
        "default": {"P1": "紧急重要", "P2": "紧急次要", "P3": "缓和重要", "P4": "缓和次要"},
    },
]
SECRET_RE = re.compile(r"(?i)(?:\b[ut]-[A-Za-z0-9._-]{16,}|bearer\s+\S+|\b[A-Za-z0-9_-]{32,}\b)")
