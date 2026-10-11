// Bradbury enforces the EIP-7825 per-transaction cap even though its block cap
// is larger. An unconstrained eth_estimateGas result can exceed this limit.
export const TRANSACTION_GAS_CAP = 16_777_216n;

// viem may wrap a deliberate stop in TransactionExecutionError. Compare the
// original object, never its message; real RPC and simulation errors propagate.
export function causedBy(error, expected) {
  const seen = new Set();
  while (error && typeof error === "object" && !seen.has(error)) {
    if (error === expected) return true;
    seen.add(error);
    error = error.cause;
  }
  return false;
}

export async function checkedGas(tx, rpc, {chainId, consensusAddress, gasCap = TRANSACTION_GAS_CAP}) {
  if (gasCap <= 0n || gasCap > TRANSACTION_GAS_CAP) throw new Error("gas cap must be in 1..16777216");
  if (tx.chainId !== chainId || tx.to.toLowerCase() !== consensusAddress.toLowerCase()) {
    throw new Error("transaction does not match the configured Bradbury chain and consensus contract");
  }
  const [rpcChainId, block] = await Promise.all([
    rpc({method: "eth_chainId", params: []}),
    rpc({method: "eth_getBlockByNumber", params: ["latest", false]}),
  ]);
  if (Number(BigInt(rpcChainId)) !== chainId) throw new Error("RPC chain id does not match Bradbury");
  const blockCap = BigInt(block.gasLimit);
  const cap = gasCap < blockCap ? gasCap : blockCap;
  const request = {
    from: tx.account.address, to: tx.to, data: tx.data,
    value: "0x" + (tx.value || 0n).toString(16), gas: "0x" + cap.toString(16),
  };
  // Failure is fatal: never fall back to an arbitrary gas limit or send a
  // transaction whose bounded simulation could not execute successfully.
  const estimate = BigInt(await rpc({method: "eth_estimateGas", params: [request]}));
  if (estimate <= 0n || estimate > cap) throw new Error("gas estimate exceeds the transaction cap");
  const buffered = (estimate * 110n + 99n) / 100n;
  const gas = buffered < cap ? buffered : cap;
  await rpc({method: "eth_call", params: [{...request, gas: "0x" + gas.toString(16)}, "latest"]});
  return {gas, estimate, cap};
}
