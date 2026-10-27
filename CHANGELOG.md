# 更新日志

## 未发布

### 破坏性变更
- **安装名与导入名对齐工具箱命名**。PyPI / 项目名由 `quanttide-academy` 改为 `quanttide-academy-toolkit`，避免与领域仓库 `quanttide-academy` 撞名；导入包由 `quanttide_academy` 改为 `quanttide_academy_toolkit`（目录 `src/quanttide_academy/` 一并改名）。GitHub 仓库名、中文标题「实训基地工具箱」与命令入口 `feishu-workflows`、`feishu-workflows-setup` 保持不变。旧导入名不再保留兼容层，请直接改用新包名。
- **定位**。飞书协作接驳（`intent` / `watch` / `org`）是当前通道。资产类型仍是工具箱；以后的非飞书工具也放在这一套里。

## 0.2.0 — 2026-10-20

### 新增
- **watch 多目标监听模块**（`src/quanttide_academy/watch/`）：
  - 支持多目标配置（`targets`）、按「目标 × 群」记录暂存与提交游标（`cursors`）、每群单次只读拉取并按发言人分发（`poll`）。
  - 新目标默认回溯 7 天（`watch_options.backfill_days`，1～30）；支持目标限定 `chats`（须为 `scope.include_chats` 非空子集）。
  - 合并批次按监听对象分节（本人在前，`#N` 全批连续）；他人条目首行展示角色（仅展示），对方 DDL 只进描述不进 Todoist `deadline`。
  - 私聊来源（`watch/dm.py`，默认关闭）：每次拉取前现场只读核验 `p2p` 会话与成员（本人 + 目标账号），缺权限 `im:message.p2p_msg:get_as_user` 或核验失败整轮报错停止（退出码 1）。
- **org 部门 ↔ 群对齐模块**（`src/quanttide_academy/org/`）：
  - 只读层（`org/read.py`）用应用身份（`--as bot`）读取部门树与部门成员，用户身份读取群信息；`org depts` 输出部门 ID 与映射建议至本地 `data/org_depts_suggest.md`。
  - 计划生成（`org/plan.py`）：部门只认 `department_id`；移出在前并标红；保护名单（本人、群主、程序账号、`org.protected`）三层兜底拦截；单群移出超过 30% 熔断；映射支持 `hold` + `hold_reason`（暂缓仅展示）。
  - 批准来源核验（`org/approve.py`）：只收本人在审批单聊发出的「批准 <id8>」消息 `message_id`，核验发送人、会话、24 小时窗口与文本，一次性登记（`org_approvals`）；`apply` 前重算计划、重新核验并打印批准时间（北京时间）。
  - 唯一飞书写入点（`org/writer.py`）：只接受已批准计划的 `(plan_id, 序号)`，写前后记录 `org_ops` 幂等日志；`org.enabled=false` 时不构造写客户端。
- **读取层与测试设施**：
  - `core/lark.py` 抽出可注入 `SubprocessRunner`，同时检查 `ok` 与 `code`，JSON 提取支持整段解析与首尾花括号回退，`--page-all` 增加 `max_pages` 上限（超限或残留 `has_more` 报错）。
  - 系统消息或空 `sender` 统一显示「（系统消息）」，不参与角色推断；支持 `thread_replies` 单话题 50 条、整批 500 条截断。
  - 新增跨平台 Python 假 `lark-cli`（记录 `argv.log`）与 `integrated_tests/` 端到端回归测试。

### 变更
- **state.db 升至 v5**：
  - `migrations.migrate()` 强制先经 `sqlite3.Connection.backup()` 在线备份并校验 `pragma integrity_check=ok`，运行锁非空或无备份拒绝迁移。
  - `intent` 的 `cursors`、`pending_cursors` 合并进 `watch_cursors`、`watch_pending_cursors` 并删除旧表；拉取起点统一为 `start=last_ts` 并按 `message_id` 去重（同秒消息分轮拉取不漏不重）。
  - 时间列声明为 `TIMESTAMP` 并带 `CHECK` 约束（统一毫秒级 `YYYY-MM-DDTHH:MM:SS.mmmZ`，读取兼容旧秒级 `Z` 与 `+08:00`），`org_approvals.sent_at` 转为 `TIMESTAMP`；布尔列声明为 `BOOLEAN` 并带 `CHECK(col IN (0, 1))`。
- **代码结构与质量门禁**：
  - 安装包名与导入名对齐量潮规范统一为 `quanttide-academy` / `src/quanttide_academy/`，入口命令保持 `feishu-workflows` 与 `feishu-workflows-setup`。
  - 拆分 `cli/`、`setup/`、`intent/reply_{parse,handle,assign}.py`、`intent/item_{text,people,render}.py`，原导入路径保留兼容重导出，所有 Python 文件格式化后均少于 300 行。
  - 敏感词哈希改用 HMAC-SHA256 移至本地 `local/sensitive_hashes.txt`（不入库）；开启 `pytest` 未关闭 SQLite 连接常驻守卫、`ResourceWarning` 报错与覆盖率门槛 `fail_under=80`。

## 0.1.0 — 基础版本

- 仓库重构为 `feishu-workflows`（`src/feishu_workflows/`），入口命令 `feishu-workflows` 与 `feishu-workflows-setup`。
- 完成 `intent` 全流程（采集、校验、卡片渲染、逐条确认闸门、Todoist/Markdown/Export 写出）与 `state.db` v2。
