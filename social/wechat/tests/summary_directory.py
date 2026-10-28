"""Write a synthetic summary and check that it follows the isolated DATA root."""
import argparse, os, subprocess, sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--source', required=True, type=Path)
p.add_argument('--work', required=True, type=Path)
a = p.parse_args()
a.work.mkdir(parents=True, exist_ok=False)
code = '''from pathlib import Path
from settings import DATA
from social_brain import Brain
b = Brain({}, None)
b.request = lambda *a, **kw: {"summary": "synthetic"}
rows = [{"role": "user", "text": "x" * 200} for _ in range(25)]
b.window(rows, "synthetic", "private")
assert b.state_dir == DATA / "social-context"
assert len(list((DATA / "social-context").glob("*.json"))) == 1
assert Brain({"social_state_dir": str(DATA / "custom")}, None).state_dir == DATA / "custom"
'''
env = dict(os.environ, XQ_WECHAT_DATA_DIR=str((a.work/'data').resolve()),
           PYTHONPATH=str(a.source.resolve()), PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
r = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-c', code], cwd=a.work,
                   env=env, capture_output=True, text=True, encoding='utf-8')
(a.work/'result.txt').write_text('exit='+str(r.returncode)+'\n'+r.stderr, encoding='utf-8')
print('summary_directory_passed' if r.returncode == 0 else 'summary_directory_failed')
sys.exit(r.returncode)
