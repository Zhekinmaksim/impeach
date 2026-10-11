"""One exact missing rehearsal request; no native writes, retries or secret output."""
import datetime
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'scripts'))
from local_env import load_local_env, model_key
from openrouter_server import NoRedirect

load_local_env()
audit=json.loads((ROOT/'runs/v3-llama-initial-coverage-audit.json').read_text())
assert len(audit['missing'])==1
missing=audit['missing'][0]
assert missing['mode']=='PINNED' and missing['item_index']==21
body=dict(missing['request'])
body['provider']={'only':['deepinfra/fp8'],'allow_fallbacks':False,'require_parameters':True,
                 'max_price':{'prompt':0.05,'completion':0.10,'request':0}}
out=ROOT/'runs/v3-llama-supplement.jsonl'
if out.exists():raise SystemExit('Existing supplement must be audited; never blind resend')
opener=urllib.request.build_opener(NoRedirect())
headers={'Authorization':'Bearer '+model_key(),'Content-Type':'application/json'}
with opener.open(urllib.request.Request('https://openrouter.ai/api/v1/key',headers=headers),timeout=30) as response:
    key=json.load(response)['data']
maximum=(len(json.dumps(body).encode())+1024)*0.05/1_000_000+512*0.10/1_000_000
assert key['limit']==5 and key['limit_reset'] is None and key['byok_usage']==0
assert float(key['limit_remaining'])>=0.10+maximum and float(key['usage'])+maximum<4.80
marker=ROOT/'runs/v3-llama-supplement-dispatch.json'
if marker.exists():raise SystemExit('Existing dispatch marker requires reconciliation')
marker.write_text(json.dumps({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'request_sha256':hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest(),
    'mode':missing['mode'],'item_index':missing['item_index'],'upper_bound_usd':maximum,
    'key_usage_before':key['usage'],'key_limit':key['limit']},indent=2)+'\n')
with opener.open(urllib.request.Request('https://openrouter.ai/api/v1/chat/completions',
    headers=headers,data=json.dumps(body).encode()),timeout=60) as response:
    result=json.load(response)
row={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'request':body,'response':result,
     'reason':'One missing exact PINNED item 21 in initial 74-attempt rehearsal; raw initial run preserved.'}
out.write_text(json.dumps(row,ensure_ascii=False)+'\n')
assert result['usage']['is_byok'] is False
assert result['model']=='meta-llama/llama-3.1-8b-instruct'
print(json.dumps({'mode':missing['mode'],'item_index':missing['item_index'],
    'content':result['choices'][0]['message']['content'],'cost_usd':result['usage']['cost'],
    'credit_only':result['usage']['is_byok'] is False}))
