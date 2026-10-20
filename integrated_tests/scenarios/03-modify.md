# 03 修改卡片

**前置**：完成 02 到推送为止。

**验收人说**：「#1 改一下，截止改到 10-30。」然后「#1 写入」。

**应产出**
- `reply` 返回 `modify`；`feishu-workflows next` 返回 `llm_edit`；Agent 只改 `topics.json` 里 no=1 的条目，重新 `validate` → `render` → 推送新卡片。
- 新卡片推送前，验收人说「#1 写入」会被追问「卡片改过」，不确认。
- 新卡片推送后「#1 写入」才生效，`writes.json` 里的 `version` 与新 `versions.json` 一致。

**追加**：验收人再说「#2 说明：报名表其实周四就要」。

- `reply` 返回 `explain`，不改变 #2 的确认状态；Agent 判断要改截止，只改 no=2，重新 `validate` → `render`，卡片版本变化，重新推送。
- Agent 传给 `reply` 的是验收人原话，一字不改。

**禁止出现**
- 手工改 `cards.txt`；用旧版本确认写入；把「说明」当作确认。
