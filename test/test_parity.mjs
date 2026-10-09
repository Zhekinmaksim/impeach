// web/src/seal.js against what the Python core computed.
//   node test/test_parity.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as seal from "../web/src/seal.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const fx = JSON.parse(readFileSync(join(root, "test/fixtures/parity.json"), "utf8"));
let pass = 0, fail = 0;
const check = (name, cond) => { cond ? (pass += 1) : (fail += 1, console.log("  FAIL " + name)); };

for (const t of fx.texts) {
  const label = JSON.stringify(t.text.slice(0, 24));
  check("squash " + label, seal.squash(t.text) === t.squash);
  check("flatten " + label, seal.flatten(t.text) === t.flatten);
  check("content hash " + label, (await seal.contentHash(t.text)) === t.content_hash);
}
for (const c of fx.commitments) {
  check("commitment " + c.hash.slice(0, 12), (await seal.itemCommitment(c.prompt, c.answer, c.salt)) === c.hash);
}
for (const v of fx.verdicts) {
  const mine = seal.ruleOffline(v.terms, v.probes);
  check("verdict " + v.result.verdict, Object.keys(v.result).every((k) => mine[k] === v.result[k]));
}
const d = seal.wordDiff("lay 16 eggs per day", "lay 22 eggs per day");
check("diff marks only the moved token",
  d.left.filter((t) => !t.kept).map((t) => t.text).join("") === "16" &&
  d.right.filter((t) => !t.kept).map((t) => t.text).join("") === "22");

console.log(`${pass} passed, ${fail} failed  (web/src/seal.js parity)`);
process.exit(fail ? 1 : 0);
