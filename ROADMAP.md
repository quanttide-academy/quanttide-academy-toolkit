---
tags: [已阅]
date: 2026-10-20
---

# feishu-toolkit 路线图

本文是仓库唯一的设计与路线图文档：记录 watch、org 的已定设计与已完成摘要，改代码前和验收前读。本文取代此前的实施计划和需求汇总，冲突以本文为准；操作命令与硬性约束以 [AGENTS.md](AGENTS.md) 为准。  

## 目标与现状

目标是把 intent、watch、org 三个工作流修完、打包并发版，达到可验收状态。架构是一个 Python 包 `src/feishu_workflows/{core,intent,watch,org}`，入口是 cli；读飞书只经 lark-cli 的 GET，飞书写操作只在 `org/writer.py`；状态存在 SQLite 的 `state.db`，迁移按版本号逐级执行。技术栈是 Python、uv、pytest、ruff、lark-cli、SQLite。  

已完成 intent 全流程、watch、org v1.2、`state.db` v5（强制在线备份、TIMESTAMP 毫秒 Z 与 BOOLEAN CHECK、intent/watch 游标合并与同秒 `message_id` 去重）、可注入 Runner 与假 `lark-cli` 端到端回归、整仓 `ruff format` 与模块拆分（`cli/`、`setup/`、`reply_*`、`item_*`），总覆盖率与核心模块覆盖率均达标。  

## 设计约定

### watch 多目标监听

- 一个目标是一个被监听的人 `{name, accounts: {open_id: 标签}}`，沿用 config 的 `watch:` 列表；目标键取第一个账号的 open_id，同一 open_id 不得出现在两个目标里。
- 监听哪些群只看全局白名单 `scope.include_chats`，没有 `scope` 就什么都不拉；目标可配 `chats`，必须是白名单的非空子集，越界由目标校验拒绝。
- 每个群每轮只拉一次，起点取该群各目标游标的最小值；新目标默认回溯 7 天（`watch_options.backfill_days`，1～30，越界报错）；频率全局统一。
- 消息按发言人 open_id 分给目标，每个目标只收不早于自己游标的消息，再按 message_id 去重（批次 1 落地，之前是 `last_ts+1`）。
- 游标按目标与群逐对记录：先写暂存表，commit 才推进，abort 丢弃，只进不退。
- watch 只负责拉取和分发，产出与 intent `fetch` 同格式的消息（多一个 `target` 字段），之后复用 intent 的 validate → render → reply → write；intent 的采集也走 `watch.poll`，intent 就是本人目标，产出格式不变。
- 每轮一个合并批次：卡片按监听对象分节、本人在前，#N 全批连续，回复语法不变。卡片只推本人，行动只按本人 open_id 推导；他人条目首行展示「监听对象：某某（角色：…，仅展示）」，对方的 DDL 只写进待办描述，不进 deadline；本人不回复确认就什么都不写。
- 只读本人所在的群；目标可以是任何 open_id，含外部成员；增删目标是配置变更，须本人确认；被监听者不会收到通知。真实配置目前只有本人一个目标。

### 私聊来源

- 默认关：`watch_options.dm` 全局开，目标上的 `dm` 优先；开启的目标须在本地配置填 `dm_chat_id`（`oc_` 开头，不入库）。会话列表不返回 p2p，按用户查私聊会话的接口是 POST，与只读冲突，所以保持手填。
- 只有 `watch/dm.py` 能读私聊，且只在该目标开关打开时调用。每次拉取前现场只读核验：会话必须是 p2p，成员必须恰好是本人和该目标的一个账号，不信任配置。
- 核验失败或缺权限 `im:message.p2p_msg:get_as_user` 时整轮报错停止（退出码 1，丢弃暂存游标，释放运行锁），不静默跳过。
- 只保留本人或该目标发的消息；依据行、链接和纯资讯来源都写「私聊」，不出现群名；夹具只用虚构数据。

### org 部门与群对齐

- 写客户端按需构造：只有 `org.enabled: true` 才构造，intent 不得 import 写客户端。组织架构用应用身份只读 GET 部门子树（用户身份返回 0 个部门，是身份问题不是缺权限），读路径不复用写客户端。
- 部门只认 department_id：`root_department` 必填，`allowed_departments` 只能在根部门之内收窄，按 ID 递归展开，不按名字匹配，范围外一律拒绝。`org depts` 只读列出部门 ID 和名字，建议写到本地 `data/org_depts_suggest.md`，本人确认后才进本地配置；部门缓存 `data/org_depts.json` 只存 id 和名字。
- 两次校验：生成计划时校验一次；apply 前按最新组织架构重算，与已批准计划不一致就拒绝，不降级、不换接口重试。计划阶段拦截、执行前重算拦截、未启用时不构造写客户端都有测试。
- 计划：移出在前并标红；plan_id 是条目 JSON 的 sha256；每批最多 20 条，其余顺延；单群移出超过 30% 拒绝；外部成员只能移出；v1 不生成管理员条目；建群、解散、转让默认关，打开后每条仍须单独批准。
- 保护名单（本人、群主、程序账号、`org.protected`）不作移出候选，万一漏进计划，plan、apply、writer 三层各拦一次。暂缓群在映射上写 `hold: true` 和必填的 `hold_reason`，只列差异不生成条目，apply 和 writer 也拒绝暂缓群；解除暂缓是配置变更，须本人确认。
- 批准来源：`org approve` 只收本人在审批单聊（`org.approval_chat_id`，只放本地）发的「批准 <计划 ID 前 8 位>」的 message_id。应用身份只读取回并核验：发送人是本人且 `sender_type=user`、会话是审批单聊、发送时间在计划生成后 24 小时内、文本完全一致；message_id 只能用一次；apply 前全部重新核验，并打印批准时间（北京时间）。
- writer 只收 `(plan_id, 序号)`，自己从 `state.db` 取已批准条目；每条前后各记一行 `org_ops`，幂等键是 `sha256(plan_id|序号|条目)`；测试只用假 runner；全仓库没有发消息的调用，有守卫测试。
- 命令 `org depts | plan [--dry-run] | show <id> | approve <message_id> | apply <id> [--only 1,3] | status`；退出码 40 读不到部门，41 配置不合规或计划被保护规则拒绝，42 批准或 apply 被拒，30 运行锁被占。
- 权限：应用身份读审批单聊里的单条消息需要 `im:message:readonly`，只有 `im:message.p2p_msg:readonly` 可能不够，验收时实测。

### 已知风险

- 审批可被冒充：本机上任何持有本人用户令牌的进程，都能以本人名义在审批单聊发出「批准 <id8>」；单条消息的元数据只区分得了用户和应用，区分不了客户端手打和接口发送。缓解靠计划 ID 只在本地报告出现、24 小时窗口、message_id 一次性、apply 前打印批准时间，以及第一次真实 apply 由本人在场批准。
- 未配置 `self_tenant_key` 时所有发言人按外部处理，规则见 AGENTS.md。
- 敏感哈希改 HMAC 后，CI 上没有密钥，敏感词守卫会 skip，只在本地生效，提交前必须本地跑；旧的 sha256 哈希还留在 git 历史里，仓库公开前必须清理历史。

## 借鉴量潮

参考的是 [qtcloud-feishu](https://github.com/quanttide/qtcloud-feishu)、[qtcloud-connect](https://github.com/quanttide/qtcloud-connect) 和 [quanttide-journal-of-business-entity](https://github.com/quanttide/quanttide-journal-of-business-entity) 里的 `fetch-chat-logs` 技能。前两个是 Rust 写的，这里只照搬设计和契约，不拷代码、不跨语言调用。  

| **我们** | **量潮** | **结论** | **理由** |
| :-- | :-- | :-- | :-- |
| lark-cli 执行 | `Runner` trait | 照着改 | 可注入，单元测试不必起子进程 |
| 抠 JSON | `extract_json` | 照着改 | 先整段解析，失败再取第一个 `{` 到最后一个 `}` |
| 成功判定 | 只认 `ok` 为 true | 改良 | `ok` 为 false 或 `code` 非 0 才算错，缺 `ok` 的裸负载不算错 |
| 翻页上限 | 到 `max_pages` 就停 | 不照搬 | 超限报错，不悄悄截断 |
| 测试设施 | 假 lark-cli 加 `argv.log` | 照着改 | 端到端走真子进程，断言命令行全是 GET |
| 原样留档 | `raw/` 目录 | 不做 | 会留下私聊原文和联系方式 |
| 游标与路径 | `cursor/*.json`、XDG 目录 | 保留我们的 | SQLite 有暂存、提交、回滚和运行锁；数据按规范放 `data/` |
| 流程推进 | `flow.rs` 三条规矩 | 已满足 | 确认前只出卡，写入失败不推进，commit 才推游标 |
| 意图抽取 | `extract.rs` | 保留我们的 | 对方一次调用加 `json_object`，没有 schema 校验 |
| 写入日志 | 发信草稿确认、fail-closed | 已满足 | `mark_written` 在同一事务里改状态并记日志，只存键与状态 |
| 发消息 | `notice` 发群通知 | 不做 | 飞书只读，守卫测试禁止发消息 |
| 系统消息 | sender 为空要兜底 | 补上 | 显示「（系统消息）」，不进角色推断 |
| 脱敏 | 真实 ID 与姓名不入库 | 对齐 | 文档用角色代称，拿不准按高保密 |
| 网络超时 | 等 10 秒重试 | 不做 | fetch 失败按退出码停本轮，下一轮重拉 |

另外照搬四条做法：实测边界写在调用旁边；夹具照真 CLI 的输出形状编造，先看原始 JSON 再写取值路径，否则会「mock 绿、真跑断」，qtcloud-feishu 就踩过真 CLI 返回不带 `ok` 的裸负载；同一段代码出现第二个调用方才提炼；扩大采集面之前先立规则，私聊来源默认关就是这么来的。和 qtcloud-feishu 不同，`state.db` 里的确认记录不能从飞书重建，所以迁移前必须备份。  

## 协作规范

- 每次调用 Cursor 只做一项（WIP=1），一项一个约定式提交，测试不过不提交；单项超过 15 分钟没有提交就停下报告。
- 指令开头写「写最终代码，应用这个修改」，写明允许改的文件、禁止范围和停止条件。编码用 `gemini-4-argon-high`，架构和计划用 `claude-opus-5-5-max-fast` 加 `--mode plan`。
- 每次提交后由审查人审查。低风险项可以边审边做；危险项必须审过才继续：schema 与迁移、HMAC、删除、`src` 主入口与运行锁。审查后的修复另起提交 `fix review: <SHA>`，不 amend、不 rebase；一两行的小改可以合并为一项。
- 每次调用前后检查工作区，提交后 `git status --short` 必须为空。只由协调人推送：直推 main、不开 PR，只推审查人审过的最新 SHA，禁止强推。
- 编码时不联网，不调用飞书或 Todoist，不读也不改 `config.yaml`、`data/`；单文件 ruff format 后少于 300 行；只有 `settings` 读环境变量；函数里不 import；依赖都写上界；时间存 UTC 带 Z，展示转 `+08:00`；测试只用夹具。
- 在 Mac 上读进程参数、历史、环境变量或日志时，只输出计数、时间戳或 PID；查进程用 `pgrep -f cursor-agent`，不加 `-l`。

## 验收标准

- 不要求 TDD。集成测试的期望输出是入库的固定文件，先于实现提交，自动比对，每个测试都有失败用例。
- 覆盖率只统计 `src/feishu_workflows`，禁止用 `omit` 或 `pragma` 凑数。门槛是总覆盖率 ≥ 80%，`org/writer.py`、`org/approve.py`、`watch/dm.py` 各自 ≥ 80%；基线是总 93%、writer 80%、approve 100%、dm 100%；BP1 开启门槛，开启前不得下降。
- 单元测试放 `tests/`，集成测试放 `integrated_tests/`，与源码同名对应；补测试单独提交，不和拆文件混在一起。
- 守卫测试和单元测试全部通过；两个批次都要求 A、B 两组卡片的版本号逐字节不变。
- 点名测试各有一条：同秒两条消息分两轮拉取、兼容旧的 Z 值、`ok` 与 `max_pages`、HMAC 缺密钥时 skip。
- 每个断点交两样：集成测试期望与实际并列对照；本人在 Cursor 里复现的步骤（打开哪个文件夹、在内置终端跑哪条命令、在哪个文件看期望输出）。本人确认后才进下一阶段。

## 待定问题

1. 时间列范围（已定）：文本时间列与 `org_approvals.sent_at` 统一为 `TIMESTAMP`（`YYYY-MM-DDTHH:MM:SS.mmmZ`）；`last_ts`、`ts`、`expires` 保持 `INTEGER` 秒。
1. `messages` 表写入方式（已定）：保持 `message_id` 幂等 upsert 与未推送孤儿消息（`pushed=0`）清理删除，`reply_logs` 与 `write_action_logs` 严格只追加。
1. 覆盖率门槛（已定）：`pyproject.toml` 开启 `fail_under = 80` 并由守卫测试禁止 `omit` 与 `pragma: no cover`；`org/writer.py`、`org/approve.py`、`watch/dm.py` 各自 ≥ 80%。
1. 话题回复拉取（待审查人定）：消息对象自带 `thread_replies` 的单话题 50 条、整批累计 500 条截断与撤回/`app` 过滤已实现并测试；在线额外调用 `container_id_type=thread` 子接口拉取未开启（保持每群每轮单次 GET）。
1. 私聊权限 `im:message.p2p_msg:get_as_user` 开通（待本人签字）后，做一次真实私聊的只读端到端核验；轮换两项已泄露的凭据（明细只在本地）。
