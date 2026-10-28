"""Exercise the actual runner with a fake UI and deterministic brain; no network."""
import argparse, importlib.util, json, sys, tempfile, types
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--source', required=True, type=Path)
p.add_argument('--entry', required=True, type=Path)
p.add_argument('--work', required=True, type=Path)
a = p.parse_args()
a.work.mkdir(parents=True, exist_ok=False)
sys.path.insert(0, str(a.source.resolve()))
import personas, social_brain
calls = []
class Row:
    role = 'user'; text = 'synthetic incoming'; key = '1'; sender = ''
    image = None; voice = None; odd = False
class FakeUI:
    def __init__(self, *args): pass
    def current(self): return 'test friend', True
    def set_target(self, *args): pass
    def read(self): return [Row()]
    def send(self, *args, **kwargs): calls.append('real send')
    def send_image(self, *args, **kwargs): calls.append('real image send')
class FakeBrain:
    def __init__(self, *args, **kwargs): pass
    def post(self, payload): return {}
    def decide(self, *args, **kwargs):
        self.post({'thinking': {'type': 'disabled'}})
        return {'speak': True, 'text': 'synthetic reply', 'sticker': ''}
personas.PersonaStore = lambda: None
social_brain.Brain = FakeBrain
sys.modules['wechat_adapter'] = types.SimpleNamespace(WeChatAdapter=FakeUI)
spec = importlib.util.spec_from_file_location('no_send_entry', a.entry)
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
entry.DATA = a.work
entry.AUDIT = a.work/'audit'
(a.work/'settings.json').write_text(json.dumps({'chats': {'test friend': {'mode': 'private'}}, 'memory_enabled': False}), encoding='utf-8')
entry.main()
assert entry.result['status'] == 'send_blocked', entry.result
assert entry.result['model_returned'] and len(entry.result['send_attempts']) == 1
assert entry.result['thinking_disabled'] is True
assert entry.result['send_attempts'][0]['length'] == len('synthetic reply')
assert not calls
assert 'synthetic reply' not in json.dumps(entry.result)
assert not list(a.work.rglob('*history*.json'))
print('actual_runner_fake_ui_send_blocked')
