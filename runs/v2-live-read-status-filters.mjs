// Public read-only comparison. No wallet, signing, writes, or provider calls.
import {writeFileSync} from 'node:fs';
import {abi, createClient} from '/Users/zmaxx/.nvm/versions/node/v20.20.2/lib/node_modules/genlayer/node_modules/genlayer-js/dist/index.js';
import {testnetBradbury} from '/Users/zmaxx/.nvm/versions/node/v20.20.2/lib/node_modules/genlayer/node_modules/genlayer-js/dist/chains/index.js';
const client=createClient({chain:testnetBradbury,endpoint:'https://rpc-bradbury.genlayer.com'});
const address='0x45F610cefF1ed367d684A1839b1801Af12Cfb038';
const report={began_at:new Date().toISOString(),address,
  docs:'https://docs.genlayer.com/api-references/genlayer-node',
  caution:'Current docs describe a newer protocol. Results retain request parameters; an ignored selector cannot prove a separate state version.',observations:[]};
const replacer=(_,v)=>v instanceof Map?Object.fromEntries(v):typeof v==='bigint'?v.toString():v;
for(const index of [14,23]){
  const data=abi.transactions.serialize([abi.calldata.encode(abi.calldata.makeCalldataObject('get_probe',[1n,BigInt(index)])),false]);
  for(const selector of [{status:'accepted'},{status:'finalized'},
    {transaction_hash_variant:'latest-final'},{transaction_hash_variant:'latest-nonfinal'}]){
    const params={type:'read',to:address,from:'0x0000000000000000000000000000000000000000',data,...selector};
    const observation={at:new Date().toISOString(),index,params};
    try{
      const raw=await client.request({method:'gen_call',params:[params]});observation.raw=raw;
      const hex=typeof raw==='string'?raw:raw.data;
      if(typeof raw==='object'&&raw.status?.code!==0)throw new Error(raw.status?.message||'gen_call error');
      observation.decoded=abi.calldata.decode(new Uint8Array(Buffer.from(hex.replace(/^0x/,''),'hex')));
    }catch(e){observation.error=e.message;}
    report.observations.push(observation);
  }
}
report.ended_at=new Date().toISOString();
const out=process.argv[2];if(!out)throw new Error('output path required');
writeFileSync(out,JSON.stringify(report,replacer,2)+'\n');
console.log(JSON.stringify(report.observations.map(o=>({index:o.index,status:o.params.status,variant:o.params.transaction_hash_variant,C2:o.decoded instanceof Map?o.decoded.get('stage_c2'):o.decoded?.stage_c2,error:o.error})),null,2));
