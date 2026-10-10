import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {test} from 'node:test';

test('a large receipt reaches a Python/CLI pipe intact before process exit', () => {
  const moduleUrl = new URL('../scripts/output.mjs', import.meta.url).href;
  const code = `import {writeLine} from ${JSON.stringify(moduleUrl)}; await writeLine(JSON.stringify({body:'x'.repeat(250000), tail:'complete'})); process.exit(0);`;
  const result = spawnSync(process.execPath, ['--input-type=module','-e',code], {encoding:'utf8',maxBuffer:300000});
  assert.equal(result.status,0,result.stderr);
  const receipt=JSON.parse(result.stdout);
  assert.equal(receipt.body.length,250000);
  assert.equal(receipt.tail,'complete');
});
