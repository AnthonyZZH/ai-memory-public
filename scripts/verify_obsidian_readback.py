import asyncio,pathlib,json
from fastmcp import Client
async def main():
 async with Client('http://127.0.0.1:8767/mcp') as c:
  r=await c.call_tool('read_note',{'identifier':'00-总览/目录','project':'main','output_format':'json'})
  text='\n'.join(x.text for x in r.content if hasattr(x,'text'))
  pathlib.Path(r'E:\AI-Memory\cache\obsidian-edit-readback.json').write_text(text,encoding='utf-8')
  print(text[:1800])
asyncio.run(main())