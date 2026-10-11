import test from "node:test";
import assert from "node:assert/strict";
import {inspectQueue, verifyProtocol, PINS, SLOT, HEADS, json} from "../scripts/inspect_queue.mjs";

const court="0x"+"1".repeat(40), tx="0x"+"a".repeat(64), zero="0x"+"0".repeat(64);
function fixture() {
  const calls=[];
  const receipt={recipient:court,status:11,result:1,txExecutionResult:1};
  const stored={id:tx,recipient:court,status:5,txCalldata:"0x00"};
  const options={address:court};
  const p={getChainId:async()=>4221,getBlock:async()=>({number:42n,timestamp:100n}),
    getStorageAt:async({address,slot})=>{assert.equal(slot,SLOT); const pin=Object.values(PINS).find(v=>v[0]===address); return "0x"+"0".repeat(24)+pin[1].slice(2);},
    readContract:async request=>{
      calls.push(request); assert.equal(request.blockNumber,42n);
      const {functionName: fn,address,args}=request;
      if(fn==="addressManager")return PINS.AddressManager[0];
      if(fn==="VERSION")return "2.0.0";
      if(fn==="getAddressNonZero")return PINS[args[0]][0];
      if(HEADS.includes(fn)){assert.equal(args[0],court);return fn==="getFinalizedHeadTxId"?tx:zero;}
      if(fn==="getTransaction")return stored;
      if(fn==="getTimeouts"){assert.equal(address,PINS.Idleness[0]);return {accept:100n};}
      if(fn==="getTimestamps"){assert.equal(address,PINS.Idleness[0]);return {lastVote:10n};}
      if(fn==="getTxQueueType"||fn==="isAtFinalizedQueueHead"){assert.equal(args[0],court);return fn==="getTxQueueType"?2:true;}
      if(fn==="canFinalize")return [false,100n,0n];
      if(fn==="getLastQueueModification")return {lastQueueType:2,lastQueueTimestamp:10n};
      if(fn==="checkFirstSlotElapsed"){assert.equal(address,PINS.Idleness[0]);return true;}
      throw new Error("unexpected read "+fn);
    }};
  const c={getContractCode:async()=>"source",getTransaction:async()=>receipt};
  return {options,deps:{p,c,decodeInputData:()=>({type:"call",leaderOnly:false,callData:new Map([["method","probe"],["args",[0n,0n,"PINNED",""]]])})},calls,stored,receipt};
}

test("reads explicit court heads and Main timers while retaining advisory false and decoded calldata",async()=>{
  const f=fixture(); f.stored.status=4;
  const result=await inspectQueue(f.options,f.deps,Buffer.from("source"));
  assert.equal(result.protocol.chainId,4221);
  assert.equal(result.transactions[0].canFinalize[0],false);
  assert.equal(result.transactions[0].firstSlotElapsed,true);
  assert.deepEqual(JSON.parse(json(result)).transactions[0].decoded.callData,{method:"probe",args:["0","0","PINNED",""]});
});

test("wrong chain or changed implementation/registry/version fails before transaction inspection",async()=>{
  for(const change of [
    f=>f.deps.p.getChainId=async()=>1,
    f=>f.deps.p.getStorageAt=async()=>"0x"+"0".repeat(64),
    f=>{const read=f.deps.p.readContract;f.deps.p.readContract=async q=>q.functionName==="getAddressNonZero"&&q.args[0]==="Idleness"?court:read(q);},
    f=>{const read=f.deps.p.readContract;f.deps.p.readContract=async q=>q.functionName==="VERSION"?"future":read(q);},
  ]) {const f=fixture();change(f); await assert.rejects(verifyProtocol(f.deps.p,42n)); assert.equal(f.calls.some(c=>c.functionName==="getTransaction"),false);}
});

test("deployed source mismatch and another court recipient are rejected",async()=>{
  let f=fixture(); await assert.rejects(inspectQueue(f.options,f.deps,Buffer.from("changed source")),/source differs/);
  f=fixture();f.stored.recipient="0x"+"2".repeat(40);await assert.rejects(inspectQueue(f.options,f.deps,Buffer.from("source")),/another court/);
});

test("finalized inspection does not call the transitional idleness check",async()=>{
  const f=fixture();f.stored.status=7;f.receipt.status=7;
  const result=await inspectQueue(f.options,f.deps,Buffer.from("source"));
  assert.equal(result.transactions[0].firstSlotElapsed,false);
  assert.equal(f.calls.some(c=>c.functionName==="checkFirstSlotElapsed"),false);
});
