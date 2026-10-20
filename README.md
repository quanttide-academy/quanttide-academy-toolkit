# feishu-workflows

本仓库是架在飞书官方 `lark-cli`（已绑定应用 **`Jerry 的 Grok Bot`**）之上的安全工作流接驳包，承接群聊意图转待办（`intent`）、重点人员跨群与私聊跟踪（`watch`）、部门架构与群聊管理（`org`：拉人、踢人、设/撤管理员、改群名、转让群主、建群、解散群）三大协作流程。  

> **小白一键上手**：直接把 `README.md` 或 [AGENTS.md](AGENTS.md) 拖进 **Workbuddy / Grok Bot / Cursor / Claude Code**，发送一句 **「请按这个文件一步步带我配好并跑起来」**，AI 就会全程带你一步配通。  

## quick-start

1. **安装环境并接驳飞书 CLI**：打开电脑终端（Mac 搜 `Terminal`，Windows 搜 `PowerShell`），参照 [AGENTS.md](AGENTS.md) 依次执行下面 3 行命令：
   ```bash
   uv sync
   lark-cli config init          # 扫码后选「使用已有应用」→ 选「Jerry 的 Grok Bot」（勿选新建！）
   lark-cli auth login --recommend
   ```
2. **完成首次配置**：对 AI 说 **「第一次用，帮我设置一下」**（AI 会按 [src/feishu_workflows/core/config.example.yaml](src/feishu_workflows/core/config.example.yaml) 问你称呼、勾选白名单群、待办存哪里，选本地文件免配密钥）。
3. **跑通自检与日常对话**：运行 `uv run feishu-workflows doctor --json` 确认就绪后，按 [integrated_tests/scenarios/README.md](integrated_tests/scenarios/README.md) 或下方表格直接用大白话吩咐 AI。

## 仓库结构

```text
feishu-toolkit/
├── README.md                # 新成员快速上手、对话调优与报错秒查
├── AGENTS.md                # AI Agent 唯一权威操作手册与验证门禁
├── ROADMAP.md               # 架构设计与路线图约定
├── CHANGELOG.md             # 版本变更记录
├── pyproject.toml           # 包定义、依赖上界与 pytest/ruff 配置
├── src/feishu_workflows/    # 核心源码（cli/ setup/ core/ intent/ watch/ org/）
├── tests/                   # 单元测试与仓库安全守卫
├── integrated_tests/        # 端到端集成测试与验收场景脚本
└── scripts/                 # 状态库迁移、敏感词哈希生成与提交校验脚本
```

## 日常对话与口头调优

| **你想干嘛** | **直接对 AI 说的话** |
| :--- | :--- |
| 拉取群消息看卡片 | 「帮我看看群消息」或「跑一轮 watch 监听」 |
| 确认无误记入待办 | 「`#1 写入`」或「`全部写入`」后再回「`确认`」 |
| 不要这条直接丢弃 | 「`否决 2`」 |
| 提炼不准口头调优 | 「`#1 修改：截止改到周五，加子任务：发通知`」 |
| 补充背景重算角色 | 「`#2 说明：这件事我负责评审，小李负责执行`」 |
| 转交他人 / 资讯转待办 | 「`指派 #3 张三`」 / 「`升格 #4 我来办`」 |
| 管群 / 对齐部门成员 | 「帮我生成一份 org 部门和群对齐计划」（审批单聊发「`批准 <计划号>`」后执行） |
| 这轮不弄了随时停 | 「`停一下，这轮不要了`」 |

## 报错秒查表

| **终端报错提示** | **原因** | **直接在终端运行这行解决** |
| :--- | :--- | :--- |
| `lark-cli 退出码 3` / `token expired` / `no token` | 飞书个人登录过期或未登录 | `lark-cli auth login --recommend`（扫码点授权） |
| `The specified app is not enabled` | 绑错了未启用的空白应用 | 先跑 `lark-cli config init`（扫码选已有应用 **`Jerry 的 Grok Bot`**），再跑 `lark-cli auth login --recommend` |
| 黄字 `[WARN] proxy detected: https_proxy=...` | 电脑开了代理软件（Clash 等） | 关黄字：`export LARK_CLI_NO_PROXY_WARN=1`<br>连不上飞书时强制直连：`export LARK_CLI_NO_PROXY=1` |
