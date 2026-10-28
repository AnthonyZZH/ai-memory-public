# personality-engine（私有）

消费相邻 conversation-processor 的 `memory-candidate/v1`；只向本地模型请求反思。
运行环境：`tools/xq-engine/Scripts/python.exe`。依赖沿用 processor 的完整版本锁。
此目录及实例配置不是通用 processor 的一部分，不应随其开源。

```powershell
$python = 'E:\AI-Memory\tools\xq-engine\Scripts\python.exe'
$engine = 'E:\AI-Memory\scripts\personality-engine\engine.py'
& $python -B -X utf8 $engine status
& $python -B -X utf8 $engine collect --dry-run
& $python -B -X utf8 $engine collect
& $python -B -X utf8 $engine extract
& $python -B -X utf8 $engine reflect
& $python -B -X utf8 $engine apply [proposal-id]
& $python -B -X utf8 $engine rollback <proposal-id>
& $python -B -X utf8 $engine approve <proposal-id> --owner-approved
& $python -B -X utf8 $engine reject <proposal-id> --owner-approved
& $python -B -X utf8 $engine sync --dry-run
```

默认配置 `config/engine.yaml`；`--config`、`--dry-run` 可放子命令前或后。
`--dry-run` 不写文件/数据库、不建锁、不启动子进程、不请求网络；采集/提取预览仅校验
已经存在的候选，不能预测尚未提取的候选。`status` 始终只读。

## 所有者策略

引擎只读 `her/identity-lock.yaml`。`evolution` 必须有：

```yaml
max_step_per_trait: 3
monthly_drift_needs_approval: 10
min_evidence_episodes: 3
min_evidence_sessions: 2
drift_window_days: 30
must_stay_in_range: true
forbid_sycophancy: true
locked_files:
  - her/persona.md
  - her/voice.md
  - her/identity-lock.yaml
writable_by_engine:
  - her/episodes/
  - her/evolution/
  - her/personality.json
  - her/relationship.md
```

缺少门槛时拒绝反思/相应护栏；缺少写权限时拒写。任何越权写入均为非零退出。
锁在进程中途变化也中止写入。代码不提供修改锁的功能。
pending 只是待主人审核的提案；`apply <id>` 仍会重新检查全部护栏，不能绕过限制。
主人使用 `approve <id> --owner-approved` 仅豁免 range、累计漂移两项，仍截断单步、
检查证据/会话数、纯夸奖、未知维度、锁定路径。`reject` 同样要求显式审批标志。
已解决的 pending 审计文件保留原位并更新 status，加载器忽略这些档案，不删除文件。
主人批准超出 trait range 的值仍能重新读取，不会修改原 range 或锁文件。

配置中的 `reflect_every` 初值 20；`expression_limit` 初值 30。反思批次最多 100 条，
先剔除 praise_only，按维度/方向统计。达到锁里的最少条数、会话数，且反向条数的
三倍不超过支持条数时，代码提名 ±1，每维度最多一项。模型只审核 approve/veto，
不得新增提案或改变维度、幅度、证据。专用 review.schema.json 加精确ID集合校验。
审核须否决主体混淆、遵守锁定底线当成长、把篇幅格式当性格的推断。
SQLite review_batches 在HTTP前持久化冻结的情景、候选与统计；不可用/无效响应不推进
水位，下次先重审原批次。有效审核（或无候选）完成后才标记本批情景已反思。
拒绝与通过均保留审核理由；通过仍运行全部护栏。apply 使用最新参数和累计漂移
重新检查。累计变化采用滚动窗口内绝对变化之和；回退也计入绝对变化，防止反复往返
规避漂移门槛。私密候选不参与反思。关键词兜底只会提高敏感级别。

## 状态、写入和提交

- 只读 processor 输出目录顶层 `*.jsonl`，逐行校验 schema、来源哈希和维度，按 id 去重。
  同 id 内容不同即停止；嵌套 staging、链接、过大文件不消费。
- 每条 normal 候选写情景；relationship/expression 还更新相应聚合。private/unsure
  只写私密仓库情景，公开 `her/` 没有占位、文件名或标题；公开状态库仅保留其 id、
  指纹、敏感级别、消费时间，不保留私密正文。
- 常用表达只收对主人私聊的友好原话。processor配置 expressions.non_owner_markers
  和 aggressive_keywords；群聊/第三方结构化来源、标记及攻击词会阻止表达，消费端
  重新检查。写入时保留audience与episode_id；每次normal写入也清理不合规旧条目。
  没有audience来源的旧记录保守移出常用表达；重写文件，不删除文件，不删除历史情景。
- 所有 her 内容写入先解析路径/目录链接，再经锁的拒绝和允许规则。私密仓库只允许
  镜像的 episodes 路径。状态、互斥锁、恢复日志分别限制在两个仓库的 `cache/engine/`，
  私密恢复数据只存在私密仓库 cache，不进入公开缓存。两处 cache 都应被 gitignore。
- 每条情景在对应仓库单独提交 `xq-memory: <id>`；每条生效提案只提交参数和演化日志，
  首行严格为 `xq-evolve: <id> <trait> <±n>`。首次日志独立提交，确保回退不删文件。
- 精确暂存目标文件；遇到已有暂存项、目标未提交编辑或未跟踪内容即停止。无关未暂存
  工作保留。提交禁用 hooks 和签名，不改变 git 全局/仓库配置，移除继承的 GIT_* 覆盖。
- 崩溃恢复日志保存前后字节和提交指针。重试只恢复同一操作，不覆盖中途外部改写。
  已提交但尚未记入 SQLite 的操作不会再次提交或再次增加参数。
- `rollback` 检查提交仅修改两个获准文件后执行 `git revert --no-edit`。不使用 reset、
  clean、文件删除。回退与后续修改冲突时保留 git 冲突现场并报错，需要人工解决；不会
  自动覆盖后续变化。重复回退幂等。
- `cache/engine/state.sqlite` 和两处恢复日志是持久运行状态，应保留；不要当作可随意
  清空的普通缓存。不得在已有运行历史时直接丢弃状态重建。

## 验证

```powershell
$env:ENGINE_TEST_ROOT = 'E:\Codex Development\tmp\v2.2c\engine-tests'
& $python -B -X utf8 -m unittest discover -s E:\AI-Memory\scripts\personality-engine\tests -v
```

所有数据均为人工样本。测试保留临时目录，通过引擎的运行时 git 包装器建立和修改
临时仓库；不接触真实对话，不在真实仓库上测试提交，不连接真实 8080。
processor 的 baseline 只在人工 sim 目录测试。真实来源 T0 必须另外确认登记。
真实来源启用、50 轮模拟和计划任务实际注册留待 V2.3/V2.4。

## 加载器和同步

persona_loader 仍只读，保留三种 target、--with-source 及空核心人格报错行为。
在 persona/voice 后按需加入身份/底线、参数、常用表达、最近关系摘要、待批提醒。
关系摘要最多 600 字符；三种入口的总输出默认最多 12000 字符（--max-chars 可改，预留
入口包装和哈希尾注空间）。超出先截关系摘要，再移除最旧表达；身份/底线/当前参数/审批提示
无法容纳时失败，不悄悄截断。所有 target 共用完整正文的 SHA-256/字数；包装仍保持
旧行为，steward 参考人格源文件并实际附带扩展段。审批提示仅含维度和带符号幅度。

sync 的目标明确列于实例 config/engine.yaml。JSON 定位 operation.fields 中的
llm.prediction.systemPrompt，只替换原 loader 开头至哈希尾注，保留图书馆规则原始
转义字节。YAML 按真实 agent preset/plugin 结构定位 persona.prefix，仅替换该 scalar，
其余文本原样保留。不重序列化整个配置，不改变模型、凭据或工具。

改动前备份至 backups/sync-<UTC时间戳>/，做解析和非人格字段相等检查。读写间比较
mtime_ns、大小、文件标识和 SHA-256；预写前检查所有输入，每次替换前再次检查。
并发变化会中止；如果写入过程中后续目标才发生变化，已完成的目标保留，其余不覆盖，
所有原始备份可供人工检查。文件组不宣称跨三个文件原子提交。无变化、dry-run 均零写入。

sync.automatic=true 时，普通引擎命令的共同人格正文发生变化便自动 sync，包含 pending
新增、approve/reject、表达/关系更新及 rollback。sync 失败时主变更可能已经提交，命令
会报 automatic_sync_failed，需修复并重跑 sync。不会为还原快照覆盖外部并发编辑。
新增 pending 会尝试 Windows PowerShell 5.1 WinRT toast，仅发维度/幅度；失败不影响流程。

## 每日运行

```powershell
& $python -B -X utf8 E:\AI-Memory\scripts\xq-daily.py --dry-run
# 下列注册命令仅由主人/Claude 在 V2.4 执行，本阶段不注册：
# & E:\AI-Memory\scripts\register-xq-daily.ps1
```

每日运行器全程持有同一 engine 互斥锁。检查本地 health，未运行时经 8088/model/start
启动；其他入口正在启动的只等候。按顺序执行 collect、extract、reflect、apply，并进行
幂等 sync 校验（也用于补齐先前失败的同步）。finally 只停止自身确认启动的模型，停止前
核对 profile、控制状态及不透明 runtime 记录指纹；外部重启/切换或无法确认所有权时
安全失败，保留模型。恢复失败、启动失败都有固定结果码。运行记录的 token 不打印、
不存日志，仅在内存取指纹。所有控制调用仅 loopback，不跟随重定向或使用代理。

日志 cache/xq-daily.log 只含时间、固定事件/结果码和计数，不含正文/证据/密钥。
--dry-run 不请求 HTTP、不建锁、不写日志、不跑引擎或启动/停止模型。
注册脚本采用当前交互用户、Limited、03:00、StartWhenAvailable、IgnoreNew；使用 pythonw
隐藏控制台，不保存密码。用户未登录时不运行，下次登录错过补跑。脚本支持 -WhatIf；
本阶段只做静态解析，从未执行注册脚本。
