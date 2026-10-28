"""One interactive, read-only WeChat runner turn. Never writes chat text."""
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

APP = Path(r'C:\xiaoqian\app\wechat')
DATA = Path(r'C:\xiaoqian\data\wechat')
AUDIT = DATA / 'v33-audit'
os.environ['XQ_WECHAT_DATA_DIR'] = str(DATA)
sys.path.insert(0, str(APP))
result = {'status': 'started', 'sent': False, 'send_attempts': []}

def main():
    from settings import DEFAULTS, merged
    from personas import PersonaStore
    from social_brain import Brain
    from wechat_adapter import WeChatAdapter
    from app import Bot

    # Defense in depth: the actual UI adapter cannot perform either send operation.
    def blocked(*args, **kwargs):
        raise RuntimeError('NO_SEND_ENFORCED')
    WeChatAdapter.send = blocked
    WeChatAdapter.send_image = blocked

    class Config(dict):
        def chat_mode(self, chat):
            return self.get('chats', {}).get(chat, {}).get('mode')

    config = Config(merged(DEFAULTS, json.loads((DATA/'settings.json').read_text(encoding='utf-8'))))
    config.update(batch_seconds=0, memory_enabled=True, proactive=False, stickers_enabled=False, web_search=False,
                  social_state_dir=str(AUDIT/'context'))
    ui = WeChatAdapter('')
    title, private = ui.current()
    if not title or not private or config.chat_mode(title) != 'private':
        result['status'] = 'open_whitelisted_private_chat'
        return
    ui.set_target(title, 'private')
    rows = ui.read()
    if not rows or rows[-1].role != 'user' or getattr(rows[-1], 'voice', None) is not None or getattr(rows[-1], 'image', None) is not None:
        result['status'] = 'last_visible_message_must_be_incoming_text'
        return
    result['read_whitelisted_chat'] = True

    class ReadOnlyAdapter:
        system_marks = []
        def read(self):
            return ui.read()
        def send(self, text, **kwargs):
            raw = text.encode('utf-8')
            result['send_attempts'].append({'length': len(text), 'sha256': hashlib.sha256(raw).hexdigest()})
            raise RuntimeError('NO_SEND_ENFORCED')
        def send_image(self, *args, **kwargs):
            raise RuntimeError('NO_SEND_ENFORCED')

    class TrackedBrain:
        def __init__(self):
            self.inner = Brain(config, PersonaStore(), log_path=None)
            original_post = self.inner.post
            def checked_post(payload):
                result['thinking_disabled'] = payload.get('thinking') == {'type': 'disabled'}
                return original_post(payload)
            self.inner.post = checked_post
        def decide(self, *args, **kwargs):
            result['model_called'] = True
            result['group_digest_nonempty'] = bool(kwargs.get('group_digest'))
            result['memory_retrieved'] = bool(kwargs.get('memory'))
            try:
                value = self.inner.decide(*args, **kwargs)
            except Exception:
                result['model_error'] = True
                raise
            result['model_returned'] = True
            result['model_speak'] = bool(value.get('speak'))
            return value

    class Enabled:
        epoch = 1
        active = True
        def is_set(self): return self.active
        def clear(self): self.active = False

    enabled = Enabled()
    bot=Bot.__new__(Bot)
    bot.settings=config;bot.adapter=ReadOnlyAdapter();bot.enabled=enabled;bot.stop=threading.Event()
    bot.emit=lambda *_: None;bot.brain=TrackedBrain();bot.data=DATA;bot.stickers=None;bot.runners={}
    bot.higher_priority=lambda _:False
    bot.initiative=type('InitiativeNoop',(),{'heard':lambda *args:None,'spoke':lambda *args:None,'declined':lambda *args:None})()
    runner=bot.runner_for(title,reply_latest=True)
    runner.history=[]
    runner.history_path=AUDIT/'history'/'current.json'
    runner.save = lambda: None
    runner.step()
    runner.step()
    result['status'] = ('send_blocked' if result['send_attempts'] else
                        'model_failed' if result.get('model_error') else
                        'model_declined_or_runner_skipped')

if __name__ == '__main__':
    try:
        main()
    except Exception:
        result['status'] = 'test_failed'
    try:
        AUDIT.mkdir(parents=True, exist_ok=True)
        path = AUDIT / ('no-send-' + str(time.time_ns()) + '.json')
        path.write_text(json.dumps(result, ensure_ascii=True), encoding='utf-8')
        if os.environ.get('XQ_AUDIT_NO_POPUP') != '1':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, 'WeChat no-send test: ' + result['status'], 'Xiaoqian V3.3', 0)
    except Exception:
        pass
