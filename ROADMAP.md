---
tags: [已阅]
date: 2026-10-20
---

# 实训基地工具箱路线图

本文记录 `quanttide-academy-toolkit` 的已完成状态与核心设计约定，在修改架构或上线验收前阅读；日常操作命令与硬性约束以 [AGENTS.md](AGENTS.md) 为准。  

## 目标与现状

已完成 `intent`（群聊意图转待办）、`watch`（多目标跨群与私聊监听）、`org`（部门与群对齐 v1.2）三大工作流，以及 `state.db` v5（强制在线备份、`TIMESTAMP` 毫秒 `Z` 与 `BOOLEAN` 约束、游标合并与同秒 `message_id` 去重）、可注入 `Runner` 与假 `lark-cli` 端到端回归、模块拆分与 `v0.2.0` 打包发版。  

## 设计约定

### watch 多目标监听

- **目标与范围**：目标格式为 `{name, accounts: {open_id: 标签}}`，目标键取首个 `open_id`（账号不可跨目标重复）；监听群由全局白名单 `scope.include_chats` 决定，目标级 `chats` 须为其非空子集。
- **单次拉取与游标**：每群每轮只拉一次（起点取各目标游标最小值，新目标默认回溯 7 天，`watch_options.backfill_days` 1～30），按发言人分发并以 `start=last_ts` 加 `message_id` 去重；游标先写暂存表，`commit` 才推进。
- **合并渲染**：复用 `intent` 校验与渲染链路；卡片按监听对象分节（本人在前，`#N` 全批连续），他人条目仅展示角色且对方 DDL 只进描述不进 `deadline`。

### 私聊来源

- **默认关闭与手填**：仅在目标开启 `dm` 且本地配置手填 `dm_chat_id`（`oc_` 开头）时，由 `watch/dm.py` 唯一读取；因按用户查私聊接口为 `POST`，与只读原则冲突，故保持手填。
- **现场核验与阻断**：每次拉取前现场核验会话为 `p2p` 且成员恰好为本人与目标账号；核验失败或缺 `im:message.p2p_msg:get_as_user` 权限时整轮报错停止（退出码 1），绝不静默跳过。

### org 部门与群对齐

- **按需写端与部门 ID**：仅 `org.enabled: true` 时构造写客户端；应用身份（`--as bot`）只读拉取部门树，只认 `department_id`（`root_department` 必填，`allowed_departments` 仅限其内收窄）。
- **计划与三层保护**：移出在前并标红，每批最多 20 条，单群移出超 30% 熔断，外部成员只出不进；保护名单（本人、群主、程序账号、`org.protected`）在 `plan`、`apply`、`writer` 三层兜底拦截；暂缓群（`hold: true` + `hold_reason`）只展示差异不生成写入条目。
- **审批核验与幂等写入**：`org approve` 只收本人在审批单聊发出的「`批准 <id8>`」消息 `message_id`（核验发送人、会话、24 小时窗口与文本，一次性使用）；`apply` 前重算计划并打印批准时间，`org/writer.py` 前后记录 `org_ops` 幂等日志。

### 已知风险

- **本机令牌冒充审批**：单条消息元数据无法区分客户端手打与本机进程持用户令牌发送；靠本地计划 ID、24 小时窗口、`message_id` 一次性使用、`apply` 前重算并打印批准时间及首次真实 `apply` 本人在场缓解。
- **配置与环境降级**：未配 `self_tenant_key` 时全员按外部成员处理；CI 无本地 HMAC 密钥时自动跳过敏感词扫描，提交前须在本地运行测试。
- **上线前真实环境核验**：待 `im:message.p2p_msg:get_as_user` 权限开通后执行一次真实私聊 `--dry-run` 核验，并由本人在场完成首次真实 `org apply`（见 [integrated_tests/scenarios/README.md](integrated_tests/scenarios/README.md)）。
