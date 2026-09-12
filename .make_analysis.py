from pathlib import Path
import re,zipfile,hashlib,math,gzip,zlib
R=Path(r'F:\ZeroOne'); apk=R/'xapk-extracted/UnityDataAssetPack.apk'; ab=R/'analysis-assets/x3.mapcommon.ab'; od=R/'unity-export/x3.mapcommon'; od.mkdir(exist_ok=True,parents=True)
def esc(x): return str(x).encode('ascii','backslashreplace').decode('ascii')
pat=re.compile(r'config|table|data|kingofsea|expd|worldmap|mapcommon|server|resource|gather|statue|goddess|temple|turtle|beast|trap|fort|garrison',re.I)
with zipfile.ZipFile(apk) as z:
 rows=[(i.filename,i.file_size) for i in z.infolist() if pat.search(i.filename)]
(R/'analysis-assets/relevant-entry-inventory.txt').write_text(''.join(f'{s}\t{esc(n)}\n' for n,s in rows),encoding='ascii')
import UnityPy
e=UnityPy.load(str(ab)); objs=list(e.objects); by={int(o.path_id):o for o in objs}
def typ(o): return esc(getattr(getattr(o,'type',None),'name',str(getattr(o,'type',''))))
cm=[]
for k,v in e.container.items():
 xs=v if isinstance(v,(list,tuple,set)) else [v]
 for x in xs:
  p=getattr(x,'path_id',None) or getattr(getattr(x,'object_reader',None),'path_id',None)
  cm.append((esc(k),p,typ(by[int(p)]) if p is not None and int(p) in by else esc(repr(x))))
paths={}
for k,p,t in cm:
 if p is not None: paths.setdefault(int(p),[]).append(k)
def ent(b): return 0 if not b else -sum((n:=b.count(x))/len(b)*math.log2(n/len(b)) for x in set(b))
def strs(b): return [(m.start(),m.group().decode('ascii','replace')) for m in re.finditer(rb'[ -~]{4,}',b)]
def chk(b):
 r=[]
 for x in ('utf-8','utf-16le'):
  try:r.append(x+'=ok')
  except:r.append(x+'=invalid')
 if b[:2]==b'\x1f\x8b':r+=['gzip-signature']
 if b[:2] in (b'x\x01',b'x\x9c',b'x\xda'):r+=['zlib-signature']
 for label,fn in [('gzip',gzip.decompress),('zlib',zlib.decompress)]:
  try:fn(b);r.append(label+'-decodes')
  except:pass
 try:
  import lz4.block as l;r.append('lz4-decodes='+str(len(l.decompress(b))))
 except:pass
 try:
  import msgpack;r.append('msgpack-decodes='+type(msgpack.unpackb(b,raw=False)).__name__)
 except:pass
 return ','.join(r)
ts=[]
for o in objs:
 if typ(o)!='TextAsset':continue
 d=o.read(); b=getattr(d,'m_Script',b''); b=b.encode('utf-8','surrogatepass') if isinstance(b,str) else bytes(b); p=int(o.path_id); n=esc(getattr(d,'m_Name','')) or 'unnamed'; s=re.sub(r'[^A-Za-z0-9._-]+','_',n).strip('_') or 'unnamed'; f=od/f'raw_{p}_{s}.bin'
 if f.exists():f=od/f'raw_{p}_{s}_{hashlib.sha1(b).hexdigest()[:8]}.bin'
 f.write_bytes(b);ts.append((p,n,b,f,paths.get(p,[])))
L=[f'file={ab} size={ab.stat().st_size}',f'objects={len(objs)} container_mappings={len(cm)}','ENV.CONTAINER:']+[f'{k}\tpath_id={p}\ttype={t}' for k,p,t in cm]+['',f'TextAssets={len(ts)}']
for p,n,b,f,ps in ts:
 L += [f'name={n!r} path_id={p} raw_len={len(b)} first64_hex={b[:64].hex(" ")}',f'raw_file={f} containers={" | ".join(ps) if ps else "(unresolved)"}',f'entropy={ent(b):.4f} checks={chk(b)}']
 q=strs(b);L.append('printable='+' | '.join(f'{o}:{s}' for o,s in q) if q else 'printable=(none)')
 c=re.findall(r'(?i)(?:entity|id|coord|position|pos|x|y|z)[^\r\n,:=]{0,8}[:=, ]+[-+]?\d+(?:\.\d+)?',b.decode('utf-8','ignore'))
 if c:L.append('candidates='+' | '.join(c[:40]))
from collections import defaultdict
g=defaultdict(list)
for t in ts:g[t[1]].append(t)
L+=['','Repeated names:']
for n,v in g.items():
 if len(v)>1:L.append(n+' :: '+' || '.join(f'path_id={x[0]} containers={x[4]}' for x in v))
if not any(len(v)>1 for v in g.values()):L.append('(none)')
L+=['','Conclusion: raw signature/decoder results are listed per asset; no claims of encryption are made beyond the observed entropy and decoder outcomes.']
(R/'analysis-assets/mapcommon-analysis.txt').write_text('\n'.join(L)+'\n',encoding='ascii')

