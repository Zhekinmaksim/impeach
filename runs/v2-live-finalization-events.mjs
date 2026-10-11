// Read-only canonical evidence for the two accepted transaction finalizations.
import {createPublicClient,http} from '/Users/zmaxx/.nvm/versions/node/v20.20.2/lib/node_modules/genlayer/node_modules/viem/_esm/index.js';
import {testnetBradbury} from '/Users/zmaxx/.nvm/versions/node/v20.20.2/lib/node_modules/genlayer/node_modules/genlayer-js/dist/chains/index.js';
import {EVENT} from '../scripts/native_finality_proof.mjs';
import {PINS,json,verifyProtocol} from '../scripts/inspect_queue.mjs';
const client=createPublicClient({chain:testnetBradbury,transport:http('https://rpc-bradbury.genlayer.com',{timeout:30000,retryCount:0})});
const tip=await client.getBlock();
const report={at:new Date().toISOString(),tip,protocol:await verifyProtocol(client,tip.number),items:[]};
for(const txId of ['0xa264c36846db3a8a567d3e493ceadfd3ff30d1582aa6f573fe7d42d701ccb40c',
                   '0xcedffa69c57e1b3b42dc91ec2f4921b5d43de2a0ca05841382df34aa2f752a54']){
  const logs=[];
  for(let end=tip.number; end>tip.number-4000n; end-=1000n){
    logs.push(...await client.getLogs({address:PINS.FinalizationPhase[0],event:EVENT,args:{txId},fromBlock:end-999n,toBlock:end,strict:true}));
  }
  if(logs.length!==1)throw Error('expected exactly one finalization event '+txId);
  const log=logs[0];
  const receipt=await client.getTransactionReceipt({hash:log.transactionHash});
  const transaction=await client.getTransaction({hash:log.transactionHash});
  const block=await client.getBlock({blockNumber:log.blockNumber});
  if(log.removed||block.hash!==log.blockHash||receipt.blockHash!==block.hash||receipt.status!=='success')throw Error('noncanonical or failed finalization');
  report.items.push({txId,log,receipt,transaction,block});
}
console.log(json(report));
