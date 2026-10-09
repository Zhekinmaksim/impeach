#!/usr/bin/env node

/* Send a GenLayer write with native value and print its hash immediately.
 * The installed official CLI currently hard-codes value: 0n, so payable
 * contract methods need this thin SDK bridge until that CLI exposes --value.
 */

import {execFileSync} from "node:child_process";
import {dirname, join, resolve} from "node:path";
import {realpathSync, readFileSync} from "node:fs";
import {pathToFileURL} from "node:url";
import {checkedGas, TRANSACTION_GAS_CAP} from "./gas_guard.mjs";

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

const cliEntry = realpathSync(execFileSync("which", ["genlayer"], {encoding: "utf8"}).trim());
const packageRoot = resolve(dirname(cliEntry), "..");
const sdk = await import(pathToFileURL(join(packageRoot, "node_modules/genlayer-js/dist/index.js")));
const chains = await import(pathToFileURL(join(packageRoot, "node_modules/genlayer-js/dist/chains/index.js")));

// Receipt reads never unlock an account or touch the keychain.
const receiptHash = option("--receipt");
if (receiptHash) {
  const client = sdk.createClient({chain: chains.testnetBradbury, endpoint: option("--rpc") || undefined});
  const receipt = await client.getTransaction({hash: receiptHash});
  console.log(JSON.stringify(receipt, (_key, value) => typeof value === "bigint" ? value.toString() : value));
  process.exit(0);
}

const deployPath = option("--deploy");
const dryRun = process.argv.includes("--dry-run");
const [address, method] = process.argv.slice(2);
if (!deployPath) {
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
    const gas = await checkedGas(tx, (request) => client.request(request), {
      chainId: chains.testnetBradbury.id,
      consensusAddress: chains.testnetBradbury.consensusMainContract.address,
      gasCap,
    });
    const report = {from: signer.address, to: tx.to, chainId: tx.chainId,
      sdkEstimate: tx.gas.toString(), boundedEstimate: gas.estimate.toString(),
      gasLimit: gas.gas.toString(), gasCap: gas.cap.toString(),
      calldataBytes: (tx.data.length - 2) / 2, dryRun};
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
  const hash = deployPath
    ? await client.deployContract({account, code: readFileSync(resolve(deployPath), "utf8"), args: parseArgs()})
    : await client.writeContract({account, address, functionName: method, args: parseArgs(), value});
  console.log("Transaction Hash:", hash);
} catch (error) {
  if (error !== dryRunComplete) throw error;
}
