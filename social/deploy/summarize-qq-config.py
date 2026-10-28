import sys, yaml
class L(yaml.SafeLoader): pass
def unknown(loader,suffix,node): return '<expression>'
L.add_multi_constructor('',unknown)
try:
    doc=yaml.load(sys.stdin.read(),Loader=L)
    if not isinstance(doc,list): raise ValueError()
    for row in doc:
        if not isinstance(row,dict): continue
        ident=str(row.get('id','')); plugin=str(row.get('name',''))
        if ident.startswith('tool-') and ident not in ('tool-executor-native','tool-executor-ptc'):
            flag=row.get('disabled',False)
            state='disabled' if flag is True else 'conditional' if flag=='<expression>' else 'enabled-row'
            print('| %s | %s | %s |' % (ident,plugin,state))
    preset=next((x for x in doc if isinstance(x,dict) and x.get('id')=='preset-xiaoqian-social'),None)
    if not preset or preset.get('disabled') is True: raise ValueError()
    nested=preset.get('config',{}).get('plugins',[])
    if [x.get('id') for x in nested] != ['persona','time-context','compaction']: raise ValueError()
    print('PRESET_STATIC_ONLY=persona,time-context,compaction')
except Exception:
    print('dump_parse_failed',file=sys.stderr);sys.exit(1)
