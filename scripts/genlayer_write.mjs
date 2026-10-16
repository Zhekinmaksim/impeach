#!/usr/bin/env node

/* Send a GenLayer write with native value and print its hash immediately.
 * The installed official CLI currently hard-codes value: 0n, so payable
 * contract methods need this thin SDK bridge until that CLI exposes --value.
 */

import {execFileSync} from "node:child_process";
import {dirname, join, resolve} from "node:path";
import {realpathSync, readFileSync} from "node:fs";
import {pathToFileURL} from "node:url";
import {checkedGas, TRANSACTION_GAS_CAP, causedBy} from "./gas_guard.mjs";
import {writeLine} from "./output.mjs";
import {rotationBudget, verifyRotationEncoding} from "./consensus_options.mjs";

function fail(message) {
  console.error("genlayer_write: " + message);
  process.exit(2);
}

function option(name, fallback = "") {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : fallback;
}

function required(value, name) {
  if (!value) fail("missing " + name);
  return value;
}

function coerce(value) {
  if (Array.isArray(value)) return value.map(coerce);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, coerce(v)]));
  }
  if (typeof value === "string") {
    if (/^-?\d+$/.test(value)) return BigInt(value);
    if (/^0x[0-9a-f]+$/i.test(value) && value.length > 2) return BigInt(value);
  }
  return value;
}

function parseArgs() {
  const json = option("--args-json");
  if (json) {
    try {
      return coerce(JSON.parse(json));
    } catch (error) {
      fail("invalid --args-json: " + error.message);
    }
  }
  const marker = process.argv.indexOf("--args");
  if (marker < 0) return [];
  return process.argv.slice(marker + 1).map((value) => {
    if (value === "true") return true;
    if (value === "false") return false;
    if (value === "null") return null;
    if (/^-?\d+$/.test(value)) return BigInt(value);
    return value;
  });
}

// Raw SDK reads contain BigInts and Maps. Emit exact JSON integers so Python
// keeps both small IDs and wei balances as integers, without rounding or
// changing strings that happen to contain digits or hexadecimal addresses.
function readJSON(value) {
  if (typeof value === "bigint") return value.toString();
  if (value === null || ["string", "boolean"].includes(typeof value)) return JSON.stringify(value);
  if (typeof value === "number" && Number.isFinite(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return "[" + value.map(readJSON).join(",") + "]";
  if (value instanceof Uint8Array) return JSON.stringify("0x" + Buffer.from(value).toString("hex"));
  if (value instanceof Map || (value && Object.getPrototypeOf(value) === Object.prototype)) {
    const entries = value instanceof Map ? [...value.entries()] : Object.entries(value);
    return "{" + entries.map(([key, item]) => JSON.stringify(String(key)) + ":" + readJSON(item)).join(",") + "}";
  }
  throw new Error("unsupported SDK read result type");
}

const cliEntry = realpathSync(execFileSync("which", ["genlayer"], {encoding: "utf8"}).trim());
const packageRoot = resolve(dirname(cliEntry), "..");
const sdk = await import(pathToFileURL(join(packageRoot, "node_modules/genlayer-js/dist/index.js")));
const chains = await import(pathToFileURL(join(packageRoot, "node_modules/genlayer-js/dist/chains/index.js")));

// Read-only paths exit before account configuration or keychain access.
const readIndex = process.argv.indexOf("--read");
if (readIndex >= 0) {
  if (["--receipt", "--deploy", "--appeal", "--finalize", "--process-idleness"].some(flag => process.argv.includes(flag))) {
    fail("choose only one read or transaction operation");
  }
  const readAddress = required(process.argv[readIndex + 1], "read contract address");
  const readMethod = required(process.argv[readIndex + 2], "read method");
  let args;
  try {
    args = JSON.parse(option("--args-json", "[]"));
    if (!Array.isArray(args)) throw new Error("expected an array");
  } catch (error) {
    fail("invalid --args-json: " + error.message);
  }
  const readClient = sdk.createClient({chain: chains.testnetBradbury, endpoint: option("--rpc") || undefined});
  const result = await readClient.readContract({address: readAddress, functionName: readMethod,
    args, jsonSafeReturn: false});
  await writeLine(readJSON(result));
  process.exit(0);
}

const receiptHash = option("--receipt");
if (receiptHash) {
  const client = sdk.createClient({chain: chains.testnetBradbury, endpoint: option("--rpc") || undefined});
  const receipt = await client.getTransaction({hash: receiptHash});
  await writeLine(JSON.stringify(receipt, (_key, value) => typeof value === "bigint" ? value.toString() : value));
  process.exit(0);
}

const deployPath = option("--deploy");
const appealHash = option("--appeal");
const finalizeHash = option("--finalize");
const idlenessHash = option("--process-idleness");
if ([deployPath, appealHash, finalizeHash, idlenessHash].filter(Boolean).length > 1) fail("choose only one deploy, appeal, finalize, or idleness operation");
const dryRun = process.argv.includes("--dry-run");
let rotations;
try {
  rotations = rotationBudget(option('--max-rotations', process.env.IMPEACH_CONSENSUS_MAX_ROTATIONS));
} catch (error) { fail(error.message); }
if (rotations !== undefined && (appealHash || finalizeHash || idlenessHash)) {
  fail('max rotations applies only to new application writes or deployments');
}
const [address, method] = process.argv.slice(2);
if (!deployPath && !appealHash && !finalizeHash && !idlenessHash) {
  required(address, "contract address");
  required(method, "method");
}

const configPath = resolve(process.env.GENLAYER_CONFIG || "~/.genlayer/genlayer-config.json".replace("~", process.env.HOME));
let config = {};
try { config = JSON.parse(readFileSync(configPath, "utf8")); } catch { /* use env/account fallback */ }
const accountName = option("--account", config.activeAccount || "");
let keychainPrivateKey = null;
if (accountName && !dryRun) {
  try {
    const keytarModule = await import(pathToFileURL(join(packageRoot, "node_modules/keytar/lib/keytar.js")));
    const keytar = keytarModule.default || keytarModule;
    keychainPrivateKey = await keytar.getPassword("genlayer-cli", "account:" + accountName);
  } catch {
    keychainPrivateKey = null;
  }
}
const privateKey = dryRun ? null : process.env.GENLAYER_PRIVATE_KEY || keychainPrivateKey;
if (!privateKey && !dryRun) {
  fail("no unlocked private key; run `genlayer account unlock --account " + (accountName || "<name>") + "`");
}

const dryRunComplete = new Error("DRY_RUN_COMPLETE");
const from = option("--from");
if (dryRun && !/^0x[0-9a-fA-F]{40}$/.test(from)) fail("--dry-run requires --from <public account address>");
const signer = dryRun ? {address: from, type: "local"} : sdk.createAccount(privateKey);
const gasCap = BigInt(option("--gas-cap", TRANSACTION_GAS_CAP.toString()));
const account = {
  ...signer,
  async signTransaction(tx) {
    let consensus = {};
    if (rotations !== undefined) {
      const {decodeFunctionData} = await import(pathToFileURL(join(packageRoot, "node_modules/viem/_esm/index.js")));
      consensus = verifyRotationEncoding(decodeFunctionData({
        abi: chains.testnetBradbury.consensusMainContract.abi, data: tx.data,
      }), rotations, chains.testnetBradbury.defaultNumberOfInitialValidators);
    }
    const gas = await checkedGas(tx, (request) => client.request(request), {
      chainId: chains.testnetBradbury.id,
      consensusAddress: chains.testnetBradbury.consensusMainContract.address,
      gasCap,
    });
    const report = {from: signer.address, to: tx.to, chainId: tx.chainId,
      sdkEstimate: tx.gas.toString(), boundedEstimate: gas.estimate.toString(),
      gasLimit: gas.gas.toString(), gasCap: gas.cap.toString(),
      calldataBytes: (tx.data.length - 2) / 2, dryRun, ...consensus};
    if (dryRun) {
      console.log(JSON.stringify(report, null, 2));
      throw dryRunComplete;
    }
    console.error("Gas preflight:", JSON.stringify(report));
    return signer.signTransaction({...tx, gas: gas.gas});
  },
};
const client = sdk.createClient({
  chain: chains.testnetBradbury,
  endpoint: option("--rpc") || undefined,
  account,
});
const value = BigInt(option("--value", "0"));
try {
  if (idlenessHash) {
    if (!/^0x[0-9a-fA-F]{64}$/.test(idlenessHash)) fail("invalid idleness transaction hash");
    if (value !== 0n) fail("idleness processing cannot send native value");
    const receipt = await client.getTransaction({hash: idlenessHash});
    if (!["UNDETERMINED", "LEADER_TIMEOUT", "VALIDATORS_TIMEOUT", "READY_TO_FINALIZE"].includes(receipt.statusName)) {
      fail("idleness processing requires a known projected timeout or finalization phase");
    }
    // Verified live v0.5 ConsensusMain exposes this permissionless method.
    // It commits deferred timeout outcomes and maintains the native queues;
    // it neither submits a new intelligent-contract call nor forces a verdict.
    const {encodeFunctionData} = await import(pathToFileURL(join(packageRoot, "node_modules/viem/_esm/index.js")));
    const data = encodeFunctionData({abi: [{type: "function", name: "processIdleness",
      stateMutability: "nonpayable", inputs: [{name: "txId", type: "bytes32"}], outputs: []}],
      functionName: "processIdleness", args: [idlenessHash]});
    // checkedGas estimates and simulates this exact method before any signing.
    const hash = await client.sendTransaction({account, to: chains.testnetBradbury.consensusMainContract.address,
      data, value: 0n});
    await writeLine("Idleness EVM transaction: " + hash);
    process.exit(0);
  }
  if (finalizeHash) {
    if (!/^0x[0-9a-fA-F]{64}$/.test(finalizeHash)) fail("invalid finalization transaction hash");
    const receipt = await client.getTransaction({hash: finalizeHash});
    if (receipt.statusName === "FINALIZED") fail("transaction is already finalized; no duplicate finalization sent");
    if (!["ACCEPTED", "UNDETERMINED", "LEADER_TIMEOUT", "VALIDATORS_TIMEOUT", "READY_TO_FINALIZE"].includes(receipt.statusName)) {
      fail("transaction has no decided outcome to finalize");
    }
    // The bounded gas simulation also checks the network's finalization window.
    const hash = await client.finalizeTransaction({account, txId: finalizeHash});
    console.log("Finalization EVM transaction:", hash);
    process.exit(0);
  }
  if (appealHash) {
    if (!/^0x[0-9a-fA-F]{64}$/.test(appealHash)) fail("invalid appeal transaction hash");
    const receipt = await client.getTransaction({hash: appealHash});
    // Verified Bradbury v0.5 Appeals.submitAppeal also supports ValidatorsTimeout
    // through a validator appeal. Gas simulation enforces the stored phase and
    // queue timing; the projected receipt name alone never authorizes signing.
    if (!["LEADER_TIMEOUT", "UNDETERMINED", "VALIDATORS_TIMEOUT"].includes(receipt.statusName)) {
      fail("only a confirmed timeout or undetermined round can be appealed with this helper");
    }
    const bond = await client.getMinAppealBond({txId: appealHash});
    // This recovery path is deliberately limited to zero-bond testnet appeals.
    if (bond !== 0n) fail("appeal requires a nonzero bond; inspect it before proceeding");
    await client.appealTransaction({account, txId: appealHash, value: 0n});
    console.log("Appealed original transaction:", appealHash);
    process.exit(0);
  }
  const consensusOptions = rotations === undefined ? {} : {consensusMaxRotations: rotations};
  const hash = deployPath
    ? await client.deployContract({account, code: readFileSync(resolve(deployPath), "utf8"), args: parseArgs(), ...consensusOptions})
    : await client.writeContract({account, address, functionName: method, args: parseArgs(), value, ...consensusOptions});
  console.log("Transaction Hash:", hash);
} catch (error) {
  if (!causedBy(error, dryRunComplete)) throw error;
}
