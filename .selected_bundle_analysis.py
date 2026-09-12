from pathlib import Path
import zipfile, json, re, shutil, traceback
import UnityPy
ROOT=Path(r'F:\ZeroOne'); AS=ROOT/'analysis-assets'; APK=ROOT/'xapk-extracted'/'UnityDataAssetPack.apk'; OUT=AS/'selected-bundle-analysis'; OUT.mkdir(parents=True,exist_ok=True)
targets=['x3.ui_prefab_wondergoddess_main.ab','x3.unit_worldmap_guildbuilding_trap__main.ab','x3.unit_worldmap_gathering_prefab__main.ab','x3.ui_prefab_servermap_main.ab']
inv=AS/'relevant-entry-inventory.txt'
pat=re.compile(r'(coord|position|location|latitude|longitude|entity|unit|id$|map|server|load|world|wonder|goddess|trap|gather|resource|garrison|guild|building|spawn)',re.I)
def typename(o): return getattr(getattr(o,'type',None),'name',str(getattr(o,'type',None)))
def plain(x,depth=0):
    if depth>8:return '<depth>'
    if x is None or isinstance(x,(str,int,float,bool)): return x
    if isinstance(x,(bytes,bytearray)): return '<bytes:%d>'%len(x)
    if isinstance(x,(list,tuple)): return [plain(v,depth+1) for v in x[:100]]
    if isinstance(x,dict): return {str(k):plain(v,depth+1) for k,v in list(x.items())[:200]}
    if hasattr(x,'__dict__'): return {k:plain(v,depth+1) for k,v in vars(x).items() if not k.startswith('_')}
    return str(x)
def walk_relevant(x,key='',out=None,path=''):
    if out is None: out=[]
    if isinstance(x,dict):
        for k,v in x.items():
            p=(path+'.' if path else '')+str(k)
            sv=str(v) if isinstance(v,(str,int,float,bool)) else ''
            if pat.search(str(k)) or (sv and pat.search(sv)): out.append((p,sv if sv else plain(v)))
            walk_relevant(v,str(k),out,p)
    elif isinstance(x,(list,tuple)):
        for i,v in enumerate(x): walk_relevant(v,key,out,f'{path}[{i}]')
    return out

def read_data(o):
    try:return o.read()
    except Exception:return None

def script_name(o,env):
    d=read_data(o)
    if d is None:return None
    p=getattr(d,'m_Script',None)
    if p is None:return None
    try:
        so=p.deref() if hasattr(p,'deref') else None
        sd=so.read() if so else None
        if sd:
            return '::'.join(str(x) for x in [getattr(sd,'m_Namespace',''),getattr(sd,'m_ClassName','')] if x)
    except Exception: pass
    return str(p)

sources={}
if inv.exists():
    txt=inv.read_text(errors='replace')
    for t in targets:
        hits=[line for line in txt.splitlines() if t.lower() in line.lower()]
        sources[t]={'inventory_hits':hits[:5]}
with zipfile.ZipFile(APK) as z:
    names=z.namelist()
    for t in targets:
        candidates=[n for n in names if Path(n).name.lower()==t.lower()]
        if not candidates: sources[t]['error']='not found in APK'; continue
        src=candidates[0]; dest=OUT/t
        if not dest.exists():
            with z.open(src) as fi, dest.open('wb') as fo: shutil.copyfileobj(fi,fo)
        sources[t]['apk_entry']=src; sources[t]['path']=str(dest.relative_to(ROOT)); sources[t]['size']=dest.stat().st_size

results=[]; errors=[]
for t in targets:
    p=OUT/t
    if not p.exists(): continue
    try: env=UnityPy.load(str(p))
    except Exception as e: errors.append(f'{t}: load {e}'); continue
    counts={}; names=[]; monos=[]; relevant=[]
    for o in env.objects:
        typ=typename(o); counts[typ]=counts.get(typ,0)+1
        d=read_data(o)
        if typ=='GameObject' and d is not None: names.append(str(getattr(d,'m_Name','')))
        if typ=='MonoBehaviour':
            rec={'path_id':getattr(o,'path_id',None),'script':script_name(o,env)}
            if d is not None:
                q=plain(d); rec['field_keys']=list(q.keys()) if isinstance(q,dict) else []
                rec['relevant']=walk_relevant(q)
                if rec['relevant']: relevant.append(rec)
            monos.append(rec)
    results.append({'bundle':t,'object_counts':counts,'gameobjects':names,'monobehaviours':monos,'relevant_mono':relevant})
out={'sources':sources,'results':results,'errors':errors}
(OUT/'report.json').write_text(json.dumps(out,indent=2,ensure_ascii=True),encoding='utf-8')
print(json.dumps({'bundles':[{ 'name':r['bundle'],'objects':sum(r['object_counts'].values()),'types':r['object_counts'],'gameobjects':len(r['gameobjects']),'monobehaviours':len(r['monobehaviours']),'relevant_mono':len(r['relevant_mono'])} for r in results],'sources':sources,'errors':errors,'report':str((OUT/'report.json').relative_to(ROOT))},indent=2))
for r in results:
 print('\n###',r['bundle']); print('GameObjects:',', '.join(r['gameobjects']) or '(none)')
 for m in r['relevant_mono']:
  print('MB',m['path_id'],m['script'],'keys=',','.join(m['field_keys']),'relevant=',m['relevant'][:12])
