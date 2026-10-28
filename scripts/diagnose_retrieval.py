import asyncio,json,pathlib
from fastmcp import Client
async def main():
 out=[]
 async with Client('http://127.0.0.1:8767/mcp') as c:
  for q,t,th in [('我的显卡是什么','vector',None),('我的显卡是什么','vector',0.0),('显卡','hybrid',None),('我在做哪些项目','vector',0.0),('项目','hybrid',None)]:
   a={'query':q,'project':'main','page_size':5,'search_type':t,'output_format':'json','compact':True}
   if th is not None:a['min_similarity']=th
   r=await c.call_tool('search_notes',a)
   row={'args':a,'result':[x.model_dump(mode='json') for x in r.content]};out.append(row)
   print(json.dumps(row,ensure_ascii=False))
 pathlib.Path(r'E:\AI-Memory\cache\retrieval-diagnostics.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
asyncio.run(main())