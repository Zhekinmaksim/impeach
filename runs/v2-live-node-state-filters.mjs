// Read-only diagnostics for current documented gen_call status/block filters.
// The deployed legacy node may reject/ignore new filters; retain raw responses.
import {abi} from '/Users/zmaxx/.nvm/versions/node/v20.20.2/lib/node_modules/genlayer/node_modules/genlayer-js/dist/index.js';
import {fromHex} from '/Users/zmaxx/.nvm/versions/node/v20.20.2/lib/node_modules/genlayer/node_modules/viem/_esm/index.js';
const url = 'https://rpc-bradbury.genlayer.com';
const rpc = async (method, params) => {
  const request = {jsonrpc: '2.0', id: 1, method, params};
  const response = await fetch(url, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(request), signal: AbortSignal.timeout(30000)});
  return {request, http_status: response.status, response: await response.json()};
};
const report = {source: 'https://docs.genlayer.com/api-references/genlayer-node#gen_call',
  began_at: new Date().toISOString(), note: 'Read-only probes of documented filters; compatibility is not assumed.', reads: []};
report.block = await rpc('eth_blockNumber', []);
const blockNumber = report.block.response.result;
if (!/^0x[0-9a-f]+$/i.test(blockNumber || '')) throw new Error('invalid public block number');
const data = abi.transactions.serialize([abi.calldata.encode(abi.calldata.makeCalldataObject('get_probe', [1n, 14n], undefined)), false]);
const base = {type: 'read', to: '0x45F610cefF1ed367d684A1839b1801Af12Cfb038', from: '0x0000000000000000000000000000000000000000', data};
for (const filter of [{transaction_hash_variant: 'latest-final'}, {transaction_hash_variant: 'latest-nonfinal'},
    {status: 'accepted'}, {status: 'finalized'}, {status: 'accepted', blockNumber}, {status: 'finalized', blockNumber}]) {
  const record = await rpc('gen_call', [{...base, ...filter}]);
  record.at = new Date().toISOString();
  const result = record.response.result;
  try {
    if (record.response.error) throw new Error('RPC error retained');
    if (result?.status && result.status.code !== 0) throw new Error(result.status.message);
    const hex = typeof result === 'string' ? result : result?.data;
    if (typeof hex !== 'string') throw new Error('missing encoded return');
    record.decoded = abi.calldata.decode(fromHex(hex.startsWith('0x') ? hex : '0x' + hex, 'bytes'));
  } catch (error) { record.decode_error = error.message; }
  report.reads.push(record);
}
report.ended_at = new Date().toISOString();
console.log(JSON.stringify(report, (_, v) => v instanceof Map ? Object.fromEntries(v) : typeof v === 'bigint' ? v.toString() : v, 2));
