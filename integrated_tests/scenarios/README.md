# 验收脚本

给一个干净的 Agent，只提供本仓库，不给额外说明。验收人按下面的脚本用自然语言和它对话，逐条核对「应产出」和「禁止出现」。全部使用 [tests/fixtures/](../examples/) 里的合成数据（虚构，不是真实群消息），不联网、不写任何待办。

准备：复制一份 `src/quanttide_academy_toolkit/core/config.example.yaml`，`paths` 指向临时目录，`todo.provider` 设为 `todoist`、`token_env` 设为一个未设置的变量名（这样只会生成 `writes.json`，不会真实写入）。用 `FEISHU_INTENT_CONFIG` 指向它。离线采集用 `feishu-workflows fetch <batch> --from tests/fixtures/messages.json`。

| **脚本** | **场景** |
| :--- | :--- |
| [01-first-setup.md](01-first-setup.md) | 首次配置 |
| [02-one-round.md](02-one-round.md) | 完整一轮 |
| [03-modify.md](03-modify.md) | 修改卡片 |
| [04-reject.md](04-reject.md) | 否决 |
| [05-resume.md](05-resume.md) | 中途失败后续跑 |
| [06-injection.md](06-injection.md) | 注入攻击 |

## 上线前真实环境验收（需本人在场）
- **私聊来源真实端到端**：权限 `im:message.p2p_msg:get_as_user` 开通、本人最终签字后，对一个开启私聊来源的目标（`dm_chat_id` 手填在本地配置）跑一次 `watch poll --dry-run`：核验 p2p 与成员通过、只读、只输出计数；再故意填错 `dm_chat_id`，确认报错停止。
- **org 首次真实 apply**：由本人亲自批准计划后执行，见 [ROADMAP.md](../../ROADMAP.md)。
