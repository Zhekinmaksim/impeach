import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import test from 'node:test';
import {canonical, COURT24_V2_CLAIM, COURT24_V2_SCRIPTED_CLAIM, COURT24_V3_CLAIM, trialRequests} from '../lib/proxy.mjs';
import {createLiveV3Proxy} from '../api/live-v3/chat/completions.mjs';

const MODEL='meta-llama/llama-3.1-8b-instruct';
const NOW=Date.parse('2026-10-11T12:00:00Z');
const ENV={OPENROUTER_API_KEY:'offline-test-key',OPENROUTER_MODEL:MODEL,
  OPENROUTER_PROVIDER:'deepinfra/fp8',TRIAL_ENABLED:'true',TRIAL_V2_ENABLED:'true',
  TRIAL_V3_ENABLED:'true',TRIAL_CREDIT_ONLY:'true',TRIAL_BUDGET_USD:'5',
  TRIAL_EXPIRES_AT:'2026-10-11T15:59:00Z'};
const KEY={limit:5,limit_remaining:3,limit_reset:null,byok_usage:0,
  include_byok_in_limit:false,is_management_key:false};
const post=body=>new Request('https://example.test/api/live-v3/chat/completions',{
  method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});

test('v3 allows exactly the 72 requests produced by the frozen contract',()=>{
  const script=`import json,sys
sys.path.insert(0,'scripts')
import rehearse
seen=[]
def http(url,body):
    seen.append(json.loads(body))
    return 200,json.dumps({'choices':[{'message':{'content':'ANSWER: 0'}}]}).encode()
rehearse.run_rehearsal(rehearse.load_claim('${COURT24_V3_CLAIM}'),'${MODEL}',0,http)
print(json.dumps(seen))`;
  const actual=JSON.parse(execFileSync('python3',['-c',script],{
    cwd:new URL('../',import.meta.url),encoding:'utf8'}));
  const allowed=trialRequests(MODEL,COURT24_V3_CLAIM);
  assert.equal(actual.length,72);
  assert.equal(new Set(allowed.map(canonical)).size,72);
  assert.deepEqual(allowed.map(canonical).sort(),actual.map(canonical).sort());
});

test('v3 switch is independent and excludes every prior corpus before upstream',async()=>{
  const calls=[];
  const fetchImpl=async(url,init)=>{
    calls.push({url,init});
    return url.endsWith('/key')?Response.json({data:KEY}):Response.json({
      choices:[{message:{content:'ANSWER: 36'}}],usage:{is_byok:false}});
  };
  const body=trialRequests(MODEL,COURT24_V3_CLAIM)[0];
  const disabled=createLiveV3Proxy({env:{...ENV,TRIAL_V3_ENABLED:undefined},fetchImpl,now:()=>NOW});
  assert.equal((await disabled(post(body))).status,503);
  assert.equal(calls.length,0);
  const enabled=createLiveV3Proxy({env:ENV,fetchImpl,now:()=>NOW});
  for(const claim of ['calibration/claim-gsm8k.json',COURT24_V2_CLAIM,COURT24_V2_SCRIPTED_CLAIM]){
    for(const prior of trialRequests(MODEL,claim))assert.equal((await enabled(post(prior))).status,403);
  }
  for(const invalid of [{...body,max_tokens:513},{...body,seed:8},
    {...body,model:'scripted/memoriser-court24-v2'},
    {...body,messages:[{role:'user',content:'hello'}]}])assert.equal((await enabled(post(invalid))).status,403);
  assert.equal(calls.length,0);
  assert.equal((await enabled(post(body))).status,200);
  const forwarded=JSON.parse(calls[1].init.body);
  assert.deepEqual(forwarded.provider,{only:['deepinfra/fp8'],allow_fallbacks:false,require_parameters:true,
    max_price:{prompt:0.05,completion:0.10,request:0}});
  delete forwarded.provider;assert.deepEqual(forwarded,body);
});

test('v3 retains the shared $5 cap and four-hour gateway window despite a longer court trial',async()=>{
  const body=trialRequests(MODEL,COURT24_V3_CLAIM)[0];
  for(const options of [
    {env:{TRIAL_BUDGET_USD:'5.01'}},{env:{TRIAL_EXPIRES_AT:'2026-10-11T16:00:01Z'}},
    {env:{OPENROUTER_PROVIDER:'other'}},{key:{limit:6}},{key:{limit_remaining:0.09}},
    {key:{limit_reset:'daily'}},{key:{byok_usage:0.01}},
    {completion:{choices:[{message:{content:'ANSWER: 36'}}]}},
  ]){
    let calls=0;
    const handle=createLiveV3Proxy({env:{...ENV,...options.env},now:()=>NOW,
      fetchImpl:async url=>{
        calls++;
        return url.endsWith('/key')?Response.json({data:{...KEY,...options.key}}):Response.json(options.completion);
      }});
    assert.equal((await handle(post(body))).status,options.completion?502:503);
    assert.equal(calls,options.env?0:options.key?1:2);
  }
});
