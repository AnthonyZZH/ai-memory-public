"""Offline tests: no SSH, real note reads, writes, task creation, or secrets."""
import asyncio, importlib.util, json, sys, tempfile, unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TOOL=Path(__file__).resolve().parents[1]/'deploy/pull_social_memory.py'
spec=importlib.util.spec_from_file_location('social_sync',TOOL);sync=importlib.util.module_from_spec(spec);spec.loader.exec_module(sync)

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=r'E:\Codex Development\tmp');self.addCleanup(self.temp.cleanup)
        self.state=Path(self.temp.name)/'state.json'
    def test_target_unique_and_whitelisted(self):
        config={'owner':'owner','chats':{'owner':{'mode':'private'},'饭友群':{'mode':'group'},'friend':{'mode':'private'}}}
        self.assertEqual(len(sync.select_targets(config)),2)
        config['chats']['饭友第二群']={'mode':'group'}
        with self.assertRaises(ValueError):sync.select_targets(config)
    def test_address_drop_private_fallback_main_allowlist(self):
        self.assertEqual(sync.classify('家住某小区'),'drop')
        self.assertEqual(sync.classify('身体不舒服'),'private')
        self.assertEqual(sync.classify('未知事项'),'private')
        self.assertEqual(sync.classify('喜欢听音乐'),'main')
    def test_new_only_and_no_plaintext_state(self):
        memory={'people':{'synthetic person':{'facts':['喜欢听音乐','未知内容'],'impression':''}},'jargon':{},'style':''}
        rows=sync.extract(memory,'a'*64);self.assertEqual(len(rows),2)
        sync.persist_state(self.state,{rows[0]['id']})
        self.assertNotIn('synthetic person',self.state.read_text(encoding='utf-8'))
        self.assertNotIn('喜欢听音乐',self.state.read_text(encoding='utf-8'))
        self.assertEqual(len([x for x in rows if x['id'] not in sync.read_state(self.state)]),1)
    def test_dry_run_never_calls_write_or_persists_state(self):
        config={'owner':'o','chats':{'o':{'mode':'private'},'饭友群':{'mode':'group'}}}
        source=Path(self.temp.name)/'chats.json';source.write_text(json.dumps(config,ensure_ascii=False),encoding='utf-8')
        memory={'people':{},'jargon':{},'style':''}
        with mock.patch.object(sync,'WHITELIST',source),mock.patch.object(sync,'STATE',self.state),mock.patch.object(sync,'fetch_memory',return_value=memory),mock.patch.object(sync,'apply_notes',side_effect=AssertionError()),mock.patch('sys.argv',['sync']),mock.patch('builtins.print') as out:
            sync.main()
        self.assertFalse(self.state.exists());self.assertNotIn('饭友群',str(out.call_args))
    def test_missing_snapshot_cannot_advance_state(self):
        config={'owner':'o','chats':{'o':{'mode':'private'},'饭友群':{'mode':'group'}}}
        source=Path(self.temp.name)/'chats.json';source.write_text(json.dumps(config,ensure_ascii=False),encoding='utf-8')
        with mock.patch.object(sync,'WHITELIST',source),mock.patch.object(sync,'STATE',self.state),mock.patch.object(sync,'fetch_memory',return_value=None),mock.patch('sys.argv',['sync']),mock.patch('builtins.print') as out:
            sync.main()
        self.assertFalse(self.state.exists());self.assertIn('SOCIAL_SYNC_MEMORY_MISSING',str(out.call_args))
    def test_private_routing_and_search_before_create(self):
        calls=[]
        @asynccontextmanager
        async def transport(url):
            calls.append(('endpoint',url));yield (object(),object(),object())
        class Session:
            def __init__(self,*args):pass
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def initialize(self):pass
            async def call_tool(self,name,args):
                calls.append((name,args.get('project')))
                return SimpleNamespace(isError=False,structuredContent={'result':{'results':[],'has_more':False}})
        import mcp, mcp.client.streamable_http
        item={'id':'a'*64,'route':'private','subject':'subject','text':'sensitive fact','kind':'fact'}
        with mock.patch.object(mcp,'ClientSession',Session),mock.patch.object(mcp.client.streamable_http,'streamable_http_client',transport):
            asyncio.run(sync.apply_notes([item],set(),self.state))
        self.assertEqual(calls[0],('endpoint',sync.ENDPOINTS['private']))
        self.assertEqual(calls[1:],[('search_notes','private'),('write_note','private')])
        self.assertNotIn('sensitive fact',self.state.read_text(encoding='utf-8'))
    def test_ambiguous_search_never_creates(self):
        calls=[]
        @asynccontextmanager
        async def transport(url):yield (1,2,3)
        class Session:
            def __init__(self,*args):pass
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def initialize(self):pass
            async def call_tool(self,name,args):
                calls.append(name)
                return SimpleNamespace(isError=False,structuredContent={'result':{'results':[{'title':'other','permalink':'x'}],'has_more':False}})
        import mcp,mcp.client.streamable_http
        item={'id':'b'*64,'route':'private','subject':'s','text':'t','kind':'fact'}
        with mock.patch.object(mcp,'ClientSession',Session),mock.patch.object(mcp.client.streamable_http,'streamable_http_client',transport):
            asyncio.run(sync.apply_notes([item],set(),self.state))
        self.assertEqual(calls,['search_notes'])
    def test_exact_private_match_updates_with_revision(self):
        calls=[]
        @asynccontextmanager
        async def transport(url):yield (1,2,3)
        class Session:
            def __init__(self,*args):pass
            async def __aenter__(self):return self
            async def __aexit__(self,*args):pass
            async def initialize(self):pass
            async def call_tool(self,name,args):
                calls.append((name,args))
                if name=='search_notes': data={'results':[{'title':'s：t','permalink':'private/x'}],'has_more':False}
                elif name=='read_note': data={'frontmatter':{'visibility':'private'},'content':'## Observations\n','checksum':'revision'}
                else: data={}
                return SimpleNamespace(isError=False,structuredContent={'result':data})
        import mcp,mcp.client.streamable_http
        item={'id':'c'*64,'route':'private','subject':'s','text':'t','kind':'fact'}
        with mock.patch.object(mcp,'ClientSession',Session),mock.patch.object(mcp.client.streamable_http,'streamable_http_client',transport):
            asyncio.run(sync.apply_notes([item],set(),self.state))
        self.assertEqual([name for name,_ in calls],['search_notes','read_note','edit_note'])
        self.assertEqual(calls[-1][1]['expected_checksum'],'revision')

if __name__=='__main__':unittest.main()
