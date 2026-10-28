import pathlib,httpx,json,os
r=pathlib.Path(r'E:\AI-Memory')
body={'model':'her-memory-test','input':'我在做哪些项目？请按图书馆规则检索后回答，并列出笔记来源。','system_prompt':r.joinpath('scripts/memory-rules.md').read_text(encoding='utf-8')+'\nMCP项目为main。中文整句无结果时缩短为关键词，如项目。不要凭空回答。','integrations':[{'type':'plugin','id':'mcp/basic-memory','allowed_tools':['read_note','search_notes']}],'context_length':16384,'temperature':0,'reasoning':'off','max_output_tokens':1600,'store':False}
token=os.environ.get('LM_API_TOKEN'); headers={'Authorization':'Bearer '+token} if token else {}; res=httpx.post('http://127.0.0.1:1234/api/v1/chat',json=body,headers=headers,timeout=180)
r.joinpath('cache/lmstudio-qwen-acceptance.json').write_text(res.text,encoding='utf-8')
print(res.status_code,res.text[:15000])