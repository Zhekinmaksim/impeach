#!/usr/bin/env node
// Read-only Bradbury v0.5 inspection. No account, keychain or signing imports.
// Pins/ABIs: verified deployment audit runs/v2-native-status-audit.json;
// official genlayer-networks f9a30ed9536e56255cd2d7f8579a4d5dcc81ffd0,
// bradbury/testnet_deployments.json, release v0.5:9c68608.
import {execFileSync} from "node:child_process";
import {createHash} from "node:crypto";
import {readFileSync, realpathSync} from "node:fs";
import {dirname, join, resolve} from "node:path";
import {pathToFileURL} from "node:url";
import {writeLine} from "./output.mjs";

export const SLOT = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc";
export const PINS = {
  AddressManager: ["0x8aCE036C8C3C5D603dB546b031302FCf149648E8", "0xf63f3a95FBf2e97618A5E3eA0ffF63024915f3e6"],
  ConsensusMain: ["0x0112Bf6e83497965A5fdD6Dad1E447a6E004271D", "0x0a2C393975dA79505ED930eFC55ae4AEB88b0d62"],
  ConsensusData: ["0x85D7bf947A512Fc640C75327A780c90847267697", "0x7EE629530e70E2a3A772F8522d8835060aBf0755"],
  FinalizationPhase: ["0x7de0FF58B401F2D800470e4390e24fF2bAa02AaE", "0x3Ab63c1fC784682ef72276a76E2AD8fc1C5813b2"],
  IdlenessPhase: ["0xCC40228B46FF76112CC172C7DE3384E006FC3935", "0x2cf61473CaFcF47AdC0DdD861290a7e848881446"],
  Idleness: ["0x4A0887eA79c6447ABf8577770CF24B005c0aaF45", "0x4e696416634012119187D8dDa6a56E66aC7cb23d"],
  TransactionManager: ["0x1D301aCEf55EAf7df5D3741659d426f51061Ec8d", "0xeEe45073F7EEb3b80D1973F8398f8e508f893f9C"],
  Queues: ["0x56a05a9bB7B261ad720020a08B9Fd5A13177b949", "0x7559EBDBC6F59e5dd2a048a1A1539aC14BF93DB0"],
};
export const HEADS = ["getFinalizedHeadTxId", "getPendingHeadTxId", "getAcceptedHeadTxId", "getUndeterminedHeadTxId"];
const field = (name, type) => ({name, type});
const tuple = (names, type = "uint256") => names.split(" ").map(name => field(name, type));
const view = (name, inputs, outputs) => ({type: "function", name, stateMutability: "view", inputs, outputs});
const TX_FIELDS = [
  ...tuple("result txExecutionResult previousStatus status", "uint8"),
  ...tuple("txOrigin sender recipient activator", "address"),
  ...tuple("txSlot initialRotations numOfInitialValidators epoch"),
  ...tuple("id randomSeed txExecutionHash resultHash", "bytes32"),
  ...tuple("txCalldata eqBlocksOutputs", "bytes"),
  {name: "readStateBlockRanges", type: "tuple[]", components: tuple("activationBlock processingBlock proposalBlock")},
  ...tuple("validUntil value lockedStorageUnitPrice storageFeeUsed"),
];
const TIMESTAMPS = tuple("created pending activated proposed committed lastVote appealSubmitted leaderRevealed");
const TIMEOUTS = tuple("activate propose commit reveal accept leaderReveal");
const ABI = [
  view("addressManager", [], [field("", "address")]),
  view("VERSION", [], [field("", "string")]),
  view("getAddressNonZero", [field("key", "string")], [field("", "address")]),
  view("getTransaction", [field("txId", "bytes32")], [{name: "", type: "tuple", components: TX_FIELDS}]),
  ...HEADS.map(name => view(name, [field("recipient", "address")], [field("", "bytes32")])),
  view("getTxQueueType", [field("recipient", "address"), field("txId", "bytes32")], [field("", "uint8")]),
  view("isAtFinalizedQueueHead", [field("recipient", "address"), field("txId", "bytes32")], [field("", "bool")]),
  view("getLastQueueModification", [field("txId", "bytes32")], [{name: "", type: "tuple", components: [field("lastQueueType", "uint8"), field("lastQueueTimestamp", "uint256")]}]),
  view("getTimeouts", [], [{name: "", type: "tuple", components: TIMEOUTS}]),
  view("getTimestamps", [field("txId", "bytes32")], [{name: "", type: "tuple", components: TIMESTAMPS}]),
  view("checkFirstSlotElapsed", [field("txId", "bytes32"), field("status", "uint8")], [field("", "bool")]),
  view("canFinalize", [field("txId", "bytes32"), field("now", "uint256")], [field("", "bool"), field("", "uint256"), field("", "uint256")]),
];
const same = (a, b) => typeof a === "string" && a.toLowerCase() === b.toLowerCase();
const hash = value => createHash("sha256").update(value).digest("hex");
export const json = value => JSON.stringify(value, (_, v) => v instanceof Map ? Object.fromEntries(v) : typeof v === "bigint" ? v.toString() : v);

export async function verifyProtocol(p, blockNumber) {
  if (await p.getChainId() !== 4221) throw new Error("RPC is not Bradbury chain 4221");
  const call = (name, functionName, args = []) => p.readContract({address: PINS[name][0], abi: ABI, functionName, args, blockNumber});
  const implementations = {};
  await Promise.all(Object.entries(PINS).map(async ([name, [address, expected]]) => {
    const raw = await p.getStorageAt({address, slot: SLOT, blockNumber});
    if (!/^0x[0-9a-fA-F]{64}$/.test(raw || "") || !same("0x" + raw.slice(-40), expected)) {
      throw new Error("unreviewed active implementation: " + name);
    }
    implementations[name] = "0x" + raw.slice(-40);
  }));
  const manager = await call("ConsensusMain", "addressManager");
  if (!same(manager, PINS.AddressManager[0])) throw new Error("unreviewed Main address manager");
  // Timers come from Main's registry, never from ConsensusData's projected clock.
  await Promise.all(Object.keys(PINS).filter(name => name !== "AddressManager").map(async name => {
    const actual = await call("AddressManager", "getAddressNonZero", [name]);
    if (!same(actual, PINS[name][0])) throw new Error("unreviewed Main registry pointer: " + name);
  }));
  for (const name of ["FinalizationPhase", "IdlenessPhase"]) {
    if (!same(await call(name, "addressManager"), manager)) throw new Error("phase uses a different Main registry: " + name);
  }
  const version = await call("ConsensusMain", "VERSION");
  if (version !== "2.0.0") throw new Error("unreviewed Main version");
  return {chainId: 4221, main: PINS.ConsensusMain[0], manager, version, implementations,
    sourceCommit: "9c686087963551277fc2dce0354c2b1a7050b4b2"};
}

export async function inspectQueue(options, {p, c, decodeInputData}, localSource) {
  if (!/^0x[0-9a-fA-F]{40}$/.test(options.address)) throw new Error("invalid court address");
  const block = await p.getBlock();
  const blockNumber = block.number;
  const protocol = await verifyProtocol(p, blockNumber);
  const remoteSource = await c.getContractCode(options.address);
  if (typeof remoteSource !== "string" || hash(remoteSource) !== hash(localSource)) throw new Error("deployed court source differs from --source");
  const read = (name, functionName, args = []) => p.readContract({address: PINS[name][0], abi: ABI, functionName, args, blockNumber});
  const heads = Object.fromEntries(await Promise.all(HEADS.map(async name => [name, await read("Queues", name, [options.address])])));
  const ids = [...new Set([...Object.values(heads), ...(options.tx ? [options.tx] : [])])].filter(tx => !/^0x0+$/.test(tx));
  if (ids.some(tx => !/^0x[0-9a-fA-F]{64}$/.test(tx))) throw new Error("malformed queue head");
  const mainTimeouts = await read("Idleness", "getTimeouts");
  const transactions = await Promise.all(ids.map(async tx => {
    const [stored, receipt, mainTimestamps, queueType, queueModification, atFinalizedHead, canFinalize] = await Promise.all([
      read("TransactionManager", "getTransaction", [tx]), c.getTransaction({hash: tx}),
      read("Idleness", "getTimestamps", [tx]), read("Queues", "getTxQueueType", [options.address, tx]),
      read("Queues", "getLastQueueModification", [tx]), read("Queues", "isAtFinalizedQueueHead", [options.address, tx]),
      read("ConsensusData", "canFinalize", [tx, block.timestamp]),
    ]);
    if (!same(stored.recipient, options.address) || !same(receipt.recipient, options.address) || !same(stored.id, tx)) {
      throw new Error("queue transaction belongs to another court/hash");
    }
    const firstSlotElapsed = [1, 2, 3, 4, 9, 10, 14].includes(Number(stored.status))
      ? await read("Idleness", "checkFirstSlotElapsed", [tx, stored.status]) : false;
    const decoded = decodeInputData(stored.txCalldata, options.address);
    return {tx, stored, receipt, decoded, mainTimestamps, firstSlotElapsed, queueType, queueModification, atFinalizedHead, canFinalize};
  }));
  return {at: Date.now(), address: options.address, blockNumber, blockTimestamp: block.timestamp,
    protocol, sourceSha256: hash(localSource), mainTimeouts, heads, transactions};
}

async function runtime(rpc) {
  const cli = realpathSync(execFileSync("which", ["genlayer"], {encoding: "utf8"}).trim());
  const root = resolve(dirname(cli), "..");
  const sdk = await import(pathToFileURL(join(root, "node_modules/genlayer-js/dist/index.js")));
  const {testnetBradbury: chain} = await import(pathToFileURL(join(root, "node_modules/genlayer-js/dist/chains/index.js")));
  const {createPublicClient, http} = await import(pathToFileURL(join(root, "node_modules/viem/_esm/index.js")));
  if (!same(chain.consensusMainContract.address, PINS.ConsensusMain[0])) throw new Error("CLI SDK uses another Main address");
  return {p: createPublicClient({chain, transport: http(rpc, {timeout: 15000, retryCount: 0})}),
    c: sdk.createClient({chain, endpoint: rpc}), decodeInputData: sdk.decodeInputData};
}

async function main() {
  const option = name => { const i = process.argv.indexOf(name); return i < 0 ? undefined : process.argv[i + 1]; };
  const rpc = option("--rpc");
  if (!rpc || !/^https?:\/\//.test(rpc)) throw new Error("--rpc is required");
  const deps = await runtime(rpc);
  const evm = option("--evm-receipt");
  if (evm) {
    if (!/^0x[0-9a-fA-F]{64}$/.test(evm)) throw new Error("invalid EVM transaction hash");
    const block = await deps.p.getBlock();
    await verifyProtocol(deps.p, block.number);
    const receipt = await deps.p.waitForTransactionReceipt({hash: evm, timeout: 45000, pollingInterval: 2000});
    const transaction = await deps.p.getTransaction({hash: evm});
    if (!same(transaction.to, PINS.ConsensusMain[0]) || transaction.value !== 0n) throw new Error("unexpected EVM operation destination/value");
    await writeLine(json({receipt, transaction}));
    return;
  }
  const options = {rpc, address: option("--address"), tx: option("--tx")};
  if (options.tx && !/^0x[0-9a-fA-F]{64}$/.test(options.tx)) throw new Error("invalid native transaction hash");
  const source = readFileSync(option("--source") || "build/impeach.py");
  await writeLine(json(await inspectQueue(options, deps, source)));
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(error => { console.error("inspect_queue: " + error.message); process.exitCode = 2; });
}
