r"""DeepSeek Harness 桌面 profile 的【首次迁移】脚本。已于 2026-10-27 执行并验收，不要重复运行。
最终生效的配置以 C:\Users\<you>\.dsh\profiles\desktop\cordis.patch.yml 为准。
若确需重建，先备份该文件，再带 --first-migration 运行本脚本。
"""
import sys
if '--first-migration' not in sys.argv:
 sys.exit('已完成首次迁移，拒绝重复运行；确需重建请加 --first-migration（见文件头说明）。')
from pathlib import Path
import datetime,yaml
root=Path(r'E:\AI-Memory'); p=Path(r'C:\Users\<you>\.dsh\profiles\desktop\cordis.patch.yml')
stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
s=p.read_text(encoding='utf-8-sig')
b=root/'backups'/f'dsh-desktop-cordis-before-{stamp}.yml'; b.write_text(s,encoding='utf-8')
if 'serverName: memory' not in s:
 s+='\n# Shared owner library (desktop profile only). 新增插件必须用 insert，id 对不上的普通条目会被 loader 跳过\n- insert:\n    - id: mcp-memory\n      name: "@deepseek-ai/dsh-mcp-client"\n      config:\n        serverName: memory\n        transport: streamable-http\n        url: http://127.0.0.1:8767/mcp\n        toolCallTimeoutMs: 120000\n'
if '      strata-local:' not in s:
 needle='    providers:\n      lmstudio:'
 assert needle in s,'provider anchor missing'
 block='''    providers:
      strata-local:
        displayName: "Strata Qwen 本地"
        api: openai-completions
        baseURL: "http://127.0.0.1:8080/v1"
        headers:
          Authorization: "Bearer strata-local"
        defaultContextWindow: 131072
        defaultMaxTokens: 16384
        models:
          - id: qwen3.8-flash-next-iq3_s
            name: "她 · Qwen3.8 Flash Next (Strata)"
            contextWindow: 131072
            maxTokens: 16384
            input: [ text, image ]
            reasoningEfforts:
              off:
              low: low
      lmstudio:'''
 s=s.replace(needle,block,1)
s=s.replace('    provider: deepseek-account\n    model: deepseek-flash\n    reasoningEffort: high','    provider: strata-local\n    model: qwen3.8-flash-next-iq3_s\n    reasoningEffort: off',1)
yaml.safe_load(s)
p.write_text(s,encoding='utf-8')
rules=(root/'scripts/memory-rules.md').read_text(encoding='utf-8')
text='''# 她的桌面图书馆

此工作区用于主人与本地管家。图书馆项目 main，MCP serverName 为 memory，工具名可能带 mcp__memory__ 前缀。
当前本地大脑：Strata 的 Qwen3.8 Flash Next；人格与说话方式模板在 her/persona.md、her/voice.md，按需读取。空白部分不得编造；规则不代表已经填写人格。
所有长期笔记仅写入 vault。setup日志、缓存及测试输出写入 scripts、cache 或 SETUP_LOG.md，不混入种子笔记。
开局只读 00-总览/目录，不自动读取人格空模板或全部笔记。使用简体中文。

'''+rules
ag=root/'AGENTS.md'
if ag.exists():(root/'backups'/f'AI-Memory-AGENTS-before-{stamp}.md').write_bytes(ag.read_bytes())
ag.write_text(text,encoding='utf-8')
print('desktop patch updated; headless untouched; workspace rules created; backup:',b)