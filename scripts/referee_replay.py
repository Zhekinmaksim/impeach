#!/usr/bin/env python3
"""Replay exact recorded referee prompts; optionally fetch missing calls only.

This is offline calibration evidence, not validator consensus. Stored responses
are never changed. Supplementary calls have a separate raw transcript and cap.
"""
import argparse
from collections import defaultdict, deque
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.request

import referee_dryrun
from local_env import load_local_env, model_key


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--claim', required=True)
    p.add_argument('--controls', required=True)
    p.add_argument('--transcript', type=Path, action='append', required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--supplement', type=Path)
    p.add_argument('--model', default='anthropic/claude-sonnet-4.6')
    p.add_argument('--max-tokens', type=int, default=1024)
    p.add_argument('--cost-cap', type=float, default=0.05)
    p.add_argument('--total-cost-cap', type=float, default=2.20)
    a = p.parse_args()
    cache = defaultdict(deque)
    source_files = []
    for path in a.transcript:
        raw = path.read_bytes()
        source_files.append({'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()})
        for row in map(json.loads,raw.decode().splitlines()):
            if row['request']['model'] != a.model:
                raise SystemExit('recorded model does not match')
            prompt = row['request']['messages'][0]['content']
            cache[prompt].append(row)
    load_local_env()
    os.environ['REFEREE_MODEL']=a.model
    os.environ['OPENAI_BASE_URL']='https://openrouter.ai/api/v1'
    token = model_key()
    used, missing, cost = [], [], 0.0

    def request(path, body=None):
        req=urllib.request.Request('https://openrouter.ai/api/v1'+path,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=120) as response:
            return json.load(response)

    if a.supplement:
        if a.supplement.exists():
            raise SystemExit('supplement already exists; use it as a replay transcript')
        model=next(m for m in request('/models')['data'] if m['id']==a.model)
        pricing=model['pricing']
        a.supplement.parent.mkdir(parents=True,exist_ok=True)

    def llm(prompt):
        nonlocal cost
        digest=hashlib.sha256(prompt.encode()).hexdigest()
        if cache[prompt]:
            row=cache[prompt].popleft()
            used.append({'prompt_sha256':digest,'source':'recorded','index':row.get('index')})
            return row['response']['choices'][0]['message']['content']
        missing.append(digest)
        if not a.supplement:
            raise RuntimeError('missing recorded prompt '+digest)
        maximum=(len(prompt.encode())+200)*float(pricing['prompt'])+a.max_tokens*float(pricing['completion'])+float(pricing.get('request',0))
        key=request('/key')['data']
        if key['limit']!=5 or key['limit_reset'] is not None or key['byok_usage']!=0:
            raise SystemExit('dedicated capped credit key required')
        if cost+maximum>a.cost_cap or float(key['usage'])+maximum>a.total_cost_cap:
            raise SystemExit('supplement cap reached; no request sent')
        body={'model':a.model,'messages':[{'role':'user','content':prompt}],
              'temperature':0,'max_tokens':a.max_tokens}
        if 'response_format' in model.get('supported_parameters',[]):
            body['response_format']={'type':'json_object'}
        if 'reasoning' in model.get('supported_parameters',[]):
            body['reasoning']={'enabled':False}
        response=request('/chat/completions',body)
        usage=response.get('usage',{})
        paid=usage.get('cost',maximum)
        cost+=float(paid)
        row={'index':len(missing),'at':int(time.time()),'request':body,'response':response,
             'usage':usage,'cost_usd':paid,'prompt_sha256':digest}
        with a.supplement.open('a',encoding='utf-8') as f:
            f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
        used.append({'prompt_sha256':digest,'source':'supplement','index':len(missing)})
        return response['choices'][0]['message']['content']

    referee_dryrun.live_llm=llm
    result_path=a.out.with_suffix('.rulings.json')
    sys.argv=['referee_dryrun.py','--claim',a.claim,'--controls',a.controls,'--out',str(result_path)]
    result=referee_dryrun.main()
    rows=json.loads(result_path.read_text())['rows']
    report={'kind':'offline referee replay with exact prompts','source_sha256':hashlib.sha256((Path(__file__).resolve().parents[1]/'contracts/impeach.py').read_bytes()).hexdigest(),
            'model':a.model,'claim':a.claim,'source_transcripts':source_files,
            'recorded_calls':sum(x['source']=='recorded' for x in used),'supplemented_calls':sum(x['source']=='supplement' for x in used),
            'missing_prompts':missing if not a.supplement else [],'supplement_cost_usd':cost,
            'honest_admitted':sum(r['expect']=='ADMISSIBLE' and r['ok'] for r in rows),
            'controls_rejected_both':sum(r['expect']=='INADMISSIBLE' and r['framing_1']==r['framing_2']=='INADMISSIBLE' for r in rows),
            'gate_passed':result==0 and (bool(a.supplement) or not missing),'calls':used,'rows':rows}
    a.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','calls')},indent=2),flush=True)
    return 0 if report['gate_passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
