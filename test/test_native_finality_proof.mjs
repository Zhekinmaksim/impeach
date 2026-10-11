import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {collectProof,finalizationEvent,EVENT,TOPIC} from '../scripts/native_finality_proof.mjs';
import {PINS,HEADS} from '../scripts/inspect_queue.mjs';
const court='0x'+'1'.repeat(40),tx='0x'+'a'.repeat(64),evm='0x'+'e'.repeat(64),blockHash='0x'+'f'.repeat(64);
function decode({abi,data,topics,strict}) {
  assert.deepEqual(abi,[EVENT]);assert.equal(strict,true);
  return {eventName:'TransactionFinalized',args:{txId:topics[1],previousStatus:Number(BigInt('0x'+data.slice(2,66))),
    shouldProcessMessages:BigInt('0x'+data.slice(66))!==0n}};
}
function fixture() {
  const log={address:PINS.FinalizationPhase[0],topics:[TOPIC,tx],data:'0x'+'d'.padStart(64,'0')+'0'.repeat(64),
    removed:false,transactionHash:evm,blockHash,blockNumber:40n,logIndex:1};
  const receipt={status:'success',to:PINS.ConsensusMain[0],transactionHash:evm,blockHash,blockNumber:40n,logs:[log]};
  const native={id:tx,recipient:court,status:7,value:0n,txCalldata:'0x00'};
  const calls=[];
  const p={getChainId:async()=>4221,getBlock:async({blockNumber}={})=>({number:blockNumber??42n,timestamp:100n,hash:blockHash}),
    getStorageAt:async({address})=>'0x'+'0'.repeat(24)+Object.values(PINS).find(v=>v[0]===address)[1].slice(2),
    readContract:async({functionName:fn,args})=>{
      if(fn==='addressManager')return PINS.AddressManager[0];if(fn==='VERSION')return '2.0.0';
      if(fn==='getAddressNonZero')return PINS[args[0]][0];if(HEADS.includes(fn))return '0x'+'0'.repeat(64);
      if(fn==='getTransaction')return native;if(fn==='canFinalize')return [false,0n,0n];
      if(fn==='getTxQueueType')return 0;if(fn==='isAtFinalizedQueueHead')return false;
      return {};
    },getLogs:async q=>{calls.push(q);return [log];},getTransactionReceipt:async()=>receipt,
    getTransaction:async()=>({hash:evm,blockHash,blockNumber:40n,to:PINS.ConsensusMain[0],value:0n})};
  const deps={p,c:{getContractCode:async()=>'source',getTransaction:async()=>({recipient:court,status:7})},
    decodeInputData:()=>({type:'call'}),decodeEventLog:decode};
  return {options:{address:court,tx,lookback:50},deps,receipt,log,native,calls};
}
test('read-only lookup binds canonical receipt and protocol pins to native FINAL',async()=>{
  const f=fixture();const b=await collectProof(f.options,f.deps,Buffer.from('source'));
  assert.equal(b.origin,'chain_observation');assert.equal(b.event.previousStatus,13);
  assert.equal(b.event.shouldProcessMessages,false);assert.equal(b.evm.receipt.status,'success');
  assert.equal(f.calls[0].address,PINS.FinalizationPhase[0]);assert.deepEqual(f.calls[0].args,{txId:tx});
});
test('saved real C0 receipt has Phase UND/no-messages event while Main event alone is insufficient',()=>{
  const receipt=JSON.parse(readFileSync(new URL('../runs/c0-finality-20261011-resume/0xb120096abc56a06cf058af128c260184348a03ce4bb1a4d4cba883b69d087541.evm-receipt.json',import.meta.url)));
  const id='0xb120096abc56a06cf058af128c260184348a03ce4bb1a4d4cba883b69d087541';
  assert.equal(finalizationEvent(receipt,id,decode).previousStatus,6);
  receipt.logs=receipt.logs.filter(l=>l.address.toLowerCase()===PINS.ConsensusMain[0].toLowerCase());
  assert.throws(()=>finalizationEvent(receipt,id,decode),/missing/);
});
test('wrong event, identity, boolean, duplicate, reorg or nonfinal native cannot authorize',async()=>{
  for(const change of [f=>f.log.removed=true,f=>f.log.address=PINS.ConsensusMain[0],
    f=>f.log.topics[1]='0x'+'c'.repeat(64),f=>f.log.data='0x'+'5'.padStart(64,'0')+'0'.repeat(64),
    f=>f.log.data=f.log.data.slice(0,-1)+'1',f=>f.receipt.logs.push({...f.log}),
    f=>f.receipt.status='reverted',f=>f.receipt.blockHash='0x'+'c'.repeat(64),f=>f.native.status=13,
    f=>f.deps.p.getChainId=async()=>1]) {
    const f=fixture();change(f);await assert.rejects(collectProof(f.options,f.deps,Buffer.from('source')));
  }
});
test('unavailable evidence and bounded no-event search fail without any fallback mutation',async()=>{
  let f=fixture();f.deps.p.getLogs=async()=>{throw new Error('archive logs unavailable');};
  await assert.rejects(collectProof(f.options,f.deps,Buffer.from('source')),/unavailable/);
  f=fixture();f.options.lookback=20000;f.deps.p.getBlock=async()=>({number:30000n,timestamp:100n,hash:blockHash});
  f.deps.p.getLogs=async q=>{f.calls.push(q);return [];};
  await assert.rejects(collectProof(f.options,f.deps,Buffer.from('source')),/bounded log range/);
  assert.equal(f.calls.length,20);assert.equal(f.calls[0].toBlock,30000n);assert.equal(f.calls.at(-1).fromBlock,10001n);
});
