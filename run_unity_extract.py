import json,csv,re,traceback
from pathlib import Path
import UnityPy
root=Path(r"F:\ZeroOne"); indir=root/'analysis-assets'; outdir=root/'unity-export'; outdir.mkdir(exist_ok=True)
rx=re.compile(r'(?i)sea|turtle|beast|trap|goddess|statue|resource|garrison|150|altar|temple|shrine|mine|wood|food|guild|alliance')
fail=[]; bundles=[]; matches=[]
def safe(x):
 if x is None or isinstance(x,(str,int,float,bool)): return x
 if isinstance(x,dict): return {str(k):safe(v) for k,v in x.items()}
 if isinstance(x,(list,tuple)): return [safe(v) for v in x]
 if hasattr(x,'__dict__'): return safe(vars(x))
 return str(x)
def name_of(d):
 if isinstance(d,dict):
  for k in ('m_Name','name','Name'):
   if k in d:return d[k]
 return None
def typ(o):
 try:return o.type.name
 except:return str(o.type)
def ptrread(p):
 try:return p.read() if p and getattr(p,'path_id',0) else None
 except:return None
for bf in sorted(indir.glob('*.ab')):
 b=bf.stem; od=outdir/b; od.mkdir(exist_ok=True); recs=[]; transforms=[]; textn=monon=0
 try:
  env=UnityPy.load(str(bf)); objs=list(env.objects)
  for o in objs:
   t=typ(o); pid=int(getattr(o,'path_id',0)); d={}; data=None
   try:data=o.read(); d=safe(data)
   except Exception as e: fail.append({'bundle':bf.name,'path_id':pid,'type':t,'stage':'read','error':str(e)})
   rec={'path_id':pid,'type':t,'name':name_of(d),'path':None}
   if t=='TextAsset' and data is not None:
    try:
     txt=getattr(data,'m_Script',''); txt=txt.decode('utf-8','replace') if isinstance(txt,bytes) else str(txt)
     fn=od/f'textasset_{pid}.txt'; fn.write_text(txt,encoding='utf-8'); rec['text_export']=str(fn); textn+=1
    except Exception as e: fail.append({'bundle':bf.name,'path_id':pid,'type':t,'stage':'text_export','error':str(e)})
   if t=='MonoBehaviour':
    try:
     tree=safe(o.read_typetree()); fn=od/f'monobehaviour_{pid}.json'; fn.write_text(json.dumps(tree,ensure_ascii=False,indent=2),encoding='utf-8'); rec['typetree_export']=str(fn); d=tree; rec['name']=name_of(d); monon+=1
    except Exception as e: fail.append({'bundle':bf.name,'path_id':pid,'type':t,'stage':'typetree','error':str(e)})
   if t=='Transform' and data is not None:
    try:
     go=ptrread(getattr(data,'m_GameObject',None)); gd=go.read() if go else None; nm=getattr(gd,'m_Name',None) if gd else None
     par=getattr(data,'m_Father',None); pp=ptrread(par); parent=int(getattr(pp,'path_id',0)) if pp else None
     pos=safe(getattr(data,'m_LocalPosition',None)); transforms.append({'path_id':pid,'gameobject_path_id':int(getattr(getattr(data,'m_GameObject',None),'path_id',0)),'name':nm,'parent_transform_path_id':parent,'local_position':pos})
     rec['name']=nm
    except Exception as e: fail.append({'bundle':bf.name,'path_id':pid,'type':t,'stage':'transform','error':str(e)})
   rec['match']=bool(rx.search(json.dumps(d,ensure_ascii=False,default=str)) or rx.search(json.dumps(rec,ensure_ascii=False)))
   if rec['match']: matches.append({'bundle':bf.name,'kind':'Object','data':rec})
   recs.append(rec)
  byid={x['path_id']:x for x in transforms}
  for x in transforms:
   chain=[]; cur=x; seen=set()
   while cur and cur['path_id'] not in seen:
    seen.add(cur['path_id']); chain.append(cur.get('name') or '?'); cur=byid.get(cur.get('parent_transform_path_id'))
   x['hierarchy']='/'.join(reversed(chain)); x['match']=bool(rx.search(str(x)))
   if x['match']:matches.append({'bundle':bf.name,'kind':'Transform','data':x})
  (od/'objects.jsonl').write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in recs)+'\n',encoding='utf-8')
  (od/'transforms.json').write_text(json.dumps(transforms,ensure_ascii=False,indent=2),encoding='utf-8')
  with (od/'transforms.csv').open('w',newline='',encoding='utf-8') as f:
   cols=['path_id','gameobject_path_id','name','hierarchy','parent_transform_path_id','local_position','match']; w=csv.DictWriter(f,fieldnames=cols); w.writeheader()
   for x in transforms:w.writerow({k:json.dumps(x.get(k),ensure_ascii=False) if isinstance(x.get(k),(dict,list)) else x.get(k) for k in cols})
  bundles.append({'bundle':bf.name,'output':str(od),'object_count':len(recs),'types':{t:sum(r['type']==t for r in recs) for t in sorted(set(r['type'] for r in recs))},'textassets_exported':textn,'monobehaviours_exported':monon,'transforms':len(transforms)})
 except Exception as e: fail.append({'bundle':bf.name,'stage':'bundle_load','error':str(e),'traceback':traceback.format_exc()})
report={'parser':'UnityPy','input':str(indir),'output':str(outdir),'bundles':bundles,'failures':fail,'strong_matches':matches}
(outdir/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'bundle_count':len(bundles),'bundles':bundles,'failure_count':len(fail),'strong_match_count':len(matches),'report':str(outdir/'report.json')},ensure_ascii=False,indent=2))
