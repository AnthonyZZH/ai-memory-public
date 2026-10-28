"""Owner-only memory pull. Dry-run by default; never prints memory or names.

No scheduled task is installed by this program. The first real invocation must
use --initialize to establish the current snapshot as a baseline; old memories
are never silently imported as new. --apply is intentionally explicit.
"""
import argparse, asyncio, base64, hashlib, json, logging, os, re, subprocess, sys
from collections import Counter
from pathlib import Path

WHITELIST=Path(r'E:\Keys\xq-wechat-chats.json')
KEY=Path(r'E:\Keys\xiaoqian_ed25519')
STATE=Path(r'E:\AI-Memory-private\social-sync\state.json')
ROOTS={'main':Path(r'E:\AI-Memory\vault'),'private':Path(r'E:\AI-Memory-private\vault')}
ENDPOINTS={'main':'http://127.0.0.1:8767/mcp','private':'http://127.0.0.1:8768/mcp'}
ADDRESS=re.compile(r'住址|地址|住在|家住|家在|居住|住处|住宅|老家|故乡|所在地|门牌|街道|小区|楼栋|家庭住处|邮编|邮寄|\d+号楼|street|address|postcode',re.I)
SENSITIVE=re.compile(r'健康|身体|疾病|病症|医院|诊断|治疗|药物|怀孕|体重|血压|心理|财务|收入|工资|存款|资产|账户|银行卡|债务|生日|出生|年龄|身份证|电话|密码|health|medical|salary|bank|birthday',re.I)
# Main is closed by default: only these complete, low-risk hobby statements pass.
PUBLIC_HOBBY=re.compile(r'^(?:喜欢|爱好)(?:听音乐|看电影|看动漫|玩游戏|读书|阅读|运动|做饭)[。！!]*$')

def classify(text):
    if ADDRESS.search(text): return 'drop'
    if SENSITIVE.search(text): return 'private'
    return 'main' if PUBLIC_HOBBY.fullmatch(text.strip()) else 'private'

def select_targets(config):
    chats=config['chats']; owner=config['owner']
    groups=[name for name,info in chats.items() if '饭友' in name and isinstance(info,dict) and info.get('mode')=='group']
    if len(groups)!=1 or owner not in chats or chats[owner].get('mode')!='private': raise ValueError('target_selection_failed')
    return [('private',owner),('group',groups[0])]

def chat_hash(mode,name): return hashlib.sha256((mode+'\0'+name).encode('utf-8')).hexdigest()

def fetch_memory(digest):
    if not re.fullmatch(r'[a-f0-9]{64}',digest): raise ValueError('digest_invalid')
    file='C:/xiaoqian/data/wechat/memory/'+digest+'.json'
    code="import base64,pathlib; p=pathlib.Path('"+file+"'); print(base64.b64encode(p.read_bytes()).decode('ascii') if p.is_file() and p.stat().st_size<=1048576 else 'MISSING')"
    command='C:/xiaoqian/app/wechat/.venv/Scripts/python.exe -c "'+code+'"'
    run=subprocess.run(['ssh','-i',str(KEY),'-o','BatchMode=yes','-o','ConnectTimeout=15','administrator@<SERVER_IP>',command],capture_output=True,timeout=40)
    if run.returncode: raise RuntimeError('SOCIAL_SYNC_READ_FAILED')
    output=run.stdout.strip()
    if output==b'MISSING': return None
    if len(output)>1400000: raise ValueError('SOCIAL_SYNC_MEMORY_TOO_LARGE')
    value=json.loads(base64.b64decode(output,validate=True).decode('utf-8-sig'))
    if not isinstance(value,dict) or not isinstance(value.get('people'),dict) or not isinstance(value.get('jargon'),dict) or not isinstance(value.get('style'),str): raise ValueError('SOCIAL_SYNC_FORMAT_INVALID')
    return value

def extract(memory, source_digest):
    result=[]
    def add(kind,subject,text):
        if not isinstance(subject,str) or not isinstance(text,str): raise ValueError('SOCIAL_SYNC_FORMAT_INVALID')
        text=' '.join(text.split())
        if not text: return
        if len(text)>160 or len(subject)>80: raise ValueError('SOCIAL_SYNC_FORMAT_INVALID')
        marker=hashlib.sha256(json.dumps([source_digest,kind,subject,text],ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()
        result.append({'id':marker,'kind':kind,'subject':subject,'text':text,'route':classify(subject+' '+text) if ADDRESS.search(subject) or SENSITIVE.search(subject) else classify(text)})
    for subject,person in memory['people'].items():
        if not isinstance(person,dict) or not isinstance(person.get('facts',[]),list): raise ValueError('SOCIAL_SYNC_FORMAT_INVALID')
        for fact in person.get('facts',[]): add('fact',subject,fact)
        add('impression',subject,person.get('impression',''))
    for term,item in memory['jargon'].items():
        if not isinstance(item,dict): raise ValueError('SOCIAL_SYNC_FORMAT_INVALID')
        add('jargon',term,item.get('meaning',''))
    add('style','',memory['style'])
    return result

def read_state(path):
    if not path.exists(): return None
    value=json.loads(path.read_text(encoding='utf-8'))
    if value.get('version')!=1 or not isinstance(value.get('seen'),list) or any(not isinstance(x,str) or not re.fullmatch(r'[a-f0-9]{64}',x) for x in value['seen']): raise ValueError('SOCIAL_SYNC_STATE_INVALID')
    return set(value['seen'])

def directory(project):
    return '40-小千社交' if (ROOTS[project]/'40-小千社交').is_dir() else '90-收件箱'

def render(item):
    subject=item['subject'];text=item['text']
    sentence=(subject+'：' if subject else '')+text
    if len(sentence)>80 or any(c in sentence for c in '\r\n'): raise ValueError('SOCIAL_SYNC_NOTE_INVALID')
    return sentence, '## Observations\n\n- [事实] '+sentence+'\n'

async def apply_notes(items, seen, state):
    logging.disable(logging.CRITICAL)
    from contextlib import AsyncExitStack
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    async with AsyncExitStack() as stack:
        sessions={}
        for project in sorted({i['route'] for i in items if i['route']!='drop'}):
            streams=await stack.enter_async_context(streamable_http_client(ENDPOINTS[project]))
            session=await stack.enter_async_context(ClientSession(streams[0],streams[1]))
            await session.initialize();sessions[project]=session
        for item in items:
            if item['route']=='drop': seen.add(item['id']);continue
            project=item['route'];session=sessions[project];title,body=render(item)
            # Query only the destination project. Any non-exact possible match is
            # left for review; never create a duplicate or guess an edit target.
            query=' '.join(re.findall(r'[\w\u4e00-\u9fff]+',title))[:100]
            if not query: continue
            found=await session.call_tool('search_notes',{'project':project,'query':query,'page_size':5,'output_format':'json'})
            if found.isError or not isinstance(found.structuredContent,dict): raise RuntimeError('SOCIAL_SYNC_SEARCH_FAILED')
            data=found.structuredContent.get('result',{})
            rows=data.get('results')
            if not isinstance(rows,list) or data.get('has_more'): raise RuntimeError('SOCIAL_SYNC_SEARCH_AMBIGUOUS')
            if rows:
                exact=[row for row in rows if isinstance(row,dict) and row.get('title')==title and row.get('permalink')]
                if len(rows)!=1 or len(exact)!=1: continue
                current=await session.call_tool('read_note',{'project':project,'identifier':exact[0]['permalink'],'output_format':'json'})
                if current.isError or not isinstance(current.structuredContent,dict): raise RuntimeError('SOCIAL_SYNC_READ_NOTE_FAILED')
                note=current.structuredContent.get('result',{})
                front=note.get('frontmatter',{})
                content=note.get('content');checksum=note.get('checksum')
                if not isinstance(front,dict) or front.get('visibility')!='private' or not isinstance(content,str) or not isinstance(checksum,str): continue
                if title in content:
                    seen.add(item['id']);persist_state(state,seen);continue
                addition='\n- [事实] '+title+'\n'
                if len(content)+len(addition)>300: continue
                edited=await session.call_tool('edit_note',{'project':project,'identifier':exact[0]['permalink'],
                    'operation':'append','content':addition,'expected_checksum':checksum,'output_format':'json'})
                if edited.isError: raise RuntimeError('SOCIAL_SYNC_EDIT_FAILED')
                seen.add(item['id']);persist_state(state,seen)
                continue
            note=await session.call_tool('write_note',{'project':project,'title':title,'directory':directory(project),
                'content':body,'tags':['小千社交'],'metadata':{'visibility':'private'},'overwrite':False,'output_format':'json'})
            if note.isError: raise RuntimeError('SOCIAL_SYNC_WRITE_FAILED')
            seen.add(item['id'])
            persist_state(state,seen)
    persist_state(state,seen)

def persist_state(path,seen):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps({'version':1,'seen':sorted(seen)},ensure_ascii=True),encoding='utf-8')
    os.replace(tmp,path)

def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group();g.add_argument('--initialize',action='store_true');g.add_argument('--apply',action='store_true');args=p.parse_args()
    targets=select_targets(json.loads(WHITELIST.read_text(encoding='utf-8-sig')))
    items=[];missing=0
    for mode,name in targets:
        digest=chat_hash(mode,name);memory=fetch_memory(digest)
        if memory is None: missing+=1
        else: items.extend(extract(memory,digest))
    # Never establish or advance a baseline from an incomplete snapshot.
    if missing:
        if args.initialize or args.apply: raise RuntimeError('SOCIAL_SYNC_MEMORY_MISSING')
        print(json.dumps({'event':'SOCIAL_SYNC_MEMORY_MISSING','missing_count':missing,'main_count':0,'private_count':0,'dropped_count':0,
            'main_directory':directory('main'),'private_directory':directory('private')},ensure_ascii=True));return
    seen=read_state(STATE)
    if args.initialize:
        if seen is not None: raise ValueError('SOCIAL_SYNC_ALREADY_INITIALIZED')
        persist_state(STATE,{x['id'] for x in items});print('SOCIAL_SYNC_BASELINE_CREATED');return
    if seen is None:
        print(json.dumps({'event':'SOCIAL_SYNC_BASELINE_REQUIRED','main_count':0,'private_count':0,'dropped_count':0,'main_directory':directory('main'),'private_directory':directory('private')},ensure_ascii=True));return
    pending=[x for x in items if x['id'] not in seen]
    counts=Counter(x['route'] for x in pending)
    if args.apply:
        asyncio.run(apply_notes(pending,seen,STATE))
    print(json.dumps({'event':'SOCIAL_SYNC_COMPLETE' if args.apply else 'SOCIAL_SYNC_DRY_RUN',
        'main_count':counts['main'],'private_count':counts['private'],'dropped_count':counts['drop'],
        'main_directory':directory('main'),'private_directory':directory('private')},ensure_ascii=True))

if __name__=='__main__':
    try: main()
    except Exception:
        print('SOCIAL_SYNC_FAILED',file=sys.stderr);sys.exit(1)
