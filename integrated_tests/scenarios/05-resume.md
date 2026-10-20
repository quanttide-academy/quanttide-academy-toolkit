# 05 中途失败后续跑

**前置**：02 中「#1 写入」之后。

**验收人说**：「写吧。」（Agent 执行父任务后，把第 2 个子任务报 `mark-written <key> fail`，然后假装会话中断。）新会话里说：「接着上次的继续。」

**应产出**
- 新会话的 Agent 先跑 `feishu-workflows next`，得到 `write`；再次 `write` 只出未完成的子任务和提醒，`parent_ext_id` 是第一次记下的 id。
- 全部 `mark-written` 后 `write` 的 `actions` 为空，`next` 返回 `commit`。

**禁止出现**
- 第二个父任务动作；重复已完成的子任务。
