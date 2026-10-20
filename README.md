# feishu-workflows

本仓库是供 **Workbuddy / Grok Bot / Cursor** 直接加载安装的飞书工作流插件包（底层接驳飞书官方 `lark-cli` 已配好的 **`Jerry 的 Grok Bot`** 应用），承接群聊意图转待办（`intent`）、重点人员跨群与私聊跟踪（`watch`）、部门架构与群聊管理（`org`：拉人、踢人、设/撤管理员、改群名、转让群主、建群、解散群）三大协作流程。  

> **全程零命令行**：你不需要自己打开终端敲命令。直接把本仓库作为插件/工作区装进 **Workbuddy**（或把 `README.md` / [AGENTS.md](AGENTS.md) 拖进对话框），全程在聊天窗口里用大白话操作即可。  

## quick-start

1. **装入 Workbuddy 并自动初始化**：在 Workbuddy 中打开本仓库，发送 **「按 [AGENTS.md](AGENTS.md) 帮我安装环境并初始化配置」**；Workbuddy 会自动装好依赖并弹出飞书二维码，你只需扫码选择 **「使用已有应用」→ 选 `Jerry 的 Grok Bot`**，再扫码点一次个人账号「授权」。
2. **对话式完成首次设置**：授权后对 Workbuddy 说 **「第一次用，帮我设置一下」**（AI 会按 [src/feishu_workflows/core/config.example.yaml](src/feishu_workflows/core/config.example.yaml) 在对话框里问你称呼、拉出你的群供勾选白名单、询问待办存哪里）。
3. **日常直接在对话框吩咐 AI**：设置完成后，按 [integrated_tests/scenarios/README.md](integrated_tests/scenarios/README.md) 或下方场景表直接发消息使用。

## 仓库结构

```text
feishu-workflows/
├── README.md                # 插件简介、Workbuddy 零命令上手与对话示例
├── AGENTS.md                # Workbuddy / AI Agent 自动执行的唯一权威指令手册
├── ROADMAP.md               # 架构设计与路线图约定
├── CHANGELOG.md             # 版本变更记录
├── pyproject.toml           # 插件包定义、命令入口与依赖配置
├── src/feishu_workflows/    # 核心源码（cli/ setup/ core/ intent/ watch/ org/）
├── tests/                   # 单元测试与仓库安全守卫
├── integrated_tests/        # 端到端集成测试与验收场景脚本
└── scripts/                 # 状态库迁移、敏感词哈希生成与提交校验脚本
```

## 核心场景与对话指令

| **业务场景** | **功能说明** | **在 Workbuddy 对话框直接说的话** |
| :-- | :-- | :-- |
| 定向消息拉取与意图提炼 | 按指定时间段（几号几点几分至几点）、指定群聊与指定发言人拉取全部发言，提炼工作意图并评估是否生成待办卡片 | 「拉取研发群今天 09:00 到 18:00 张三的所有发言，提炼工作意图并判断哪些要做待办」 |
| 卡片口头调优与角色重算 | 对候选卡片直接口头修改字段、补充上下文重算职责、转交他人或将资讯升格为待办 | 「`#1 修改：截止改到周五，加子任务：发通知`」<br>「`#2 说明：我负责评审，小李负责执行`」<br>「`指派 #3 张三`」 / 「`升格 #4 我来办`」 |
| 待办逐条确认与写入 | 经本人明确确认后写入本地待办或 Todoist，无需跟进的条目直接否决或中止本轮 | 「`#1 写入`」 / 「`全部写入` → `确认`」<br>「`否决 2`」 / 「`停一下，这轮不要了`」 |
| 群聊治理与组织架构对齐 | 统一修改群名称、设置或撤销群管理员、按部门架构将指定成员拉入或移出群聊、建群或解散群（审批单聊发「`批准 <计划号>`」后执行） | 「帮我把这几个群的名称按部门对齐，设置小李为管理员，并把新入职成员拉进对应部门群」 |

## 常见异常与处理方式

| **出现的异常提示** | **原因** | **处理方式（对 Workbuddy 说或后台执行）** |
| :-- | :-- | :-- |
| `lark-cli 退出码 3` / `token expired` / `no token` | 飞书个人登录过期或未登录 | 对 AI 说「帮我重新发起飞书登录授权」（后台执行 `lark-cli auth login --recommend`），扫码点授权 |
| `The specified app is not enabled` | 绑错了未启用的空白应用 | 对 AI 说「重新绑定飞书应用」（后台执行 `lark-cli config init`），扫码选 **已有应用 `Jerry 的 Grok Bot`** 后重新授权 |
| 黄字 `[WARN] proxy detected: https_proxy=...` | 电脑开了代理软件（Clash 等） | 让 AI 设置环境变量 `LARK_CLI_NO_PROXY_WARN=1`（静默警告）或 `LARK_CLI_NO_PROXY=1`（强制直连飞书） |
