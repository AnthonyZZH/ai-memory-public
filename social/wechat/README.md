# xiaoqian-wechat 社交加固补丁

上游基线为已去隐私的 `AnthonyZZH/xiaoqian-wechat`，提交 `27bb88c33d3b9e43ffb368f576b736ec090b88be`。`vendor.lock` 同时固定原始树、补丁、应用后树的 SHA256。上游仓库保持不动；源码只在新的构建输出目录中出现。

离线构建示例（输出目录必须不存在）：

```powershell
& E:\AI-Memory\tools\xq-engine\Scripts\python.exe -B social\wechat\build\fetch-and-patch.py --source-root E:\Projects --out 'E:\Codex Development\tmp\wechat-build-new'
```

不传 `--source-root` 时沿用共享构建器的 GitHub 固定提交下载和摘要验证。构建不安装、不运行源码，不修改 git。不要从构建产物执行原上游的危险功能测试。

补丁移除 agents/Forge/lms 的执行实现，替换 Brain 为 DeepSeek HTTPS JSON 模式、无 tools 传输。配置仅存 `base_url`（默认 `https://api.deepseek.com/v1`，仅允许官方主机）、`model.identifier`、`api_key_env`（默认 `DEEPSEEK_API_KEY`）；密钥由运行进程环境注入，不放 settings、命令行或日志。拒绝代理继承和 HTTP 重定向。未调用真实 DeepSeek 进行测试。

上下文按 mode+chat 哈希隔离：最近最多20条且总计2000字符；旧消息逐批压缩为600字符内滚动摘要；每轮从该聊天自己的 memory 词法检索最多5条、每条200字符。人物设定上限12000字符，目录最多20个表情，不附加跨聊天摘要或未约束的额外上下文。历史被改写时停止压缩而不复用错位摘要。摘要文件、history、memory 是本聊天的业务存储，**不是诊断日志**，不能提供给其他聊天。

原生 Initiative 和 may_proactive 保留；最终发送阶段加持久预算及进程/线程锁：主动3分钟冷却、12条/小时、01–08静默，`social_timezone` 默认 Asia/Shanghai。支持 UTC 及运行环境已提供时区数据库的 IANA 名称。必回不占主动预算；文本+目录表情作为一轮预留一次；发送不确定也保留预留，暂停后人工检查，避免重试刷屏。未知/损坏状态拒绝发送。保持每个机器人仅一条 UI worker，不能并发切换同一微信桌面。

表情必须是配置目录中的索引ID，索引文件名也校验边界、类型、大小和符号链接；不接受模型路径。文本带路径、媒体标记、URL 或 `__SKIP__` 整轮丢弃。传统 relay/handoff/direct say/show 发送入口关闭，正常回复只能用当前 Runner 的 adapter。诊断日志只存时间和固定事件码，不存聊天名、正文、密钥或原始异常。GUI保留普通聊天显示；错误GUI仅显示事件码。

保留原生每聊天 memory 学习与检索，学习请求也限制为20条/2000正文字符、已有事实最多5条；输出类型、条数和长度由代码校验，再经原有 Memory.apply 过滤。滚动摘要独立正常运行。模型页改为 API 元数据设置，绘图页仅显示禁用提示，其余危险执行入口为不可用/no-op。微信好友默认应全部可用：部署时由已登录的小号好友列表建立任意多 private chats；原上游安全准入仍要求窗口进入可信聊天清单，不根据群里自称主人授权。此阶段不读取真实好友列表或生成账号配置。

测试使用上游去隐私发布库已有的 Python/Pillow 环境，仅导入纯控制代码，不打开 GUI、不导入/驱动微信适配器、不登录，不联网。

```powershell
& E:\AI-Memory\tools\xq-engine\Scripts\python.exe -B social\wechat\tests\run.py --python E:\Projects\xiaoqian-wechat\.venv\Scripts\python.exe --source-root E:\Projects --work-root 'E:\Codex Development\tmp\v3.1b'
```

同一组28项断言在原始锁定归档和构建器真实应用补丁后的归档分别执行，保留 before.log/after.log/results.json，不清理临时文件。部分新增能力在上游不存在，前测因此标记 ERROR；其他反例观察到未授权头、跨聊天上下文、路径解析、日志正文、未禁用能力或未过滤 SKIP 等实际失败。history、memory、sender 索引使用聊天类型加完整名字的哈希，避免显示名清洗/截断碰撞造成私聊串群。不把这些结果当作真实微信桌面验收。

## V3.2 独立数据目录

启动前可设定 `XQ_WECHAT_DATA_DIR` 为绝对目录，例如 `C:\xiaoqian\data\wechat`；未设置时仍沿用 `app/data`。相对路径会拒绝。环境变量必须在导入应用模块前设置。`settings.json`、personas、history、memory 和 stickers 的默认目录随 DATA 迁移；微信客户端自身缓存及 app.py 的 startup_error.txt 不由此保证迁移，实际部署时另查。`api_key_env` 应配置为 `XQ_DEEPSEEK_API_KEY`，由主人在服务器设置机器级环境变量。

本地离线验证：原有 28 项配对契约（原始 0/28、补丁后 28/28）与独立目录写入额外测试通过。测试不驱动微信 UI 或真实 API。额外测试 `tests/data_directory.py` 在全新子进程设定环境变量，实例化默认 Settings、PersonaStore、StickerLibrary 并核验目标文件和目录。
