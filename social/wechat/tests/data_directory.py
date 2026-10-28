"""Exercise the patched app's default writers in a fresh isolated process."""
import argparse, json, os, subprocess, sys
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--source',type=Path,required=True); p.add_argument('--work',type=Path,required=True); args=p.parse_args()
work=args.work.resolve(); work.mkdir(parents=True,exist_ok=False)
data=work/'external-data'
code='''from settings import DATA, Settings\nfrom personas import PersonaStore\nfrom stickers import StickerLibrary\nfrom pathlib import Path\nSettings()\nPersonaStore()\nStickerLibrary()\nassert DATA == Path(__import__("os").environ["XQ_WECHAT_DATA_DIR"]).resolve()\nassert (DATA / "settings.json").is_file()\nassert (DATA / "personas" / "小千.json").is_file()\nassert (DATA / "stickers").is_dir()\n'''
env=dict(os.environ,XQ_WECHAT_DATA_DIR=str(data),PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',PYTHONPATH=str(args.source.resolve()))
r=subprocess.run([sys.executable,'-B','-X','utf8','-c',code],cwd=work,env=env,capture_output=True,text=True,encoding='utf-8')
(work/'result.json').write_text(json.dumps({'exit':r.returncode,'stdout':r.stdout,'stderr':r.stderr},ensure_ascii=False,indent=2),encoding='utf-8')
if r.returncode: print('data_directory_test_failed'); sys.exit(1)
print('data_directory_test_passed')
