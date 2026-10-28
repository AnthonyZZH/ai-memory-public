"""Production launcher: run the panel and start replying; a hard crash leaves its stack in crash.log."""
import faulthandler, os, runpy, sys, time
os.environ['XQ_WECHAT_DATA_DIR'] = r'C:\xiaoqian\data\wechat'
os.chdir(r'C:\xiaoqian\app\wechat')
sys.path.insert(0, r'C:\xiaoqian\app\wechat')
log = open(r'C:\xiaoqian\data\wechat\logs\crash.log', 'a')
log.write('\n=== start %s ===\n' % time.strftime('%Y-%m-%d %H:%M:%S')); log.flush()
faulthandler.enable(file=log, all_threads=True)
sys.argv = ['app.py', '--start']
runpy.run_path(r'C:\xiaoqian\app\wechat\app.py', run_name='__main__')
