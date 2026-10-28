from pathlib import Path
p=Path(r'E:\AI-Memory\scripts\serve.ps1')
s=p.read_text(encoding='utf-8')
s=s.replace("$env:BASIC_MEMORY_NO_PROMOS = '1'", "$env:BASIC_MEMORY_NO_PROMOS = '1'\n$env:HF_HUB_OFFLINE = '1'")
p.write_text(s,encoding='utf-8')
p=Path(r'C:\Users\<you>\.codex\config.toml')
s=p.read_text(encoding='utf-8')
needle='[mcp_servers.basic-memory]\nurl = "http://127.0.0.1:8767/mcp"'
if needle in s and 'enabled_tools = ["read_note", "search_notes", "write_note", "edit_note"]' not in s:
 s=s.replace(needle,needle+'\nenabled_tools = ["read_note", "search_notes", "write_note", "edit_note"]')
p.write_text(s,encoding='utf-8')
p=Path(r'E:\AI-Memory\README.md')
s=p.read_text(encoding='utf-8')
s+='\n## 本机入口\n\n- Obsidian：`E:\\AI-Memory\\apps\\Obsidian\\Obsidian.exe`，打开 vault 的 `00-总览/分类总览.base`。\n- LM Studio：新聊天选择预设「她的图书馆」，启用 basic-memory。图书馆仅启用 read_note/search_notes/write_note/edit_note 四项，以减少工具定义开销。\n- HTTP登录自启任务：AI-Memory-HTTP。每日备份任务：AI-Memory-Daily-Backup，本机00:00，错过后补跑。\n- 目录笔记读取约357–453 token；工具定义是额外开销，不计入这个数字。\n'
p.write_text(s,encoding='utf-8')