#!/usr/bin/env node
// Use the installed official CLI to create/unlock an independent test account.
// Passwords travel only through process memory/stdin and the OS keychain.
// Default invocation is a plan; --execute is required for account creation.

import {execFileSync, spawn} from "node:child_process";
import {randomBytes} from "node:crypto";
import {chmodSync, existsSync, readFileSync, realpathSync} from "node:fs";
import {dirname, join, resolve} from "node:path";
import {homedir} from "node:os";
import {pathToFileURL} from "node:url";

const option = (name, fallback = "") => {
  const index = process.argv.indexOf(name);
  return index < 0 ? fallback : process.argv[index + 1];
};
const name = option("--name", "impeach-challenger");
if (!/^[a-z][a-z0-9-]{0,63}$/.test(name)) throw new Error("invalid account name");
if (process.argv.includes("--help") || !process.argv.includes("--execute")) {
  console.log(`Creates ${name} with the official CLI, preserves the active account, and unlocks it in OS Keychain.`);
  console.log("Usage: node scripts/prepare_challenger.mjs --name impeach-challenger --execute");
  console.log("No account is created without --execute. This script never funds an account.");
  process.exit(0);
}

const cliEntry = realpathSync(execFileSync("which", ["genlayer"], {encoding: "utf8"}).trim());
const cliRoot = resolve(dirname(cliEntry), "..");
const cliPackage = JSON.parse(readFileSync(join(cliRoot, "package.json"), "utf8"));
if (cliPackage.version !== "0.39.1") throw new Error("Review password prompt handling before using another CLI version");
const configPath = join(homedir(), ".genlayer", "genlayer-config.json");
const keystorePath = join(homedir(), ".genlayer", "keystores", name + ".json");
if (existsSync(keystorePath)) throw new Error("account already exists; refusing to overwrite it");
const before = JSON.parse(readFileSync(configPath, "utf8"));
if (!before.activeAccount) throw new Error("select the publisher account before creating the challenger");
const keytarModule = await import(pathToFileURL(join(cliRoot, "node_modules/keytar/lib/keytar.js")));
const keytar = keytarModule.default || keytarModule;
const recoveryService = "impeach-testnet";
const recoveryAccount = "keystore-password:" + name;
if (await keytar.getPassword(recoveryService, recoveryAccount)) {
  throw new Error("a recovery password already exists; inspect it before retrying account creation");
}

// CLI 0.39.1 uses this exact external Inquirer ESM singleton for password
// prompts. Feed only password questions in the child; reject every other
// prompt. The official create/unlock actions still perform all cryptography,
// keystore writes, and private-key caching themselves.
const inquirerRoot = join(cliRoot, "node_modules/inquirer");
const inquirerPackage = JSON.parse(readFileSync(join(inquirerRoot, "package.json"), "utf8"));
const inquirerPath = join(inquirerRoot, inquirerPackage.exports["."].import.default);
const childCode = `
import {pathToFileURL} from 'node:url';
let input = '';
for await (const chunk of process.stdin) input += chunk;
const payload = JSON.parse(input);
const inquirer = (await import(pathToFileURL(payload.inquirerPath))).default;
inquirer.prompt = async (questions) => {
  const result = {};
  for (const question of questions) {
    if (question.type !== 'password' || question.name !== 'password') throw new Error('Unexpected CLI prompt');
    result.password = payload.password;
  }
  return result;
};
process.argv = ['node', payload.cliEntry, ...payload.args];
await import(pathToFileURL(payload.cliEntry));
`;

async function cli(args, password) {
  await new Promise((resolvePromise, reject) => {
    const child = spawn(process.execPath, ["--input-type=module", "-e", childCode], {
      stdio: ["pipe", "ignore", "ignore"], timeout: 180000,
    });
    child.on("error", () => reject(new Error("official CLI process could not start")));
    child.stdin.on("error", () => reject(new Error("official CLI input failed")));
    child.on("exit", code => code === 0 ? resolvePromise() : reject(new Error("official CLI account action failed; recovery password remains in OS Keychain")));
    child.stdin.end(JSON.stringify({cliEntry, inquirerPath, args, password}));
  });
}

const password = randomBytes(32).toString("base64url");
await keytar.setPassword(recoveryService, recoveryAccount, password);
await cli(["account", "create", "--name", name, "--no-set-active"], password);
if (!existsSync(keystorePath)) throw new Error("CLI did not produce an encrypted keystore");
chmodSync(keystorePath, 0o600);
const keystore = JSON.parse(readFileSync(keystorePath, "utf8"));
if (!keystore.Crypto && !keystore.crypto) throw new Error("keystore is not encrypted");
await cli(["account", "unlock", "--account", name], password);
const privateKey = await keytar.getPassword("genlayer-cli", "account:" + name);
if (!privateKey) throw new Error("CLI did not cache the new private key in OS Keychain");
const sdk = await import(pathToFileURL(join(cliRoot, "node_modules/genlayer-js/dist/index.js")));
const address = sdk.createAccount(privateKey).address;
if (address.toLowerCase() !== "0x" + keystore.address.toLowerCase().replace(/^0x/, "")) {
  throw new Error("unlocked account does not match its encrypted keystore");
}
const publisher = JSON.parse(readFileSync(join(homedir(), ".genlayer", "keystores", before.activeAccount + ".json"), "utf8"));
if (publisher.address.toLowerCase().replace(/^0x/, "") === address.toLowerCase().slice(2)) {
  throw new Error("challenger must have a different address from the publisher");
}
const after = JSON.parse(readFileSync(configPath, "utf8"));
if (after.activeAccount !== before.activeAccount) throw new Error("CLI unexpectedly changed the active account");
console.log(JSON.stringify({name, address, unlocked: true, funded: false,
  recoveryPassword: {service: recoveryService, account: recoveryAccount}}, null, 2));
