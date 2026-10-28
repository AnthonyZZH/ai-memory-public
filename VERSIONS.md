# 组件版本（固定安装与复现记录）

| 组件 | 版本 / 固定值 |
|---|---|
| uv | 0.13.1 (62faed335)；本机已有，未升级 |
| Python | 3.12.11；uv运行时 |
| basic-memory | 0.24.1；E:\AI-Memory\tools\basic-memory；auto_update=false |
| 全部 Python 依赖 | scripts/requirements.lock.txt 精确锁定173项 |
| FastEmbed / ONNX Runtime | 0.9.1 / 1.31.0 |
| 语义模型 | sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2；384维 |
| 模型分发仓库 | Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q |
| 模型修订 | faf4aa4225822f3bc6376869cb1164e8e3feedd0；逐文件SHA256见scripts/embedding-model-lock.json |
| Obsidian | 1.14.5；官方Windows安装包SHA256: 4b95aa855062fb253439c392a32b536c3f9f22ac7fad04f1a6cbf176ecbcfa2a |
| LM Studio | 0.4.26+4；已有安装，未升级 |
| lms CLI | dcefd5a |
| Claude Code | 2.1.307；验收模型claude-sonnet-5-5 |
| Codex CLI | 0.163.0；已有安装，未升级 |
| DeepSeek Harness | DSH 0.2.1-rc.2（Electron 44.7.0）；E:\DeepSeek Harness，已有安装，未升级；仅桌面 profile 接入图书馆 |
| Harness 本地模型 | Strata qwen3.8-flash-next-iq3_s，127.0.0.1:8080/v1，窗口131072；推理档位 off（默认）/ low |

记录日期：2026-10-27。不得自动升级图书馆服务。客户端现有安装按以上版本验收；客户端更新策略另见SETUP_LOG.md。模型缓存保留在cache/fastembed。升级前更新本文件并重新验收。
## V3.2 社交服务器资产与锁定状态（2026-10-28）

- NapCat Shell: [v4.18.41 正式版](https://github.com/NapNeko/NapCatQQ/releases/tag/v4.18.41)，`NapCat.Shell.zip`，SHA256 `6801f93e533846cea05f4f531874a0e84371ab2331c5585b57cd7e3b869cf96b`；本地下载 SHA256 与 GitHub Release 资产声明一致。官方未说明此版本特定 QQ 下载版本；相邻 [v4.18.37 验证说明](https://github.com/NapNeko/NapCatQQ/releases/tag/v4.18.37)列出 Windows QQ 9.9.33-52230 的无登录测试，[v4.18.33](https://github.com/NapNeko/NapCatQQ/releases/tag/v4.18.33)提供其腾讯 CDN 地址。实际登录仍需验收。
- NTQQ: 预选 9.9.33-52230，腾讯官方地址 `https://qqdl.gtimg.cn/qqfile/QQNT/9.9.33/release/497e2f1f/QQ_9.9.33_260813_x64_01.exe`；下载与 SHA256 尚未完成，未锁定。
- 微信: 腾讯 `https://dldir1.qq.com/weixin/Windows/WeChatSetup.exe`；已下载，FileVersion 3.9.12.1000（ProductVersion 3.9.11.0）；SHA256 `c29fc05630cfc95ef6483f6b5b52aabfe74265bb260e210e78ae437d305d8990`；Authenticode 状态 Valid，签名者 `Tencent Technology (Shenzhen) Company Limited`。动态下载地址在以后可能变化，部署必须使用并复核这份已锁定文件。
- DSH CLI: 截至查询时官方 npm registry 没有满足 `>=0.2.1-0 <0.3.0-0` 的 0.2.x 正式版；latest 为 0.2.1-rc.2，属预发布。按主人正式版要求，不自动选 RC，不安装；正式版和依赖摘要仍未锁定。
- dsh-napcat: commit `95e818a1a47e0d2dfc15ba374bffa5bf50cea2f6`，补丁及树摘要见 `social/vendor.lock`。
- xiaoqian-wechat: commit `27bb88c33d3b9e43ffb368f576b736ec090b88be`，补丁及树摘要见 `social/wechat/vendor.lock`。
- NapCat 已知风险：本次接受保留第三方 rkey fallback 源码，以 hosts、Windows 出站规则及实际验证作为首轮缓解；规则无法自动证明覆盖 DNS 变化、代理或硬编码新地址，必须验收并持续关注。不要把请求内容是否包含聊天数据视为已独立验证的事实。

### DSH RC 决策更新（2026-10-28）

主人接受预发布，锁定官方 npm `@deepseek-ai/dsh@0.2.1-rc.4`（查询时兼容范围内最新 RC）；tarball `https://registry.npmjs.org/@deepseek-ai/dsh/-/dsh-0.2.1-rc.4.tgz`，registry integrity `sha512-8gxl6zOi6vx1sDolH+vjh9txrpbXD+t74Z2YfWkEBtR3xP2YEtk0bbLkgLZRnYQgDxCoXitXyXDKn5k0+6iXrg==`；本地下载核验相同 SHA-512，SHA256 `1fddead34d3c943b7a4eed1d614e14fa19925803455e28c5141645caf4b02d13`。尚未验证 npm 全部依赖树或安装运行。

NTQQ 服务器资产已核验：9.9.33.52230，SHA256 `b25c0d3ce9df764074a9118d0ded927e1b2d7ebf60e306112e8df18a040ec492`，Tencent Authenticode 有效；与 [Microsoft winget 官方清单](https://github.com/microsoft/winget-pkgs/blob/master/manifests/t/Tencent/QQ/NT/9.9.33.52230/Tencent.QQ.NT.installer.yaml)一致。

## V3.3 服务器运行库

Microsoft Visual C++ 2015–2022 Redistributable x64：服务器注册表 `v14.44.35211.00`、Installed=1；主人报告从微软官方下载、签名有效、安装 exit 0，安装包 SHA256 未由本代理复核。官方分发入口 `https://aka.ms/vs/17/release/vc_redist.x64.exe` 是可更新地址，非该版本固定哈希。
