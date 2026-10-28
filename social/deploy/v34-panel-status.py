"""Read only a fixed panel label on the interactive desktop; no chat contents."""
import json
from pathlib import Path
import uiautomation as auto

out=Path(r'C:\xiaoqian\setup\v34-panel-status.json')
result={'panel_exists':False,'paused_label':False}
try:
    with auto.UIAutomationInitializerInThread():
        panel=auto.WindowControl(searchDepth=1,Name='AI 群友控制台')
        result['panel_exists']=panel.Exists(3)
        if result['panel_exists']:
            result['paused_label']=panel.TextControl(Name='已暂停', searchDepth=20).Exists(2)
except Exception:
    result['probe_error']=True
out.write_text(json.dumps(result),encoding='utf-8')
