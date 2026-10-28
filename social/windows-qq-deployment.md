# QQ Windows 部署清单（仅准备，尚未执行）

适用：独立社交用 Windows Server 2022；不复制主人 home、DSH desktop/headless、私密库或本机凭据。微信走自己的加固版 xiaoqian-wechat，不再部署 wechat-ai。本文不含真实凭据，也不代表已部署或已完成服务器验收。

## 版本与安装

1. 从 [NapNeko/NapCatQQ Releases](https://github.com/NapNeko/NapCatQQ/releases) 选一个人工审核的 Windows Shell 发布版本，登记 tag、资产名、SHA256、对应 QQ 版本。不要使用 latest 更新脚本或第三方整合包。本步骤未下载或选定生产安装包。
2. 按 [官方 Windows Shell 安装说明](https://napneko.github.io/guide/boot/Shell) 安装固定版本 QQ，解压 `NapCat.Shell.zip`，使用 `launcher.bat`。不使用带自动更新管理功能的 Desktop 管理器或一键安装器。扫码和账号确认由主人完成。
3. 使用社交专用用户与目录，示例 `E:\XQ-Social\napcat`、`E:\XQ-Social\dsh-home`、`E:\XQ-Social\qq-workspace`。这些是部署建议，尚未创建。微信 UI 自动化需要其登录用户的交互桌面；不要把登录后运行等同于无人登录服务。

## 本机监听和两个独立 token

- `napcat/config/webui.json`（实际相对于该固定版本的 Shell 安装目录）：`host: "127.0.0.1"`、`port: 6099`，设置独立的至少 32 随机字节 WebUI token；`accessControlMode: "whitelist"`、`ipWhitelist: ["127.0.0.1"]`、`enableXForwardedFor: false`。不要使用默认 token，不复制含 token 的启动 URL到日志或报告。管理通过主人的受限远程桌面；不开放 6099 公网端口。
- `config/onebot11_<QQ>.json` 的 `network.websocketServers` 只启用一个 forward WS 服务：`host: "127.0.0.1"`、`port: 3001`、`token: <另一个随机 token>`、`enable: true`、`reportSelfMessage: false`、`messagePostFormat: "array"`。其他 HTTP/SSE/WS 服务与反向客户端数组全部为空。OneBot token 与 WebUI token 不相同。
- dsh-napcat 的 `mode: forward`、`url: ws://127.0.0.1:3001`、`token` 与上述 OneBot 一致。不要把 token 放到 URL。以安装版本 schema 验证完整配置，示例只列关键字段，不覆盖该版本其余必填字段。
- Windows 防火墙与阿里云安全组都不对外放行这些端口，也不开放 DSH Web 管理端口。部署验收时检查实际 IPv4/IPv6 监听，拒绝 `0.0.0.0` / `::` 意外监听。

依据：[官方 WebUI 配置](https://napneko.github.io/config/basic)、[OneBot 与 WebUI token 区分](https://napneko.github.io/NapCatQQ-Desktop/docs/connections/)。字段还核对了 V3.0 固定源码的 `packages/napcat-onebot/config/config.ts`、`packages/napcat-webui-backend/src/helper/config.ts`。

## 关闭更新和第三方服务

- 只用人工固定 Shell 文件；不启用管理器的自动检查/更新，不注册更新计划任务，不调用 WebUI 更新接口，不安装插件市场内容。QQ 的自动升级也在安装后关闭，人工升级前先备份并回归测试。未发现可据以承诺关闭全部更新的统一 `autoUpdate:false` 字段，因此不虚构该开关。
- OneBot `musicSignUrl: ""`、`enableLocalFile2Url: false`、`imageDownloadProxy: ""`，`network.plugins: []`；禁用所有非本机 HTTP 上报、第三方音乐签名和插件扩展。
- **第三方 rkey 不能只靠上述配置关闭。** 审计固定源码 `packages/napcat-core/apis/file.ts` 初始化了两个第三方 rkey provider，原生获取失败会调用 `rkeyManager.getRkey()`。上线前必须对所选版本另做小补丁：provider 列表清空并删除/禁用该远程 fallback，保留 QQ 自身获取失败即失败；验证没有请求这两个第三方域名。不要以“不开音乐卡”代替这个验证。这里仅列部署前置项，没有擅改 NapCat 源码或发布二进制。
- 部署时记录进程出站目的地，仅批准 QQ 自身服务、配置的 DeepSeek 和必要基础设施；其他遥测/第三方请求不得因默认值而放行。对不可关闭的非必要服务应停止上线并评审，不临时加宽网络规则。

## 独立 DSH profile

使用 **qq-social** 自定义 Web profile，单独 `DSH_HOME=E:\XQ-Social\dsh-home` 和工作目录，绝不复用主人 `desktop`、`headless` 或 `standard` 工具全集。Node 至少 24.9，部署锁定具体版本。DSH CLI 也锁定经审计的版本；保留 Node/CLI/npm 依赖锁和资产摘要。

1. 依据 `social/vendor.lock` 的 `95e818a1a47e0d2dfc15ba374bffa5bf50cea2f6`，用 `social/build/fetch-and-patch.py` 拉取、校验并应用 `social/patches/dsh-napcat/0001-social-boundaries.patch`。不要直接安装未打补丁的 npm 最新包，不重新编译覆盖已经修补的 lib。
2. qq-social 的 `package.json` 注册本地已打补丁的插件依赖及 `dsh.profile.bundles`，profile `cordis.patch.yml` 用插件实际 schema 配置。最终合成配置要单独审查；本清单不执行 profile 初始化，也不复制主人配置。CLI 支持 `dsh --profile <name>`；从 Web 模板创建和首次启动应分开部署审查，**不要每次启动都传 `--from-default-profile`，那会重置 profile**。
3. 进程环境设置 `DSH_TELEMETRY_DISABLED=1`，profile 另外移除 session telemetry/反馈导出；Web 启动加 `--no-open`，只监听本机。用配置导出检查时只输出工具名/计数，先过滤密钥，不把完整配置打印到日志。
4. persona 仅导入 `publish-public.py` 导出的 `persona-social.txt`；MCP 只连接服务器上的 public 实例或经过认证的只读公开检索网关。不得连接主人 8767/8768，不挂载主库或私密库，不开放文件系统、命令、通用发送工具。禁用原 agent 的 workspace/shell 工具，审批 `never` 不能代替“工具未注册”。
5. 准入：`dmPolicy: allowlist`，`allowFrom: [<任意多个主人批准的QQ号>]`；`groupPolicy: allowlist`，`groupAllowFrom: [<任意多个群号>]`。空白名单拒绝，不设群数上限，不禁用全部私聊。
6. `triggerKeywords: ["小千"]`；启用原生 proactive，冷却 10 分钟、每小时 4 条、`proactiveQuietHours: "01:00-08:00"`、`socialTimezone: "Asia/Shanghai"`。强制 `__SKIP__` 不发送，回复只回触发它的聊天。自动长期记忆使用已打补丁后的关闭模式或社交 file 后端，不能使用主人 mnemon。
7. 验收：多个群与私聊交错时不串话；名单外私聊不进模型；工具列表不含任意目标发送/读文件/raw API；路径媒体不被发送；主动计数重启保持且分段按一条；必回不消耗主动预算；错误不回群，日志无正文；OneBot/WebUI 错 token 均拒绝。最后再由主人授权小号上线。

DSH CLI/profile 依据：[审计固定提交的 CLI README](https://github.com/deepseek-ai/deepseek-harness/blob/22ddee3792402c3e70ec5f86a63c3e3e895a2f60/apps/cli/README.md)。本次没有安装、启动、联网服务器、登录或执行此清单。
