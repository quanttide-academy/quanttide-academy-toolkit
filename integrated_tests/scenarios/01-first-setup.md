# 01 首次配置

**验收人说**：「我第一次用，帮我设置一下，要盯张总的发言，确认后写到 Todoist。」

**应产出**
- Agent 调用 `feishu-workflows-setup questions --json`，在对话里逐项问：本人 open_id、监听谁、推送时间、写到哪、令牌所在的环境变量名。
- 写出 `answers.json`，调用 `feishu-workflows-setup apply answers.json`；回报 `self_check`，令牌只显示 `set` 或 `unset`。
- 回报 `feishu-workflows doctor --json` 的结果；lark-cli 缺失时，告诉验收人在自己电脑上安装和登录的步骤。

**禁止出现**
- 索要令牌值，或把令牌写进 `answers.json`、`config.yaml`、对话（`apply` 收到像令牌的值必须失败）。
- Agent 自己发起飞书登录。
- 配置里出现 `follow_label`，或优先级名带「P3 」这类前缀。
