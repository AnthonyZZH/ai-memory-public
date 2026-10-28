"""Offline 0005/0006 paired contracts; synthetic images and chats only."""
import argparse, base64, io, sys, threading, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
a,rest=p.parse_known_args();sys.path.insert(0,str(a.source));a.work.mkdir(parents=True,exist_ok=True)
from PIL import Image
from social_brain import Brain
from app import Bot, Enabled
from runner import Runner
from settings import Settings

class V35Tests(unittest.TestCase):
    def setUp(self):
        self.work=a.work/self._testMethodName;self.work.mkdir(parents=True,exist_ok=True)
        self.s=Settings(self.work/'settings.json')
        self.s.values.update({'owner':'owner','persona':'p','chats':{'owner':{'mode':'private'},'friend':{'mode':'private'},'group':{'mode':'group'}},'social_state_dir':str(self.work/'state'),'describe_images':True,'collect_stickers':True})
        self.p=SimpleNamespace(load=lambda _:SimpleNamespace(prompt='persona'))
    def test_image_payload_bounded_and_no_tools(self):
        b=Brain(self.s,self.p);captured=[]
        b.post=lambda payload: captured.append(payload) or {'description':'a synthetic image'}
        self.assertEqual(b.describe_image(Image.new('RGB',(2400,1600),'red')),'a synthetic image')
        payload=captured[0];self.assertNotIn('tools',payload)
        part=payload['messages'][1]['content'][1]['image_url']['url']
        self.assertLessEqual(len(part.encode()),1024*1024)
        image=Image.open(io.BytesIO(base64.b64decode(part.split(',',1)[1])))
        self.assertLessEqual(max(image.size),1024);self.assertEqual(image.format,'JPEG')
    def test_owner_group_context_only_for_owner(self):
        seen=[];b=Brain(self.s,self.p);b.request=lambda messages,**kw:seen.append(messages) or {'speak':True,'text':'ok'}
        for chat,mode in [('owner','private'),('friend','private'),('group','group')]:
            b.decide([{'role':'user','text':'hello'}],chat=chat,mode=mode,group_digest='GROUP_SENTINEL')
        self.assertIn('GROUP_SENTINEL',str(seen[0]));self.assertNotIn('GROUP_SENTINEL',str(seen[1:] ))
    def test_group_digest_only_groups_and_bounded(self):
        b=Bot.__new__(Bot);b.settings=self.s
        b.runner_for=lambda chat:SimpleNamespace(history=[{'role':'user','text':chat+'x'*1500}])
        text=b.owner_group_digest();self.assertIn('group',text);self.assertNotIn('friend',text);self.assertLessEqual(len(text),1200)
    def test_one_image_per_turn_and_whitelist(self):
        calls=[]; brain=SimpleNamespace(describe_image=lambda image:calls.append(1) or 'synthetic')
        enabled=Enabled();enabled.set()
        r=Runner(self.s,SimpleNamespace(),enabled,threading.Event(),lambda *args:None,brain,'owner',history_dir=self.work/'h',memory_dir=self.work/'m')
        r.own_sticker=lambda image:False
        def row(key): return SimpleNamespace(role='user',text='[图片]',key=key,sender='',image=Image.new('RGB',(8,8)),voice=None,odd=False)
        r.accept(row('1'));r.accept(row('2'));self.assertEqual(len(calls),1)
        self.s.values['chats'].pop('owner');r.pending.clear();r.accept(row('3'));self.assertEqual(len(calls),1)
    def test_sticker_collected_only_from_whitelist(self):
        calls=[];brain=SimpleNamespace(describe_image=lambda image:'synthetic')
        library=SimpleNamespace(inbox=SimpleNamespace(add=lambda *args:calls.append(1) or 'id'),hashes=lambda:[])
        enabled=Enabled();enabled.set();r=Runner(self.s,SimpleNamespace(),enabled,threading.Event(),lambda *args:None,brain,'owner',history_dir=self.work/'h',memory_dir=self.work/'m',stickers=library)
        r.own_sticker=lambda image:False
        r.accept(SimpleNamespace(role='user',text='[表情]',key='1',sender='',image=Image.new('RGB',(8,8)),voice=None,odd=False))
        self.assertEqual(calls,[1])
    def test_photo_is_not_collected_and_diagnostics_are_fixed_codes(self):
        events=[];calls=[];brain=SimpleNamespace(describe_image=lambda image:'SYNTHETIC_DESCRIPTION')
        library=SimpleNamespace(inbox=SimpleNamespace(add=lambda *args:calls.append(1)),hashes=lambda:[])
        enabled=Enabled();enabled.set();r=Runner(self.s,SimpleNamespace(),enabled,threading.Event(),lambda k,v:events.append((k,v)),brain,'owner',history_dir=self.work/'h',memory_dir=self.work/'m',stickers=library)
        r.own_sticker=lambda image:False
        r.accept(SimpleNamespace(role='user',text='[图片]',key='1',sender='',image=Image.new('RGB',(8,8)),voice=None,odd=False))
        self.assertEqual(calls,[])
        self.assertNotIn('SYNTHETIC_DESCRIPTION',str(events))
        self.assertIn('SYNTHETIC_DESCRIPTION',r.history[-1]['text'])
    def test_image_switch_off_prevents_upload(self):
        from settings import DEFAULTS
        self.assertTrue(DEFAULTS['describe_images'])
        calls=[];self.s.values['describe_images']=False
        enabled=Enabled();enabled.set();r=Runner(self.s,SimpleNamespace(),enabled,threading.Event(),lambda *args:None,SimpleNamespace(describe_image=lambda image:calls.append(1)),'owner',history_dir=self.work/'h',memory_dir=self.work/'m')
        r.own_sticker=lambda image:False
        r.accept(SimpleNamespace(role='user',text='[图片]',key='1',sender='',image=Image.new('RGB',(8,8)),voice=None,odd=False))
        self.assertEqual(calls,[]);self.assertIn('图片',r.history[-1]['text'])
    def test_image_recognition_switch_default_on(self):
        from settings import DEFAULTS
        self.assertTrue(DEFAULTS['describe_images']);self.assertTrue(DEFAULTS['collect_stickers'])

if __name__=='__main__':unittest.main(argv=[sys.argv[0],*rest])
