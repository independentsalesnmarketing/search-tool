#!/usr/bin/env python3
"""Extract publicly accessible, CURRENT nationwide FCC/Esri provider + geography rows.
No stale Form 477 sources, no guessed ZIPs, no implied address-qualified plans.
"""
import csv,json,os,time,requests,datetime,sys
from pathlib import Path
BASE="https://services8.arcgis.com/peDZJliSvYims39Q/ArcGIS/rest/services/FCC_Broadband_Data_Collection_December_2024_View/FeatureServer"
# Despite URL label, item metadata says source dataset as of Dec. 2025.
OUT=Path("out");OUT.mkdir(exist_ok=True)
PATTERNS=["Verizon","Cellco","Frontier","Metronet","Lumos","T-Mobile","Brightspeed","Charter","Spectrum","Windstream","Kinetic","Optimum","Altice","Cincinnati Bell","altafiber","EarthLink"]
FILTER=" OR ".join("ProviderName LIKE '%"+p.replace("'","''")+"%'" for p in PATTERNS)
SESSION=requests.Session();SESSION.headers.update({"User-Agent":"StanceNationalResearch/1.0 FCC GIS coverage extractor"})
stats=[]

def get(url,params,limit=8):
    for a in range(limit):
        try:
            r=SESSION.get(url,params=params,timeout=(15,120))
            if r.status_code in (429,500,502,503,504): raise ValueError("HTTP "+str(r.status_code))
            r.raise_for_status()
            val=r.json()
            if "error" in val:raise ValueError(str(val["error"])[:300])
            return val
        except Exception as e:
            print("RETRY",a+1,str(e)[:250],flush=True)
            if a==limit-1: raise
            time.sleep(min(2**a,25))
    raise RuntimeError("unreachable")

def extract(layer,name,filtered,fields):
    where=FILTER if filtered else "1=1"
    url=f"{BASE}/{layer}/query"
    offset=0;count=0;pages=0
    path=OUT/(name+".csv")
    with open(path,"w",newline="",encoding="utf8") as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        while True:
            params={"where":where,"outFields":",".join(fields),"returnGeometry":"false","f":"json",
                    "orderByFields":"OBJECTID ASC","resultOffset":offset,"resultRecordCount":2000}
            v=get(url,params)
            rows=v.get("features",[])
            for row in rows: writer.writerow({k:row.get("attributes",{}).get(k) for k in fields})
            n=len(rows);count+=n;pages+=1
            print(f"{name} page={pages} fetched={n} total={count} offset={offset} exceeded={v.get('exceededTransferLimit')}",flush=True)
            if n==0 or (n<2000 and not v.get("exceededTransferLimit")):break
            offset+=n
            if pages>10000:raise RuntimeError("Safety page limit")
    stats.append(dict(file=path.name,rows=count,pages=pages,filtered=filtered))
    return count

errors=[]
targets=[
 (11,"provider_states",True,["OBJECTID","GEOID","ProviderName","FRN","Technology","TotalBSLs","ServedBSLs","UnderservedBSLs","UnservedBSLs"]),
 (10,"provider_counties",True,["OBJECTID","GEOID","ProviderName","FRN","Technology","TotalBSLs","ServedBSLs","UnderservedBSLs","UnservedBSLs"]),
 (0,"all_state_denominators",False,["OBJECTID","GEOID","TotalBSLs"]),
 (1,"all_county_denominators",False,["OBJECTID","GEOID","TotalBSLs"]),
]
for t in targets:
 try: extract(*t)
 except Exception as e: errors.append({"table":t[1],"error":str(e)});print("ERROR",t[1],e,flush=True)
manifest={"as_of":"2025-12-31","extracted_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
"source":BASE,"source_layers":{x[1]:x[0] for x in targets},
"records":stats,"errors":errors,"pattern_filter":PATTERNS,
"warning":"ServedBSLs is not equivalent to all commission qualifying retail tiers. Counts are BSLs, not households. Brand aliases may be incomplete. No ZIP coverage inferred."}
(OUT/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf8")
if not stats: sys.exit(1)
