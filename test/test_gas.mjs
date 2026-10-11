import assert from "node:assert/strict";
import test from "node:test";
import {checkedGas, TRANSACTION_GAS_CAP, causedBy} from "../scripts/gas_guard.mjs";

const address = "0x" + "1".repeat(40);
const tx = {chainId: 4221, to: address, account: {address}, data: "0x1234", value: 0n};
const options = {chainId: 4221, consensusAddress: address};
const mockRpc = (overrides = {}, calls = []) => async (request) => {
  calls.push(request);
  if (request.method in overrides) return overrides[request.method](request);
  return {eth_chainId: "0x107d", eth_getBlockByNumber: {gasLimit: "0x5f5e100"},
    eth_estimateGas: "0x989680", eth_call: "0x"}[request.method];
};

test("recognizes only the identical dry-run sentinel through viem wrappers", () => {
  const stop = new Error("DRY_RUN_COMPLETE");
  assert.equal(causedBy(stop, stop), true);
  assert.equal(causedBy(new Error("wrapped", {cause: new Error("inner", {cause: stop})}), stop), true);
  assert.equal(causedBy(new Error("DRY_RUN_COMPLETE"), stop), false);
  assert.equal(causedBy(new Error("RPC reverted", {cause: new Error("DRY_RUN_COMPLETE")}), stop), false);
  const cycle = new Error("unrelated"); cycle.cause = cycle;
  assert.equal(causedBy(cycle, stop), false);
});

test("bounds the estimate, adds margin, and simulates the exact selected gas", async () => {
  const calls = [];
  const result = await checkedGas(tx, mockRpc({}, calls), options);
  assert.equal(result.gas, 11_000_000n);
  assert.equal(calls.find(x => x.method === "eth_estimateGas").params[0].gas, "0x1000000");
  assert.equal(calls.find(x => x.method === "eth_call").params[0].gas, "0xa7d8c0");
});

test("does not exceed the transaction cap when adding margin", async () => {
  const result = await checkedGas(tx, mockRpc({eth_estimateGas: () => "0xf42400"}), options);
  assert.equal(result.gas, TRANSACTION_GAS_CAP);
});

test("refuses an oversized estimate instead of silently truncating it", async () => {
  await assert.rejects(checkedGas(tx, mockRpc({eth_estimateGas: () => "0x2faf080"}), options), /exceeds/);
});

test("refuses a failed simulation", async () => {
  await assert.rejects(checkedGas(tx, mockRpc({eth_call: () => {throw new Error("revert");}}), options), /revert/);
});

test("refuses the wrong chain and an override above the protocol cap", async () => {
  await assert.rejects(checkedGas(tx, mockRpc({eth_chainId: () => "0x1"}), options), /chain id/);
  await assert.rejects(checkedGas(tx, mockRpc(), {...options, gasCap: 50_000_000n}), /gas cap/);
});
