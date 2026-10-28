"""Offline paired contracts; all extracted sources and logs are retained.

--python selects a Python that already has the pinned upstream Pillow installed.
No installation, real UI, login, real model API, SSH or upstream git write.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--python',required=True,type=Path)
    p.add_argument('--source-root',required=True,type=Path)
    p.add_argument('--work-root',required=True,type=Path)
    args=p.parse_args()
    args.work_root.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='wechat-contracts-',dir=args.work_root))
    spec=importlib.util.spec_from_file_location('wb',ROOT/'build/fetch-and-patch.py')
    wrapper=importlib.util.module_from_spec(spec); spec.loader.exec_module(wrapper)
    v=wrapper.builder
    v.materialize(work/'vendor',args.source_root)
    item=json.loads((ROOT/'vendor.lock').read_text())['projects'][0]
    data=subprocess.check_output(['git','-C',str(args.source_root/item['name']),'archive',item['commit']])
    v.extract(data,work/'original')
    result={}
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',TEMP=str(work),TMP=str(work))
    for name,source in [('before',work/'original'),('after',work/'vendor'/item['name'])]:
        run=subprocess.run([str(args.python),'-B','-X','utf8',str(ROOT/'tests/contracts.py'),'--source',str(source),'--work',str(work/name),'-v'],env=env,capture_output=True,text=True,encoding='utf-8')
        log=run.stdout+run.stderr
        (work/(name+'.log')).write_text(log,encoding='utf-8')
        cases=dict(re.findall(r'^(test_\w+) \([^\n]+\) \.\.\. (ok|FAIL|ERROR)$',log,re.M))
        result[name]={'exit':run.returncode,'cases':cases,'passed':sum(v=='ok' for v in cases.values()),'total':len(cases)}
    result['paired']=bool(result['after']['cases']) and result['before']['cases'].keys()==result['after']['cases'].keys() and all(
        result['before']['cases'].get(k) in ('FAIL','ERROR') and v=='ok' for k,v in result['after']['cases'].items())
    # Compare relay contracts against the audited 0004 baseline, not upstream.
    baseline=json.loads((ROOT/'vendor.lock').read_text(encoding='utf-8'))
    project=baseline['projects'][0]
    # Later fix-ups (0007+) sit on top of 0006; the stage baselines below start from 0006.
    while project['patches'] and not project['patches'][-1]['path'].endswith('/0006-images-group-context.patch'):
        project['patches'].pop()
    if not project['patches'] or not project['patches'][-1]['path'].endswith('/0006-images-group-context.patch'):
        raise ValueError('v35_patch_missing')
    project['patches'].pop()
    if not project['patches'][-1]['path'].endswith('/0005-owner-relay.patch'):
        raise ValueError('relay_patch_missing')
    project['patched_tree_sha256']='2823495002f045158fb7762ccb15ffcce6baddaa2855a935d67204920734c165'
    v35_baseline_path=work/'v35-baseline-lock.json'
    v35_baseline_path.write_text(json.dumps(baseline),encoding='utf-8')
    v.materialize(work/'v35-baseline',args.source_root,v35_baseline_path)
    project['patches'].pop()
    project['patched_tree_sha256']='f87c33f41fdf322bf80eb3fa89ed3ecef3f6d77367dbddbf7fa83c6332a489f5'
    baseline_path=work/'baseline-lock.json'
    baseline_path.write_text(json.dumps(baseline),encoding='utf-8')
    v.materialize(work/'relay-baseline',args.source_root,baseline_path)
    relay={}
    for name,source in [('before',work/'relay-baseline'/item['name']),('after',work/'vendor'/item['name'])]:
        run=subprocess.run([str(args.python),'-B','-X','utf8',str(ROOT/'tests/relay_contracts.py'),'--source',str(source),'--work',str(work/('relay-'+name)),'-v'],env=env,capture_output=True,text=True,encoding='utf-8')
        log=run.stdout+run.stderr
        (work/('relay-'+name+'.log')).write_text(log,encoding='utf-8')
        cases=dict(re.findall(r'^(test_\w+) \([^\n]+\) \.\.\. (ok|FAIL|ERROR)$',log,re.M))
        relay[name]={'exit':run.returncode,'cases':cases,'passed':sum(v=='ok' for v in cases.values()),'total':len(cases)}
    relay['paired']=bool(relay['after']['cases']) and relay['before']['cases'].keys()==relay['after']['cases'].keys() and all(
        relay['before']['cases'].get(k) in ('FAIL','ERROR') and v=='ok' for k,v in relay['after']['cases'].items())
    result['relay']=relay
    thinking={}
    for name,source in [('before',work/'relay-baseline'/item['name']),('after',work/'vendor'/item['name'])]:
        run=subprocess.run([str(args.python),'-B','-X','utf8',str(ROOT/'tests/thinking_contracts.py'),'--source',str(source),'--work',str(work/('thinking-'+name)),'-v'],env=env,capture_output=True,text=True,encoding='utf-8')
        log=run.stdout+run.stderr
        (work/('thinking-'+name+'.log')).write_text(log,encoding='utf-8')
        cases=dict(re.findall(r'^(test_\w+) \([^\n]+\) \.\.\. (ok|FAIL|ERROR)$',log,re.M))
        thinking[name]={'exit':run.returncode,'cases':cases,'passed':sum(v=='ok' for v in cases.values()),'total':len(cases)}
    thinking['paired']=bool(thinking['after']['cases']) and thinking['before']['cases'].keys()==thinking['after']['cases'].keys() and all(
        thinking['before']['cases'].get(k) in ('FAIL','ERROR') and v=='ok' for k,v in thinking['after']['cases'].items())
    result['thinking']=thinking
    v35={}
    for name,source in [('before',work/'v35-baseline'/item['name']),('after',work/'vendor'/item['name'])]:
        run=subprocess.run([str(args.python),'-B','-X','utf8',str(ROOT/'tests/v35_contracts.py'),'--source',str(source),'--work',str(work/('v35-'+name)),'-v'],env=env,capture_output=True,text=True,encoding='utf-8')
        log=run.stdout+run.stderr
        (work/('v35-'+name+'.log')).write_text(log,encoding='utf-8')
        cases=dict(re.findall(r'^(test_\w+) \([^\n]+\) \.\.\. (ok|FAIL|ERROR)$',log,re.M))
        v35[name]={'exit':run.returncode,'cases':cases,'passed':sum(v=='ok' for v in cases.values()),'total':len(cases)}
    v35['paired']=bool(v35['after']['cases']) and v35['before']['cases'].keys()==v35['after']['cases'].keys() and all(
        v35['before']['cases'].get(k) in ('FAIL','ERROR') and v=='ok' for k,v in v35['after']['cases'].items())
    result['v35']=v35
    (work/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'before':result['before']['passed'],'after':result['after']['passed'],'total':result['after']['total'],'paired':result['paired'],
        'relay_before':relay['before']['passed'],'relay_after':relay['after']['passed'],'relay_total':relay['after']['total'],
        'relay_paired':relay['paired'],'thinking_before':thinking['before']['passed'],'thinking_after':thinking['after']['passed'],
        'thinking_paired':thinking['paired'],'v35_before':v35['before']['passed'],'v35_after':v35['after']['passed'],
        'v35_total':v35['after']['total'],'v35_paired':v35['paired'],'artifacts':str(work)}))
    return 0 if result['paired'] and result['after']['exit']==0 and relay['paired'] and relay['after']['exit']==0 and thinking['paired'] and thinking['after']['exit']==0 and v35['paired'] and v35['after']['exit']==0 else 1


if __name__=='__main__': raise SystemExit(main())
