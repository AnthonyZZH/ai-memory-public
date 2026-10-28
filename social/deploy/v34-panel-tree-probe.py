import json
from pathlib import Path
import uiautomation as auto
out=Path(r'C:\xiaoqian\setup\v34-panel-tree-probe.json')
result={'window':False,'controls':0,'paused_exact':0,'paused_contains':0,'start_button':0,'types':{}}
try:
    with auto.UIAutomationInitializerInThread():
        panel=auto.WindowControl(searchDepth=1,Name='AI 群友控制台')
        result['window']=panel.Exists(2)
        if result['window']:
            rect=panel.BoundingRectangle
            result['bounds']=[rect.left,rect.top,rect.right,rect.bottom]
            todo=[panel]
            while todo and result['controls']<1000:
                c=todo.pop();result['controls']+=1
                name=c.Name or ''
                result['paused_exact']+=name=='已暂停'
                result['paused_contains']+='已暂停' in name
                result['start_button']+=name=='开始 / 继续'
                typ=c.ControlTypeName
                result['types'][typ]=result['types'].get(typ,0)+1
                todo.extend(c.GetChildren())
except Exception:
    result['probe_error']=True
out.write_text(json.dumps(result,ensure_ascii=True),encoding='utf-8')
