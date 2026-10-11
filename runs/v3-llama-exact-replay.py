"""Offline exact-prompt replay of 71 new responses plus one new supplement."""
import datetime
import hashlib
import json
from pathlib import Path
import socket
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'scripts'))
import rehearse
import snapshot

canonical=lambda value:json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))
files=['runs/v3-llama-requests.jsonl','runs/v3-llama-supplement.jsonl']
lookup={};sources=[];cost=0
for name in files:
    raw=(ROOT/name).read_bytes();sources.append({'path':name,'sha256':hashlib.sha256(raw).hexdigest()})
    for row in map(json.loads,raw.decode().splitlines()):
        request=dict(row['request']);provider=request.pop('provider')
        assert provider=={'only':['deepinfra/fp8'],'allow_fallbacks':False,'require_parameters':True,
                         'max_price':{'prompt':0.05,'completion':0.10,'request':0}}
        assert row['response']['usage']['is_byok'] is False
        key=canonical(request);assert key not in lookup
        lookup[key]=row['response'];cost+=float(row['response']['usage']['cost'])
expected=json.loads((ROOT/'runs/v3-exact-subject-requests.json').read_text())
assert len(expected)==len(lookup)==72 and set(lookup)=={canonical(r) for r in expected}
seen=[]
def http(url,body):
    request=json.loads(body);seen.append(canonical(request))
    return 200,json.dumps(lookup[canonical(request)]).encode()
claim=rehearse.load_claim(str(ROOT/'calibration/claim-court24-v3.json'))
with patch.object(socket.socket,'connect',side_effect=AssertionError('Offline replay attempted network')):
    driver,cid,verdict,certificate=rehearse.run_rehearsal(claim,'meta-llama/llama-3.1-8b-instruct',1000,http)
assert len(seen)==72 and set(seen)==set(lookup)
assert certificate['pinned_milli']==certificate['rewrite_milli']==1000
assert certificate['recall_milli']==0 and certificate['recall_probes']==24
assert certificate['dead_probes']==0 and certificate['admissible_probes']==certificate['items_probed']==24
case=snapshot.build_case(driver.view,cid,label='Llama 3.1 8B',note='Offline exact replay of actual new v3 model responses; scripted referee admission. Not native consensus.')
previews={rehearse.S.tool.content_hash(item['prompt']):item['prompt'] for item in claim['_items']}
sealed={item['content_hash']:item['item_hash'] for item in case['items']}
result=snapshot.envelope('simulation','',[case],snapshot.build_registry(driver.view,previews,sealed),
    int(datetime.datetime.now(datetime.timezone.utc).timestamp()),
    'Exact new-prompt real model responses, local contract and scripted admission; forecast only. Initial 74 attempts and 3 no-reply outcomes retained separately.')
(ROOT/'runs/v3-llama-verified.json').write_text(json.dumps(result,indent=1)+'\n')
report={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'kind':'offline exact new-prompt replay',
    'source_sha256':hashlib.sha256((ROOT/'contracts/impeach.py').read_bytes()).hexdigest(),
    'claim_sha256':hashlib.sha256((ROOT/'calibration/claim-court24-v3.json').read_bytes()).hexdigest(),
    'source_transcripts':sources,'initial_attempts':74,'initial_no_reply':3,'supplement_calls':1,
    'unique_actual_new_requests':72,'exact_prompt_replay':True,'new_calls_during_replay':0,
    'recorded_response_cost_usd':cost,'all_responses_credit_only':True,'local_forecast':verdict,
    'local_certificate':certificate,'native_certificate':False,'gate_passed':True}
(ROOT/'runs/v3-llama-verified-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['unique_actual_new_requests','initial_attempts','initial_no_reply',
    'supplement_calls','exact_prompt_replay','recorded_response_cost_usd','local_forecast','native_certificate','gate_passed']}))
