import os, re, zipfile, json, traceback
from pathlib import Path
import UnityPy

root=Path(r'F:\ZeroOne'); apk=root/'xapk-extracted'/'UnityDataAssetPack.apk'; assets=root/'analysis-assets'; export=root/'config-export'; assets.mkdir(exist_ok=True); export.mkdir(exist_ok=True)
want=['x3.config.ab','x3.config_asset.ab','x3.config_dk.ab']
with zipfile.ZipFile(apk) as z:
    for n in want:
        p=assets/n
        if not p.exists():
            with z.open('assets/AssetBundles/'+n) as src, open(p,'wb') as dst:
                while True:
                    b=src.read(1024*1024)
                    if not b: break
                    dst.write(b)
terms=['SeaTurtle','turtle','sea beast','seabeast','trap','goddess','statue','wondergoddess','garrison','resource','gathering','KingOfSeas','sea area','alliance','guild building','coordinates','coordinate','position','spawn','server','map ID','mapid','150']
term_re=re.compile('|'.join(re.escape(x) for x in terms),re.I)
records=[]; alltext=[]; errors=[]
def decode(b):
    for enc in ('utf-8','utf-16-le','utf-16-be'):
        try:
            s=b.decode(enc)
            if enc=='utf-8' and '\x00' in s: continue
            return s,enc
        except UnicodeDecodeError: pass
    return None,None
def safe(s): return re.sub(r'[^A-Za-z0-9_.-]+','_',str(s))[:180]
for bundle in want:
    bp=assets/bundle; out=export/bundle; out.mkdir(exist_ok=True)
    try: env=UnityPy.load(str(bp))
    except Exception as e: errors.append(f'{bundle}: load: {e}'); continue
    containers=[]
    try:
        for path, entry in env.container.items():
            try:
                obj=entry.resolve() if hasattr(entry,'resolve') else entry
                containers.append((str(path), getattr(obj,'type',None).name if getattr(obj,'type',None) else '?'))
            except Exception as e: containers.append((str(path),f'ERROR {e}'))
    except Exception as e: errors.append(f'{bundle}: container: {e}')
    for i,obj in enumerate(env.objects):
        try:
            typ=obj.type.name
            if typ!='TextAsset': continue
            d=obj.read(); raw=getattr(d,'m_Script',b'')
            if isinstance(raw,str): raw=raw.encode('utf-8','surrogatepass')\n            raw=bytes(raw)
            name=getattr(d,'m_Name',f'TextAsset_{i}') or f'TextAsset_{i}'
            paths=[p for p,t in containers if t=='TextAsset' and (name in p or True)]
            # retain all container paths whose resolved object identity/file id matches when possible; fallback list is useful inventory
            fn=f'{i:04d}_{safe(name)}.bin'; (out/fn).write_bytes(raw)
            text,enc=decode(raw)
            rec={'bundle':bundle,'index':i,'name':str(name),'file':str((out/fn).relative_to(root)),'bytes':len(raw),'encoding':enc,'text':text,'paths':paths}
            records.append(rec)
            if text is not None: alltext.append((rec,text))
            else:
                # printable ASCII and UTF-16LE strings for binary config inspection
                a=' '.join(re.findall(r'[ -~]{4,}',raw.decode('latin1')))
                u=' '.join(re.findall(r'(?:[ -~]\x00){4,}',raw.decode('latin1')))
                rec['strings']=(a+' '+u).strip()
        except Exception as e: errors.append(f'{bundle} TextAsset {i}: {e}')
# improve paths by mapping container entries to object path where entry resolves and matches source object file id
for rec in records:
    try:
        env=UnityPy.load(str(assets/rec['bundle']))
        obj=env.objects[rec['index']]
        hits=[]
        for p,e in env.container.items():
            x=e.resolve() if hasattr(e,'resolve') else e
            if getattr(x,'path_id',None)==getattr(obj,'path_id',None): hits.append(str(p))
        rec['paths']=hits or rec['paths'][:30]
    except: pass
report=root/'analysis-assets'/'config-search-report.txt'
with open(report,'w',encoding='utf-8',errors='replace') as f:
    f.write('UnityPy config bundle search report\n')
    f.write('Source: xapk-extracted/UnityDataAssetPack.apk; raw TextAsset m_Script bytes exported under config-export/<bundle>/\n\n')
    f.write('BUNDLES\n')
    for b in want: f.write(f'  {b}: { (assets/b).stat().st_size } bytes\n')
    f.write('\nTEXTASSET INVENTORY / CONTAINER PATHS\n')
    for r in records: f.write(f"\n[{r['bundle']}] {r['index']} {r['name']} ({r['bytes']} bytes, {r['encoding'] or 'binary'})\n  file: {r['file']}\n  container: {' | '.join(r['paths']) if r['paths'] else '(none)'}\n")
    f.write('\nCASE-INSENSITIVE MATCHES WITH NEARBY CONTEXT\n')
    found=0
    for r,t in alltext:
        lines=t.splitlines() or [t]
        hits=[j for j,x in enumerate(lines) if term_re.search(x)]
        if hits:
            found+=len(hits); f.write(f"\n[{r['bundle']}] {r['name']} :: {r['file']}\n")
            seen=set()
            for j in hits:
                for k in range(max(0,j-2),min(len(lines),j+3)):
                    if k not in seen: f.write(f'  L{k+1}: {lines[k][:1000]}\n'); seen.add(k)
    f.write(f'\nMATCHED TEXT LINES: {found}\n')
    f.write('\nBINARY/PRINTABLE STRING MATCHES\n')
    for r in records:
        if r.get('text') is None and term_re.search(r.get('strings','')):
            s=r['strings']; f.write(f"\n[{r['bundle']}] {r['name']} :: {r['file']}\n  {s[:4000]}\n")
    f.write('\nNUMERIC/CONFIG REFERENCES NEAR TERMS\n')
    num=re.compile(r'(?<![A-Za-z0-9])(?:-?\d+(?:\.\d+)?)(?![A-Za-z0-9])')
    for r,t in alltext:
        lines=t.splitlines()
        for j,line in enumerate(lines):
            if term_re.search(line):
                nums=num.findall(line)
                if nums: f.write(f"[{r['bundle']}] {r['name']} L{j+1}: numbers={','.join(nums)} | {line[:1000]}\n")
    f.write('\nINTERPRETATION / LIMITATIONS\n')
    f.write('Only literal case-insensitive matches and nearby serialized text were reported; coordinates were not inferred. TextAssets that decode as binary are preserved byte-for-byte and printable strings are shown where available. Static-vs-server-state evidence requires runtime/network code or scene data; this report does not claim coordinates are static without explicit fields/formulas.\n')
    if errors: f.write('\nERRORS\n'+'\n'.join(errors)+'\n')
print(f'Exported {len(records)} TextAssets; report={report}; errors={len(errors)}')

