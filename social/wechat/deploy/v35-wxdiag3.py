"""Occlusion self-heal check: cover WeChat with an Explorer window, then run the
no-send turn with no manual minimizing. Never sends; records window state only."""
import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path

out = Path(r'C:\xiaoqian\data\wechat\v33-audit\diag.json')
diag = {}
user32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    sys.path.insert(0, r'C:\xiaoqian\app\wechat')
    sys.path.insert(0, r'C:\xiaoqian\app\wechat\vendor')
    import uiautomation as auto
    hwnd = auto.WindowControl(searchDepth=1, ClassName='mmui::MainWindow').NativeWindowHandle
    import social_brain
    original = social_brain.Brain.decide
    def traced(self, *a, **k):
        try:
            return original(self, *a, **k)
        except Exception as exc:
            diag['brain_error'] = True
            raise
    social_brain.Brain.decide = traced
    import ctypes.wintypes as wt
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    user32.SetWindowPos(hwnd, wt.HWND(-2), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # HWND_NOTOPMOST
    subprocess.Popen(['explorer.exe', r'C:\xiaoqian\setup'])
    time.sleep(3)
    shell = auto.WindowControl(searchDepth=1, ClassName='CabinetWClass')
    if shell.Exists(1):
        user32.ShowWindow(shell.NativeWindowHandle, 9)
        user32.MoveWindow(shell.NativeWindowHandle, rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top, True)
        user32.SetForegroundWindow(shell.NativeWindowHandle)
        time.sleep(1)
    cx, cy = (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
    top = user32.GetAncestor(user32.WindowFromPoint(wt.POINT(cx, cy)), 2)
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(top, buf, 256)
    diag['covered_before'] = top != hwnd
    sys.path.insert(0, r'C:\xiaoqian\setup')
    import importlib.util
    spec = importlib.util.spec_from_file_location('nosend', r'C:\xiaoqian\setup\v35-no-send.py')
    nosend = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nosend)
    from wechat_adapter import WeChatAdapter
    owner = json.loads(open(r'C:\xiaoqian\data\wechat\settings.json', encoding='utf-8').read())['owner']
    try:
        WeChatAdapter('').open_chat(owner)
        diag['opened_owner'] = True
    except Exception as exc:
        diag['open_error'] = True
    try:
        nosend.main()
    except Exception as exc:
        nosend.result['status'] = 'test_failed'
        diag['error'] = True
    result=nosend.result
    diag['send_blocked'] = result.get('status') == 'send_blocked'
    diag['read_whitelisted_chat'] = bool(result.get('read_whitelisted_chat'))
    diag['thinking_disabled'] = bool(result.get('thinking_disabled'))
    diag['group_digest_nonempty'] = bool(result.get('group_digest_nonempty'))
    diag['memory_retrieved'] = bool(result.get('memory_retrieved'))
    top = user32.GetAncestor(user32.WindowFromPoint(wt.POINT(cx, cy)), 2)
    diag['wechat_front_after'] = top == hwnd
    diag['wechat_topmost'] = bool(user32.GetWindowLongW(hwnd, -20) & 0x8)
except Exception as exc:
    diag['diag_error'] = True
out.write_text(json.dumps(diag, ensure_ascii=False), encoding='utf-8')
