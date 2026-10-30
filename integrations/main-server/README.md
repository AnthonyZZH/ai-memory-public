# AI Memory：main 图书馆服务器适配

本目录提供本项目编写的 MCP 客户端适配、Windows 运行脚本、单向版本备份及恢复说明。底层服务采用官方 `basic-memory==0.24.1`，不是 basic-memory 的分支，也没有修改上游源码。

本次交付面向 `AnthonyZZH/ai-memory`（私有代码库）和 `AnthonyZZH/ai-memory-public`（公开代码库）。代码库的可见性与 basic-memory 的 `main` / `private` 项目是两个独立维度。本包只接 main，不包含任何笔记、人格或 private 数据。

## 目录

| 目录 | 用途 |
|---|---|
| adapter/ | Node 24、零运行依赖的 Streamable HTTP MCP 客户端及主人 Agent 注册函数 |
| deployment/ | Windows main 服务独立配置、无窗口运行、开机任务模板 |
| backup/ | 既有 SSH 认证拉取、逐文件 SHA256 校验、版本保留与每日任务模板 |

所有路径均为示例：服务器根 `C:\AI-Library\main`，备份根 `E:\AI-Library-Backups`，SSH 别名 `library-host`。使用前应修改模板常量并核对对应账户、路径和权限。代码不创建 SSH 凭据，不调整防火墙。

## 服务器部署

1. 使用既有 Python 3.12 在示例服务器根新建 `venv`；从官方 PyPI 安装 `basic-memory==0.24.1`，固定依赖版本，保留安装记录。不要复制其他机器的整个虚拟环境。
2. 将获准迁移的 **main** Markdown、附件及笔记元数据放入 `vault`，生成逐文件大小和 SHA256 清单，迁移后逐项核对。保留原件；不迁移账号配置、数据库、凭据或 private。
3. 该上游版本默认具备语义运行时。本部署只使用全文检索，因此在这个独立环境中移除 `sqlite-vec`，使官方代码走全文回退；同时设置离线环境，禁止模型自动下载。不会修改上游源码。之后普通依赖安装可能重新补入该包，升级前须重新核对这一策略；依赖完整性检查会指出这个有意排除项。
4. 将 `deployment/` 三个脚本复制到示例服务器根，用该 venv 的 Python 执行 `configure_library.py`。它核对版本、仅登记 main、全文检索与离线约束，拒绝覆盖已有配置。已有安装须人工审阅差异，不删除配置重来。
5. 用 `register_main_task.ps1` 创建任务前审阅其中固定根目录。任务使用当前既有账户、S4U、Limited 和开机触发，不保存密码；已存在同名任务时拒绝覆盖。若系统策略不支持，报告具体错误，不自动增加账户权限。
6. 服务只监听 `http://127.0.0.1:8767/mcp`。验证实际进程、回环监听、main 原索引元数据及一次只读检索后，再交给宿主接入。服务无须 RDP 或可见桌面。

本次实际部署曾核实健康 `ready`、只读检索成功；这些历史结果不代表他人部署自动通过。真实原索引锚点为 **`00-总览/目录`**，此前的 `00-索引/目录` 是错误路径。迁移到其他库时必须配置其真实锚点，不能创建空笔记伪造健康。

## Agent 接入与隔离

```js
import {createMainLibraryAdapter, registerOwnerLibraryTools, LIBRARY_TOOL_NAMES}
  from './adapter/src/index.mjs';

const library = createMainLibraryAdapter({
  chats: trustedHostConfig.chats,
  url: trustedHostConfig.libraryUrl,
  probeIdentifier: '00-总览/目录',
});
// 在宿主现有 registerAgent 中调用，并先把 LIBRARY_TOOL_NAMES 加入主人专属白名单。
registerOwnerLibraryTools({
  agentCtx, agent, chatId, adapter: library, defineTool,
  isActive: id => hostStillAuthorizesOwnerPrivateChat(id),
});
```

`trustedHostConfig`、`hostStillAuthorizesOwnerPrivateChat` 是宿主应提供的可信接口，不由模型参数生成。保留宿主原有 Agent 身份校验、会话绑定、动态撤销和取消信号。

工具仅在主人私聊注册，固定 `project: main`。普通群聊和其他私聊在联网前拒绝。不得把 main 接入默认社交召回，或把私库工具全局开放。客户端拒绝公网端点、8768、项目覆盖、任意 MCP 方法、显式路由 URL 和越界路径。服务仍须由可信宿主管理；客户端不是恶意服务的沙箱。

提供 health/search/read/write/edit。新建强制不覆盖；编辑必须提供刚读取的 checksum，单次 find_replace 只替换一处。写入超时或无法确认结果时返回 `LIBRARY_WRITE_OUTCOME_UNKNOWN`，必须先只读核对，不能自动重试。未配置或服务断开会明确报错，不返回伪造的空库。

## 备份、单一写入端和恢复

服务器 main 是唯一主写端，原本机库保留为迁移快照。备份只用现有认证 SSH 从服务器拉到新版本目录，保留全部成功和失败版本，不做删除镜像或双向覆盖。脚本只归档 vault，数据库和运行状态留在 vault 外。

`backup_main.py` 核对服务器前后两份完整 SHA256 清单，再逐项核对本地提取结果。拒绝路径越界、链接、重复归档项与空替代库；成功标记最后写入。这保证文件清单一致性，不声称应用事务级原子快照。

将 `backup_main.py`、`run-backup.ps1` 放入备份根的固定 `_scripts`，审阅 SSH 别名和路径。Python 示例使用 PATH 中的 `python`，定时任务部署时应替换为核实过的稳定绝对路径。`install-task.ps1` 默认只预览，加 `-Create` 才创建任务，并拒绝覆盖同名任务。

任务示例为 Melbourne 每日 20:00，核对本机 Windows 时区 `AUS Eastern Standard Time`；使用既有当前用户 Interactive/Limited、隐藏窗口，不保存密码。需要用户登录、备份盘可用及现有 SSH 认证有效。登录或错过触发时补跑，失败每 30 分钟重试最多 3 次，之后等下一次触发。离线期间无法补出未保留的历史状态。

恢复应人工选择带 `SUCCESS.json` 的版本，重新验证 manifest，协调暂停写入，并恢复到获准的新目标；本工具不提供自动反向覆盖。损坏或部分版本不作为恢复源。保留原目录便于回退。

## 针对性验证

```powershell
node --test adapter/tests/library.test.mjs
Set-Location backup
python -m unittest -v test_backup.py
```

测试只用合成数据和 mock，不连接真实库、不调用模型、不注册任务。真实验收另核对 main 锚点、只读搜索、监听、任务身份和备份哈希；不将这些机器的原始日志或库清单提交到公开仓库。

## 发布范围与许可

本包只含本项目的适配源码、模板、说明和合成测试；不包含 main/private vault、原人格、聊天、数据库、部署机器地址、密钥、迁移归档、运行日志或安装环境。公开更新应使用明确文件白名单，不能运行旧的笔记/人格导出器代替代码发布。

basic-memory 上游声明 AGPL-3.0-or-later，须保留相应第三方许可和义务。本包不将上游改称 MIT，也不替仓库所有者新增整个项目的许可声明。
