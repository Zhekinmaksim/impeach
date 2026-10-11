// Read-only comparison of the SDK's two officially supported state selectors.
import {createClient} from '/Users/zmaxx/.nvm/versions/node/v20.20.2/lib/node_modules/genlayer/node_modules/genlayer-js/dist/index.js';
import {testnetBradbury} from '/Users/zmaxx/.nvm/versions/node/v20.20.2/lib/node_modules/genlayer/node_modules/genlayer-js/dist/chains/index.js';
const client = createClient({chain: testnetBradbury, endpoint: 'https://rpc-bradbury.genlayer.com'});
const address = '0x45F610cefF1ed367d684A1839b1801Af12Cfb038';
const report = {began_at: new Date().toISOString(), address, claim_id: 1, challenge_id: 1, views: {}};
for (const transactionHashVariant of ['latest-final', 'latest-nonfinal']) {
  const states = [];
  for (let index = 0; index < 24; index++) {
    states.push(await client.readContract({address, functionName: 'get_probe',
      args: [1n, BigInt(index)], transactionHashVariant}));
  }
  report.views[transactionHashVariant] = {at: new Date().toISOString(), states};
}
report.ended_at = new Date().toISOString();
console.log(JSON.stringify(report, (_, v) => v instanceof Map ? Object.fromEntries(v) : typeof v === 'bigint' ? v.toString() : v, 2));
