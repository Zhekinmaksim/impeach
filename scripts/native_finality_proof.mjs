#!/usr/bin/env node
// Read-only proof lookup. No account/keychain/signing imports.
import {execFileSync} from 'node:child_process';
import {readFileSync, realpathSync} from 'node:fs';
import {dirname, join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {inspectQueue, verifyProtocol, PINS, json} from './inspect_queue.mjs';
import {writeLine} from './output.mjs';

export const EVENT = {type:'event',name:'TransactionFinalized',anonymous:false,inputs:[
  {name:'txId',type:'bytes32',indexed:true}, {name:'previousStatus',type:'uint8',indexed:false},
  {name:'shouldProcessMessages',type:'bool',indexed:false}]};
export const TOPIC = '0xfcc739ca8e51c67e4fd127179070d26ae8ed5ed6dcbc26bcd88ff81c50f346a6';
const same=(a,b)=>typeof a==='string' && typeof b==='string' && a.toLowerCase()===b.toLowerCase();
const ensure=(condition,message)=>{if(!condition)throw new Error(message);};

export function finalizationEvent(receipt, tx, decodeEventLog) {
  const logs=receipt.logs.filter(log=>same(log.address,PINS.FinalizationPhase[0]) &&
    same(log.topics?.[0],TOPIC) && same(log.topics?.[1],tx));
  ensure(logs.length===1,'missing or competing FinalizationPhase evidence');
  const log=logs[0];
  ensure(log.removed===false && log.topics.length===2 && /^0x[0-9a-fA-F]{128}$/.test(log.data), 'invalid finalization log');
  ensure(same(log.transactionHash,receipt.transactionHash) && same(log.blockHash,receipt.blockHash) &&
    BigInt(log.blockNumber)===BigInt(receipt.blockNumber),'event/receipt identity mismatch');
  const decoded=decodeEventLog({abi:[EVENT],data:log.data,topics:log.topics,strict:true});
  ensure(decoded.eventName==='TransactionFinalized' && same(decoded.args.txId,tx) &&
    [6,12,13].includes(Number(decoded.args.previousStatus)) && decoded.args.shouldProcessMessages===false,
    'finalization may have processed application messages');
  return {txId:tx,previousStatus:Number(decoded.args.previousStatus),shouldProcessMessages:false,log};
}

export async function collectProof(options, deps, source) {
  const {p,decodeEventLog}=deps;
  const lookback=options.lookback ?? 20000;
  ensure(Number.isInteger(lookback) && lookback>0 && lookback<=20000,'invalid bounded log range');
  ensure(/^0x[0-9a-fA-F]{64}$/.test(options.tx),'invalid native hash');
  const snapshot=JSON.parse(json(await inspectQueue(options,deps,source)));
  const native=snapshot.transactions.find(t=>same(t.tx,options.tx));
  ensure(native?.stored.status===7 && native.receipt.status===7,'native transaction is not finalized');
  ensure(String(native.stored.value)==='0','native transaction is not zero-value');
  const tip=BigInt(snapshot.blockNumber), floor=tip>=BigInt(lookback)?tip-BigInt(lookback)+1n:0n;
  const found=[], ranges=[];
  for(let high=tip; high>=floor;) {
    const low=high-floor>=999n?high-999n:floor;
    ranges.push({fromBlock:low,toBlock:high});
    if(low===floor)break;
    high=low-1n;
  }
  if(!options.evmHash) {
    for(let offset=0;offset<ranges.length;offset+=4) {
      const results=await Promise.allSettled(ranges.slice(offset,offset+4).map(range=>p.getLogs({
        address:PINS.FinalizationPhase[0],event:EVENT,args:{txId:options.tx},...range,strict:true})));
      const errors=[];
      for(const result of results) {if(result.status==='fulfilled')found.push(...result.value);else errors.push(result.reason);}
      if(errors.length)throw new Error('bounded event lookup unavailable: '+String(errors[0]));
      ensure(found.length<=1,'competing finalization events');
    }
    ensure(found.length===1,'no finalization proof within bounded log range');
  } else ensure(/^0x[0-9a-fA-F]{64}$/.test(options.evmHash),'invalid explicit EVM hash');
  const receipt=await p.getTransactionReceipt({hash:options.evmHash || found[0].transactionHash});
  const transaction=await p.getTransaction({hash:receipt.transactionHash});
  ensure(receipt.status==='success' && same(receipt.to,PINS.ConsensusMain[0]) &&
    same(transaction.to,PINS.ConsensusMain[0]) && transaction.value===0n &&
    same(transaction.hash,receipt.transactionHash) && same(transaction.blockHash,receipt.blockHash) &&
    transaction.blockNumber != null && BigInt(transaction.blockNumber)===BigInt(receipt.blockNumber),
    'invalid finalization EVM transaction');
  const block=await p.getBlock({blockNumber:receipt.blockNumber});
  ensure(same(block.hash,receipt.blockHash) && BigInt(block.number)<=tip,'unconfirmed/noncanonical finalization');
  const eventProtocol=await verifyProtocol(p,receipt.blockNumber);
  const event=finalizationEvent(receipt,options.tx,decodeEventLog);
  ensure(options.evmHash || (same(found[0].blockHash,receipt.blockHash) && Number(found[0].logIndex)===Number(event.log.logIndex)),
    'lookup differs from confirmed receipt');
  return JSON.parse(json({format:'impeach-native-no-messages/1',tx:options.tx,address:options.address,
    observedAt:Date.now(),snapshot,eventProtocol,event,evm:{receipt,transaction,block},
    lookup:{fromBlock:floor,toBlock:tip,maxBlocks:lookback,explicitEvmHash:options.evmHash || null},origin:'chain_observation'}));
}

async function runtime(rpc) {
  const cli=realpathSync(execFileSync('which',['genlayer'],{encoding:'utf8'}).trim());
  const root=resolve(dirname(cli),'..');
  const sdk=await import(pathToFileURL(join(root,'node_modules/genlayer-js/dist/index.js')));
  const {testnetBradbury:chain}=await import(pathToFileURL(join(root,'node_modules/genlayer-js/dist/chains/index.js')));
  const viem=await import(pathToFileURL(join(root,'node_modules/viem/_esm/index.js')));
  ensure(same(chain.consensusMainContract.address,PINS.ConsensusMain[0]),'CLI uses an unreviewed Main');
  return {p:viem.createPublicClient({chain,transport:viem.http(rpc,{timeout:10000,retryCount:0})}),
    c:sdk.createClient({chain,endpoint:rpc}),decodeInputData:sdk.decodeInputData,decodeEventLog:viem.decodeEventLog};
}
async function main() {
  const arg=name=>{const i=process.argv.indexOf(name);return i<0?undefined:process.argv[i+1];};
  const rpc=arg('--rpc'); ensure(/^https?:\/\//.test(rpc||''),'RPC is required');
  const options={rpc,address:arg('--address'),tx:arg('--tx'),evmHash:arg('--evm-hash'),lookback:Number(arg('--lookback-blocks')||20000)};
  const source=readFileSync(arg('--source')||'build/impeach.py');
  await writeLine(json(await collectProof(options,await runtime(rpc),source)));
}
if(process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(error=>{console.error('native_finality_proof: '+error.message);process.exitCode=2;});
}
