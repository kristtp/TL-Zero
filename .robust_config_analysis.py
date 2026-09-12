from pathlib import Path
import re, json, traceback, struct
import UnityPy

ROOT=Path(r'F:\ZeroOne')
AS=ROOT/'analysis-assets'
OUT=AS/'config-relevant-raw'
AS.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
BUNDLES=['x3.config.ab','x3.config_asset.ab','x3.config_dk.ab']
NAME_RE=re.compile(r'(sea|turtle|beast|monster|trap|goddess|statue|wonder|garrison|resource|gather|world|map|territory|guild|union|king|spawn|unit|building|server)',re.I)
SEARCH_RE=re.compile(r'(sea|turtle|beast|monster|trap|goddess|statue|wonder|garrison|resource|gather|world|map|territory|guild|union|king|spawn|unit|building|server)',re.I)

def esc(b):
    return ''.join(chr(x) if 32<=x<127 and x not in (92,) else ('\\\\' if x==92 else '\\x%02x'%x) for x in b)
def strings_at(raw):
    out=[]
    for m in re.finditer(rb'[\x20-\x7e]{4,}',raw): out.append((m.start(),m.group().decode('ascii','replace')))
    for m in re.finditer(rb'(?:[\x20-\x7e]\x00){4,}',raw):
        b=m.group()[::2]; out.append((m.start(),b.decode('ascii','replace')))
    return out

def varint(b,p):
    v=0; shift=0; q=p
    while q<len(b) and shift<70:
        x=b[q]; q+=1; v|=(x&127)<<shift
        if x<128:return v,q
        shift+=7
    return None,p

def wire(raw,limit=20000):
    out=[]; p=0; n=len(raw)
    while p<n and len(out)<limit:
        off=p; key,q=varint(raw,p)
        if key is None or key==0: break
        field=key>>3; wt=key&7
        if field<=0 or field>10000: break
        p=q; val=None; end=p
        try:
            if wt==0: val,end=varint(raw,p)
            elif wt==1: end=p+8; val=raw[p:end] if end<=n else None
            elif wt==2:
                ln,end0=varint(raw,p); end=end0+ln if ln is not None else n
                val=raw[end0:end] if ln is not None and end<=n else None
            elif wt==5: end=p+4; val=raw[p:end] if end<=n else None
            else: break
        except Exception: break
        if val is None or end>n: break
        item={'offset':off,'field':field,'wire':wt}
        if wt==0: item['value']=val
        elif wt in (1,5):
            item['hex']=val.hex(); item['numeric']=struct.unpack('<d',val)[0] if wt==1 else struct.unpack('<f',val)[0]
        else:
            item['length']=len(val); item['hex']=val.hex()[:256]
            ss=strings_at(val)
            if ss: item['strings']=[{'offset':end-len(val)+a,'value':s} for a,s in ss[:20]]
            if val: item['escaped']=esc(val[:128])
        out.append(item); p=end
    return out

inventory=[]; relevant=[]; errors=[]; totals={'bundles':0,'objects':0,'textassets':0,'relevant':0,'bytes':0,'wire_records':0,'string_hits':0}
for bn in BUNDLES:
    bp=AS/bn; totals['bundles']+=1
    try: env=UnityPy.load(str(bp))
    except Exception as e: errors.append(f'{bn}: load: {e}'); continue
    totals['objects']+=len(env.objects)
    byid={getattr(o,'path_id',None):o for o in env.objects}
    paths={}
    try:
        for path,entry in env.container.items():
            try:
                obj=entry.resolve() if hasattr(entry,'resolve') else entry
                paths.setdefault(getattr(obj,'path_id',None),[]).append(str(path))
            except Exception as e: errors.append(f'{bn}: container {path}: {e}')
    except Exception as e: errors.append(f'{bn}: containers: {e}')
    for i,obj in enumerate(env.objects):
        try:
            if getattr(obj.type,'name',str(obj.type))!='TextAsset': continue
            totals['textassets']+=1; d=obj.read(); value=getattr(d,'m_Script',b'')
            raw=value if isinstance(value,(bytes,bytearray,memoryview)) else str(value).encode('utf-8','surrogateescape')
            raw=bytes(raw); totals['bytes']+=len(raw)
            name=str(getattr(d,'m_Name',None) or f'TextAsset_{i}')
            cps=paths.get(getattr(obj,'path_id',None),[])
            rec={'bundle':bn,'index':i,'path_id':getattr(obj,'path_id',None),'name':name,'paths':cps,'bytes':len(raw)}
            inventory.append(rec)
            hit=bool(NAME_RE.search(name) or any(NAME_RE.search(x) for x in cps))
            if hit:
                totals['relevant']+=1; safe=re.sub(r'[^A-Za-z0-9_.-]+','_',name)[:120]
                fn=OUT/f'{bn}__{i:05d}__{safe}.bin'; fn.write_bytes(raw); rec['raw_dump']=str(fn.relative_to(ROOT)); relevant.append((rec,raw))
        except Exception as e: errors.append(f'{bn} TextAsset {i}: {e}')

for rec,raw in relevant:
    rec['strings']=[]; rec['wire']=[]; rec['search_hits']=[]
    for off,s in strings_at(raw):
        rec['strings'].append({'offset':off,'value':s})
        if SEARCH_RE.search(s): rec['search_hits'].append({'offset':off,'value':s})
    for m in re.finditer(r'(?i)(?:sea|turtle|beast|monster|trap|goddess|statue|wonder|garrison|resource|gather|world|map|territory|guild|union|king|spawn|unit|building|server)',raw.decode('latin1')):
        if m.start()==0 or True: pass
    rec['wire']=wire(raw); totals['wire_records']+=len(rec['wire']); totals['string_hits']+=len(rec['search_hits'])

inv=AS/'config-textasset-inventory.txt'
with inv.open('w',encoding='utf-8') as f:
    f.write('TextAsset inventory (raw m_Script extraction)\n')
    f.write('Raw rule: bytes used directly; non-bytes encoded with utf-8/surrogateescape; decoded surrogate strings are never written.\n\n')
    for r in inventory:
        f.write(f"[{r['bundle']}] index={r['index']} path_id={r['path_id']} name={r['name']!r} bytes={r['bytes']}\n")
        f.write('  container_paths: '+(' | '.join(r['paths']) if r['paths'] else '(none)')+'\n')

report=AS/'config-relevant-report.txt'
with report.open('w',encoding='utf-8') as f:
    f.write('Relevant UnityPy config TextAsset report\n')
    f.write('No coordinates inferred; numeric values are reported only with offsets/explicit wire fields or literal strings.\n\n')
    f.write('COUNTS\n'+json.dumps(totals,indent=2)+'\nErrors: '+str(len(errors))+'\n\n')
    for rec,raw in relevant:
        f.write('\n'+'='*100+'\n')
        f.write(f"TABLE name={rec['name']!r} bundle={rec['bundle']} index={rec['index']} path_id={rec['path_id']} bytes={rec['bytes']}\n")
        f.write('PATHS: '+(' | '.join(rec['paths']) if rec['paths'] else '(none)')+'\nRAW: '+rec['raw_dump']+'\n')
        f.write('ASCII/UTF8-LIKE STRINGS (offset, escaped value)\n')
        for x in rec['strings']:
            f.write(f"  0x{x['offset']:x} ({x['offset']}): {x['value']!r}\n")
        f.write('SEARCH MATCHES\n')
        for x in rec['search_hits']: f.write(f"  0x{x['offset']:x}: {x['value']!r}\n")
        f.write('PROTOBUF-LIKE WIRE FIELDS (offset, field, wire, values)\n')
        for x in rec['wire']:
            vals={k:v for k,v in x.items() if k not in ('offset','field','wire')}
            f.write(f"  0x{x['offset']:x}: field={x['field']} wire={x['wire']} {json.dumps(vals,ensure_ascii=True)}\n")
    if errors: f.write('\nERRORS (non-fatal)\n'+'\n'.join(errors)+'\n')
print(json.dumps({'counts':totals,'inventory':str(inv),'report':str(report),'raw_dir':str(OUT),'errors':len(errors)},indent=2))
