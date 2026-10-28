import asyncio,json,pathlib,tiktoken,hashlib
from fastmcp import Client
R=pathlib.Path(r'E:\AI-Memory')
async def main():
 async with Client('http://127.0.0.1:8767/mcp') as c:
  out={}
  for name,args,key in [('read_note',{'identifier':'00-总览/目录','project':'main'},'index'),('search_notes',{'query':'我的显卡是什么','project':'main','page_size':5,'search_type':'hybrid','compact':True},'gpu'),('search_notes',{'query':'我在做哪些项目','project':'main','page_size':5,'search_type':'hybrid','compact':True},'projects')]:
   res=await c.call_tool(name,args)
   out[key]={'content':[x.model_dump(mode='json') for x in res.content]}
   print(key,json.dumps(out[key],ensure_ascii=False)[:5000])
  text='\n'.join(x.get('text','') for x in out['index']['content'])
  print('INDEX_TOKENS', {enc:len(tiktoken.get_encoding(enc).encode(text)) for enc in ['cl100k_base','o200k_base']})
  R.joinpath('cache/mcp-verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
asyncio.run(main())