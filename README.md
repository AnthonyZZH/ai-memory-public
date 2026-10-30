# 她的图书馆（AI-Memory）

一套**本机运行、多个 AI 共用的长期记忆库**。笔记是普通 Markdown 文件，用 [basic-memory](https://github.com/basicmachines-co/basic-memory) 提供检索，通过 MCP 协议让 Claude Code、Codex、DeepSeek Harness 和 LM Studio 里的本地模型读写同一份记忆，Obsidian 可以直接打开查看。

> 这是**去隐私的公开版**：个人笔记（`vault/` 里的内容）、服务器操作日志和测试记录都已移除，只留目录模板；服务器地址、账号、朋友的名字都换成了占位或示例。路径仍按作者的 `E:\` 布局写，没有做成通用安装包。

## 小千全家桶

| 仓库 | 是什么 |
|---|---|
| [小千微信 · Harness Native](https://github.com/AnthonyZZH/xiaoqian-weixin) | 小千本体：微信桥接、持久会话、工具与权限，main 图书馆接这里 |
| [小千部署 Skill](https://github.com/AnthonyZZH/xiaoqian-deploy-skill) | 把小千部署到 Windows 桌面的流程：安装、升级、迁移、健康检查、回退 |
| **她的图书馆**（当前） | 多个 AI 共用的长期记忆、人格、成长引擎和社交补丁（去隐私公开版） |

## 项目简介

- **记忆是文件**：全部内容是 `vault/` 里的 Markdown，可以用 Obsidian 查看、手改，basic-memory 会自动重新索引。
- **多个 AI 共用**：不同的 AI 客户端连到同一个本地服务，不用在每个工具里各存一份。
- **本机优先**：服务只监听 `127.0.0.1`，不上传；检索用本地多语言向量模型，离线运行。
- **分级与隔离**：普通笔记放 `main` 库；健康、存款、生日等敏感信息放另一个 `private` 库，只配给本人使用的入口，对外入口（群聊机器人等）读不到。

## 结构

```
Claude Code ─┐
Codex ───────┼──► 127.0.0.1:8767  (basic-memory, 只服务 main)    ──► vault/               普通库，在本仓库
LM Studio ───┤
DeepSeek Harness（本机会话）
Claude Code ─┐
Codex ───────┼──► 127.0.0.1:8768  (basic-memory, 只服务 private) ──► E:\AI-Memory-private\vault   私密库，不在本仓库
DeepSeek Harness（本机会话）

对外入口（小千、以后的 QQ / 微信）：只允许 8767，不配 8768
```

| 组件 | 说明 |
|---|---|
| basic-memory 0.24.1 | 记忆服务与检索，`--project` 限定每个服务只暴露一个项目 |
| FastEmbed + 多语言 MiniLM（384 维） | 本地向量检索，离线 |
| `scripts/` | 读写规则、启动脚本、备份、验证脚本 |
| `AGENTS.md` | 在本目录打开的 AI 会话会自动加载的读写规则 |
| `her/` | 「她」的人格与说话方式模板（待填写） |

## 仓库目录

| 位置 | 用途 |
|---|---|
| `vault/` | 普通笔记库，分类 00-总览、10-个人档案、20-偏好、30-项目、40-设备与环境、50-学习、60-人物、70-她、90-收件箱 |
| `her/` | 人格与说话方式模板，空模板 |
| `scripts/` | `memory-rules.md`（读写规则）、`serve.ps1` / `serve-private.ps1`（启动服务）、`backup.ps1`（备份）、`run_task.py`（计划任务入口）、验证脚本 |
| `AGENTS.md` | 工作区规则：默认使用图书馆、读写规则、私密库规则 |
| `VERSIONS.md`、`SETUP_LOG.md` | 组件版本、搭建日志 |
| `backups/`、`cache/`、`bin/`、`tools/`、`apps/` | 备份、模型缓存、运行工具，不进 Git |

## 快速开始（复现要点）

1. 安装 uv，用它装 `basic-memory==0.24.1`，依赖版本见 `scripts/requirements.lock.txt`；设置 `auto_update=false`。
2. 把 basic-memory 的 `main` 项目指向 `vault/`，用 `scripts/serve.ps1` 启动，监听 `127.0.0.1:8767`。
3. 在各客户端里添加 MCP 服务：Claude Code 用 `claude mcp add`，Codex 用 `codex mcp add`，LM Studio 写 `mcp.json`，DeepSeek Harness 在 profile 补丁里用 `insert` 新增 `@deepseek-ai/dsh-mcp-client`。
4. 需要私密库时：新建 `private` 项目，用 `scripts/serve-private.ps1` 监听 `127.0.0.1:8768`，**只**配给本人入口。
5. 把 `scripts/memory-rules.md` 的读写规则放进各客户端的全局指令（Claude 的 `CLAUDE.md`、Codex 的 `AGENTS.md`、LM Studio 的系统提示词）。

详细的搭建过程、踩坑和验收记录见 `SETUP_LOG.md`。

## 隐私与安全

- 本仓库是**私有**仓库，`vault/` 里有个人档案、偏好、项目等笔记，请勿公开或设为可公开 Fork。
- 私密库（`private`）在 `E:\AI-Memory-private`，**不在本仓库**，也不在 `backup.ps1` 的备份范围内，需要另行备份。
- `visibility` 字段只是内容分级约定，**不是权限控制**；真正的隔离靠"哪个入口连哪个服务"。
- 隔离是配置层的逻辑隔离，不是操作系统级隔离：8768 没有认证，同一 Windows 用户下的其他进程能直接连。对外入口不要配 8768。
- 不要把密钥放进 `vault/`、`her/` 或 `scripts/`。`.gitignore` 已排除 `*.env`、`*.key`、`*.pem`、`secrets*`。

---

# 使用说明

一个共用的记忆库,供 Claude、Codex 和 LM Studio 里的本地模型读写。内容在 `vault`,由 basic-memory 提供检索。

## 目录

| 位置 | 用途 |
|---|---|
| `vault/` | 唯一图书馆,分类 00-总览、10-个人档案、20-偏好、30-项目、40-设备与环境、50-学习、60-人物、70-她、90-收件箱 |
| `her/persona.md`、`her/voice.md` | 她的人格与说话方式,空模板,由你填写 |
| `scripts/` | 读写规则 `memory-rules.md`、备份 `backup.ps1`、启动 `serve.ps1`、验证脚本 |
| `backups/` | 每日备份 zip,不进 git |
| `cache/`、`bin/`、`tools/`、`apps/` | 模型缓存与运行工具,不进 git |
| `VERSIONS.md`、`SETUP_LOG.md` | 组件版本、搭建日志 |

## 共享服务

- 地址:`http://127.0.0.1:8767/mcp`,只监听本机。
- 启动脚本:`scripts/serve.ps1`。已注册登录自启任务。
- Claude、Codex、LM Studio 都通过这个地址访问同一个图书馆。

## 怎么读

1. 开局先读 `00-总览/目录`(约 360–450 token),不要一次加载全部笔记。
2. 项目概览直接依据目录列出名称,不要重复搜索。笔记没有明确写出的状态(是否活跃、已完成、运行中)不得推断,回答「笔记未说明」。
3. 具体主题:用 2–4 个关键词或同义词(例如「GPU OR RTX」)调用 `search_notes`(project: main, page_size: 5, compact: true)。整句自然问句召回不稳。
4. 每个问题最多搜索 2 次(首次加一次重试),重试时换更短的关键词或同义词。
5. 搜索后最多 `read_note` 读 2 篇相关笔记,然后作答;信息不足就说明不确定之处。
6. **搜不到不等于没有记忆。** 不能据空结果断言没有记忆。

## 怎么写

- 只记决定、偏好、稳定事实、「现象 → 根因 → 解法」。
- 不记报错原文、日志、重复内容、闲聊。
- 会话结束汇总写一次。先搜同主题,有则更新,没有才新建。
- 分类不确定放 `90-收件箱`。
- 每篇只讲一件事,约 300 中文字以内,标题是一句结论。
- 不删除任何文件。
- 家庭所在地不写。健康、身体信息、财务状况（含存款）、生日属于「私密信息」：只能写入 private 项目（工具 memory-private，project: private），不得写入 main；当前会话没有 private 工具时，不写这类信息。
- 完整规则与笔记格式见 `scripts/memory-rules.md`。

## 分级

`visibility` 有三档:`private` 仅主人与管家,`her` 她自知不外说,`public` 可对外提及。新笔记默认 `private`。

这是内容分级约定,**不是权限隔离**。任何能连上共享服务的客户端都能读到全部笔记。

## 在 Obsidian 里查看

用 Obsidian 打开 `vault`。`00-总览/分类总览.base` 是 Bases 视图,按分类或按 visibility 分组,显示每组条数。在 Obsidian 里改了笔记,basic-memory 会重新索引。

## 备份

- `scripts/backup.ps1`:先 git 提交,再用 `git archive` 打包已跟踪文件到 `backups/`。
- 不含 cache、backups、bin、tools、apps,不含密钥和 `*.env`(由 `.gitignore` 控制)。
- 只在本机,不上传。
- 每日 00:00 的计划任务已按你的批准注册。
- 不要把密钥放进 `vault`、`her` 或 `scripts`。`git add -A` 会纳入没被 `.gitignore` 匹配的新文件。

## 排错

- 搜不到已有内容:换短关键词或同义词重试一次(每个问题最多搜索 2 次);仍无,检查服务是否在运行(计划任务 `AI-Memory-HTTP` 通过 `scripts/run_task.py serve` 启动 `http://127.0.0.1:8767/mcp`；`serve.ps1` 可供手动运行)。
- 新写的笔记搜不到:索引需要一点时间;让 Codex 重建索引。
- LM Studio 调用 `mcp/basic-memory` 返回 403:需在 LM Studio 的 Server Settings 里开启「Allow calling servers from mcp.json」。
- 笔记前置属性被工具重新格式化(例如 tags 变成多行):无害。

## 本机入口

- Obsidian：`E:\AI-Memory\apps\Obsidian\Obsidian.exe`，打开 vault 的 `00-总览/分类总览.base`。
- LM Studio：新聊天选择预设「她的图书馆」，启用 basic-memory。图书馆仅启用 read_note/search_notes/write_note/edit_note 四项，以减少工具定义开销。
- HTTP登录自启任务：AI-Memory-HTTP。每日备份任务：AI-Memory-Daily-Backup，本机00:00，错过后补跑。
- 目录笔记读取约357–453 token；工具定义是额外开销，不计入这个数字。

## DeepSeek Harness 桌面端

- 只接入**桌面 profile**；小千使用的 headless profile 未改动，没有配置图书馆 MCP，但**尚未建立访问隔离**：共享服务无认证，同一用户下的进程都能连 8767 或直接读 vault，“未配置”不等于“读不到”（图书馆目前全为 private）。
- 配置文件：`C:\Users\<you>\.dsh\profiles\desktop\cordis.patch.yml`。要点：
  - 新增 MCP 插件必须写成 `- insert: [ {id, name, config} ]`；写成 id 对不上的普通条目会被 loader 静默跳过，Harness 不会连接图书馆。
  - MCP：`serverName: memory`、`streamable-http`、`http://127.0.0.1:8767/mcp`，模型看到的工具名为 `mcp__memory__<tool>`。
  - 本地模型 provider `strata-local`（`127.0.0.1:8080/v1`）。手写模型必须声明 `reasoningEfforts`（`off` / `low`），否则任何推理档位都会报 `UNSUPPORTED_REASONING_EFFORT`；默认档位为 `off`（不带推理参数）。
  - 新建会话的默认模型已改为本地 Strata，不再是 DeepSeek 云端，影响所有桌面新会话。
- 规则注入：打开 `E:\AI-Memory` 工作区时，Harness 自动加载本目录的 `AGENTS.md`（图书馆读写规则）。全局 `~/.dsh/AGENTS.md` 不存在也不要创建——它无法按 profile 限定，会同时作用于 headless。
- 改配置后需**完全退出并重启** Harness（关窗口不够）才会生效。改前备份在 `backups/`。
- 实测（2026-10-27）：明确要求用 `mcp__memory__search_notes` 时，能搜到并读取笔记，答出台式机为 MSI RTX 5090 Suprim。`AGENTS.md` 里没有“默认使用图书馆”规则时，本地模型倾向先用系统命令或直接读 vault 文件；加上该规则后（2026-10-27），不点名工具的普通问句“我的显卡是什么？”也会先 `search_notes`、再 `read_note`，并答出 MSI RTX 5090 Suprim。规则只在新会话的第一次请求时加载。
- `scripts/connect_dsh.py` 是首次迁移脚本，已加防护，默认拒绝运行。

## 私密库（健康、存款、生日等）

- 位置：`E:\AI-Memory-private\vault`，basic-memory 项目 `private`，在 Git 仓库之外，**不在每日备份范围内，需另行备份**。
- 服务：`127.0.0.1:8768`（`scripts/serve-private.ps1`，`--project private`）。8767 仍只服务 `main`。两个服务各只暴露自己的项目内容，已实测互相搜不到、读不到。
- 只配给主人本人的入口：Claude Code（`memory-private`）、Codex（`memory-private`）、桌面 Harness（`mcp-private`，serverName `private`）。**对外入口（小千，以后接 QQ/微信的 Harness 会话）不得配置 8768**，最多配 8767。
- 身份由接入入口决定，不由对话内容决定；规则见 `scripts/memory-rules.md` 的「私密库(owner-only)」。
- 限制：这是配置层的逻辑隔离，不是操作系统级隔离。8768 无认证，同一 Windows 用户下的其他进程能直接连；QQ Bridge 默认持有 DSH 会话签名密钥，它被攻破时可以开完整权限会话。接 QQ 前必须实测 `qq-chat` 预设的会话工具列表里没有 `mcp__private__*`；不要开 QQ Bridge 的 `closed-agent` 模式。
- 自启：计划任务 `AI-Memory-Private-HTTP` 尚未注册（注册被权限拦截，待主人亲自执行）；`scripts/run_task.py` 已加 `serve-private` 命令。未注册前，重启电脑后需手动运行 `scripts/serve-private.ps1`。


## main 图书馆服务器代码适配

[部署、主人专属 MCP 接入、每日版本备份与恢复说明](integrations/main-server/README.md)。本项目适配官方 basic-memory 0.24.1，真实索引锚点为 `00-总览/目录`；包含脱敏配置与合成测试，使用前请核对模板路径、账户和时区。此目录不包含知识库数据、人格或运行凭据。
