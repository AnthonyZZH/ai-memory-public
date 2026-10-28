# 第 0 阶段：补地基

制定：Claude（主导）　执行：Codex　拍板：主人
日期：2026-10-27　前置：无　之后：V1 固定人格

## 目标

在加人格系统之前，让现有图书馆做到：两个库都有版本记录和每日备份、服务开机自启可验证、工作区干净可回退。

## 现状核查（2026-10-27，Claude 实测，和 GPT 总结有出入）

| # | 发现 | 结论 |
|---|---|---|
| F1 | `AI-Memory-Private-HTTP` 计划任务**已存在且在运行**，8767、8768 都在监听 | GPT 说"自启没注册成功"已过时，只需重新登录后验证 |
| F2 | `AI-Memory-Daily-Backup` 从未运行过（LastTaskResult 267011 = 尚未运行），下次 10-28 00:00 | 若半夜关机会错过，需开 StartWhenAvailable，并先手动跑一次 |
| F3 | `E:\AI-Memory-private` 不是 git 仓库，没有任何备份 | 要补 |
| F4 | 主库有未提交改动：`AGENTS.md`(+80 行)、`分类总览.base`；4 篇笔记只有换行符差异；未跟踪 `CLAUDE.md`、`.agentbridge/` | `backup.ps1` 用 `git add -A`，会把 `.agentbridge/` 一起提交，需先处理 |
| F5 | 没有 `.gitattributes`，LF/CRLF 警告反复出现 | 可选修复 |
| F6 | 计划任务实际入口是 `scripts/run_task.py`，`serve.ps1` / `serve-private.ps1` 是另一份重复配置 | 两处参数可能不同步，标注即可 |
| F7 | 所有备份都在 E 盘同一块硬盘 | 需主人决定是否加异盘副本，不阻塞本阶段 |

## 硬约束（Codex 必须遵守）

1. 不删除任何文件（图书馆写规则第 7 条）。需要"移除"时改名为 `*.bak-日期` 或移到 `backups/`。
2. 不修改 `vault/` 里的笔记内容，换行符规范化也不例外（F5 只加 `.gitattributes`，不批量重写）。
3. 不运行 `scripts/connect_dsh.py`。
4. 不做任何网络上传。
5. 私密库内容、文件名列表、笔记标题不得出现在主库的提交、日志、`SETUP_LOG.md` 里。私密库日志只记路径和结果码。
6. 改计划任务前先导出原任务 XML 到 `backups/`。

## 任务

### 0.1 主库基线提交　Codex · medium
- 看一眼 `.agentbridge/` 里有什么。属于运行状态或可能含令牌 → 加进 `.gitignore`。
- 看一眼 `CLAUDE.md`。若和 `AGENTS.md` 一样是工作区规则 → 跟踪；若含密钥或私密信息 → 停下报告。
- 审 `AGENTS.md` 和 `分类总览.base` 的 diff，确认是预期改动后提交，提交信息 `phase0: baseline`。
- **验收**：`git status` 干净；`git log -1 --stat` 贴给 Claude。

### 0.2 私密库纳入版本和备份　Codex · medium
- `E:\AI-Memory-private` 初始化 git，`.gitignore` 照搬主库那套排除规则。首次提交。
- 备份：给 `backup.ps1` 加 `-Root` 参数（默认仍是主库，行为不变），或者另写 `backup-private.ps1`，二选一，理由写进汇报。ZIP 存到 `E:\AI-Memory-private\backups\`，不进主库的 `backups\`。
- `run_task.py` 加 `backup-private`，日志写 `cache/task-backup-private.log`，只记结果码。
- 新建计划任务 `AI-Memory-Private-Daily-Backup`，每日触发。
- **验收**：手动跑一次生成 ZIP；同一天再跑一次输出 skip；ZIP 内文件数和 vault 一致；主库 `git status` 仍干净。

### 0.3 备份任务防错过　Codex · low
- 两个备份任务都开 StartWhenAvailable（错过时间开机后补跑）。
- 现在手动触发两个任务各一次。
- **验收**：`Get-ScheduledTaskInfo` 两个任务 LastTaskResult 都是 0。

### 0.4 健康检查脚本　Codex · medium
- 新建 `scripts/healthcheck.py`，检查：8767、8768 能否完成一次 MCP 初始化握手；两个库最近一次备份 ZIP 的日期；两个仓库是否有超过 1 天未提交的改动。
- 只输出结论表格，不输出笔记内容。
- **验收**：现在跑一次全绿；停掉一个服务再跑能报红（跑完恢复）。

### 0.5 启动脚本去重　Codex · low
- 在 `serve.ps1`、`serve-private.ps1` 文件头注明"计划任务实际走 run_task.py，本文件只供手动调试；改端口两处同改"。不改逻辑。

### 0.6（可选）换行符　Codex · low
- 加 `.gitattributes`：`*.md`、`*.yaml`、`*.json`、`*.base` 统一 `eol=lf`，`*.ps1` 用 `eol=crlf`。只加规则，不执行 `git add --renormalize`，等主人同意再做。

### 0.7 验收评审　Claude · medium
- 审 0.1–0.6 的 diff 和汇报。
- 跑 `scripts/final_acceptance.py`，确认原有功能没坏。
- 主人注销再登录一次（主人操作），之后跑 `healthcheck.py` 确认自启。

## Codex 汇报格式（每个任务一次）

```
任务：0.x
改动文件：…
关键命令及输出：…（截断到要点）
验收结果：通过 / 未通过 + 原因
偏离计划之处：无 / …
```

## 待主人决定（不阻塞本阶段）

- D1：异盘备份放哪（另一块硬盘、移动硬盘、NAS）？还是暂时只放 E 盘？
- D2：0.6 换行符规则加完后，要不要一次性规范化现有文件（会产生一个大的纯格式提交）。

## 本阶段完成标准

- 两个库都在 git 里，工作区干净。
- 两个每日备份任务都至少成功跑过一次，并且开了补跑。
- 重新登录后 `healthcheck.py` 全绿。
- `final_acceptance.py` 通过。

完成后进入 V1：人格文件结构、persona/voice 草稿（主人审）、人格加载器、跨模型一致性测试。
