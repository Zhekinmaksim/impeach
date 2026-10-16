import assert from 'node:assert/strict';
import test from 'node:test';
import {rotationBudget, verifyRotationEncoding} from '../scripts/consensus_options.mjs';

test('rotation override is bounded and leaves the SDK default untouched when absent', () => {
  assert.equal(rotationBudget(undefined), undefined);
  assert.equal(rotationBudget(''), undefined);
  assert.equal(rotationBudget('7'), 7);
  for (const value of ['0', '8', '-1', '1.5', '1e3', ' 7', '07', 'NaN', 7]) {
    assert.throws(() => rotationBudget(value));
  }
});

test('decoded calldata must change rotations without changing the five-validator committee', () => {
  const decoded = {functionName: 'addTransaction', args: ['sender', 'court', 5n, 7n, '0x']};
  assert.deepEqual(verifyRotationEncoding(decoded, 7, 5), {initialValidators: 5, consensusMaxRotations: 7});
  assert.deepEqual(verifyRotationEncoding({...decoded, args: [...decoded.args, 1792140000n]}, 7, 5),
    {initialValidators: 5, consensusMaxRotations: 7});
  for (const invalid of [
    {...decoded, args: ['sender', 'court', 7n, 5n, '0x']},
    {...decoded, args: ['sender', 'court', 5n, 3n, '0x']},
    {...decoded, args: [...decoded.args, 0n]},
    {...decoded, args: [...decoded.args, 'unexpected']},
    {...decoded, args: [...decoded.args, 1792140000n, 1n]},
    {...decoded, functionName: 'submitAppeal'},
    {...decoded, args: undefined},
  ]) assert.throws(() => verifyRotationEncoding(invalid, 7, 5));
});
