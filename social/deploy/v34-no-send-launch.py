"""Run the audited no-send entry without a modal completion dialog."""
import os
import runpy
os.environ['XQ_AUDIT_NO_POPUP']='1'
runpy.run_path(r'C:\xiaoqian\setup\v33-wechat-no-send.py',run_name='__main__')
