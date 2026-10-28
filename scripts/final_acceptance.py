import pathlib,json,re,collections,hashlib
r=pathlib.Path(r'E:\AI-Memory');v=r/'vault'
notes=list(v.rglob('*.md')); names={p.stem for p in notes}
errors=[]
for p in notes:
 s=p.read_text(encoding='utf-8-sig')
 if not re.search(r'^visibility: private\s*$',s,re.M):errors.append(str(p)+': visibility')
 for link in re.findall(r'\[\[([^]|#]+)',s):
  if pathlib.PurePosixPath(link).stem not in names:errors.append(str(p)+': bad link '+link)
p=pathlib.Path(r'C:\Users\<you>\.lmstudio\conversations\<id>.conversation.json')
d=json.loads(p.read_text(encoding='utf-8')); calls=[]; answers=[]
def walk(x):
 if isinstance(x,dict):
  if x.get('type')=='toolCallRequest':calls.append({'name':x.get('name'),'parameters':x.get('parameters')})
  for a in x.values():walk(a)
 elif isinstance(x,list):
  for a in x:walk(a)
walk(d['messages'])
for m in d['messages']:
 for version in m.get('versions',[]):
  if version.get('role')=='assistant':
   for step in version.get('steps',[]):
    if step.get('type')=='contentBlock':
     for block in step.get('content',[]):
      if block.get('type')=='text':answers.append(block.get('text',''))
summary={'markdown_notes':len(notes),'categories':dict(collections.Counter(p.parent.name for p in notes)),'structural_errors':errors,'qwen_calls':calls,'qwen_text':answers,'qwen_conversation':str(p),'strata_restored_generation_ready':True,'http':'http://127.0.0.1:8767/mcp','index_tokens':{'cl100k_base':453,'o200k_base':357},'backup_schedule':'00:00 Australia/Sydney; StartWhenAvailable'}
r.joinpath('cache/acceptance-final.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:val for k,val in summary.items() if k!='qwen_text'},ensure_ascii=False))
p=r/'README.md';s=p.read_text(encoding='utf-8').replace('例如「GPU RTX」','例如「GPU OR RTX」').replace('访问 `http://127.0.0.1:8767/mcp` 的进程由 `serve.ps1` 启动','计划任务 `AI-Memory-HTTP` 通过 `scripts/run_task.py serve` 启动 `http://127.0.0.1:8767/mcp`；`serve.ps1` 可供手动运行');p.write_text(s,encoding='utf-8')
with (r/'SETUP_LOG.md').open('a',encoding='utf-8') as f:f.write('\n- [Codex] Obsidian表格visibility编辑器已实测可用,保持private;手动将目录title冒号改为中文冒号,MCP立即读到新标题。Obsidian自动更新已关闭(updateDisabled=true)。\n- [Codex] LM Studio经Windows MCP完成Qwen27B最终复测:原句“我在做哪些项目”,只调用read_note目录1次,列出8项目并明确状态笔记未说明;无新增笔记。只启用读/搜/写/改4工具,但工具定义仍有额外上下文开销,不能把目录453token视为整次会话成本。\n- [Sonnet+Codex] 最终规则完成并同步三端:主题关键词OR查询、最多2次搜索、最多2篇正文;概览依目录,不得推断未写明状态。备份脚本补齐失败检测、临时归档成功后改名、每日一次约束。\n- [Codex] HTTP任务改用pythonw无窗口启动且重启验收通过,读取Obsidian修改成功;服务只监听127.0.0.1。模型缓存HF_HUB_OFFLINE=1固定使用已校验缓存。午夜备份任务采用同一无窗口启动器。\n- [Codex] 临时LM Studio模型her-memory-test已卸载;Strata profile launch-iq3_s-128k原修订81d8f63e4b86c722恢复,官方返回generation_ready=true、api_identity_verified=true、launch_attested=true。\n')
assert not errors,errors