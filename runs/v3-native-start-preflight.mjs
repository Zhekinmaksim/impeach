// Public read-only native preflight. No account, signing, endpoint or model calls.
import {readFileSync,writeFileSync} from 'node:fs';
import {createClient,decodeInputData} from '/Users/zmaxx/.nvm/versions/node/v20.20.2/lib/node_modules/genlayer/node_modules/genlayer-js/dist/index.js';
import {testnetBradbury} from '/Users/zmaxx/.nvm/versions/node/v20.20.2/lib/node_modules/genlayer/node_modules/genlayer-js/dist/chains/index.js';
import {createPublicClient,http} from '/Users/zmaxx/.nvm/versions/node/v20.20.2/lib/node_modules/genlayer/node_modules/viem/_esm/index.js';
import {inspectQueue,json} from '../scripts/inspect_queue.mjs';
const address='0x45F610cefF1ed367d684A1839b1801Af12Cfb038';
const rpc='https://rpc-bradbury.genlayer.com';
const c=createClient({chain:testnetBradbury,endpoint:rpc});
const p=createPublicClient({chain:testnetBradbury,transport:http(rpc,{timeout:30000,retryCount:0})});
const input=JSON.parse(readFileSync('runs/v3-native-preflight-input.json','utf8'));
const call=(functionName,args=[])=>c.readContract({address,functionName,args});
const report={at:new Date().toISOString(),mode:'READ_ONLY_NO_MODEL_CALLS',address,rpc,input,
  native:await inspectQueue({address,rpc},{p,c,decodeInputData},readFileSync('build/impeach.py'))};
report.counts=await call('counts');
report.clock=await call('clock');
report.solvency=await call('solvency');
report.existing_claim1=await call('get_claim',[1n]);
report.existing_challenge1=await call('get_challenge',[1n]);
report.registry=await call('registry',[0n,100n]);
report.wallets=[];
for(const [role,wallet] of [['publisher','0x771388495F34d21C5574FeFc04cd1D5811E00aDa'],['challenger','0x4988285D5a05da3a1827f21330fdf14d9F81d4C9']]){
  report.wallets.push({role,address:wallet,wallet_wei:await p.getBalance({address:wallet}),contract_credit_wei:await call('balance_of',[wallet])});
}
report.unspent_checks=[];
for(let start=0;start<input.items.length;start+=3){
  const results=await Promise.all(input.items.slice(start,start+3).map(async item=>({...item,
    commitment_spent:await call('is_spent',[item.item_commitment]),
    content_spent:await call('is_spent',[item.content_hash])})));
  report.unspent_checks.push(...results);
}
report.counts_after=await call('counts');
report.all_24_unspent=report.unspent_checks.length===24&&report.unspent_checks.every(x=>x.commitment_spent===false&&x.content_spent===false);
report.native_queues_empty=Object.values(report.native.heads).every(x=>/^0x0+$/.test(x));
report.next_ids_from_actual_counts={claim_id:report.counts.claims,challenge_id:report.counts.challenges};
report.ended_at=new Date().toISOString();
writeFileSync('runs/v3-native-start-preflight.json',json(report)+'\n');
console.log(json({at:report.at,ended_at:report.ended_at,counts:report.counts,counts_after:report.counts_after,
  all_24_unspent:report.all_24_unspent,native_queues_empty:report.native_queues_empty,solvency:report.solvency,wallets:report.wallets}));
