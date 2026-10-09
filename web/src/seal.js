// Third copy of the pure core, after contracts/impeach.py and cli/impeach.py.
// test/test_parity.mjs holds this file to the fixtures the Python side writes.
//
// The page uses it for two things a reader should not have to take on trust:
// hashing an item's text locally to ask the registry about it, and recomputing
// a verdict from the published probes.

export const VERSION = "impeach/1";

const SPACE = new Set([" ", "\t", "\n", "\r", "\x0b", "\x0c", "\u00a0"]);
const QUOTES = { "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"' };
const encoder = new TextEncoder();

export function squash(text) {
  const out = [];
  let gap = false;
  for (const ch of text) {
    if (SPACE.has(ch)) { gap = true; continue; }
    if (gap && out.length) out.push(" ");
    gap = false;
    out.push(ch);
  }
  return out.join("");
}

export function flatten(text) {
  const out = [];
  for (let ch of squash(text)) {
    if (QUOTES[ch]) ch = QUOTES[ch];
    const o = ch.codePointAt(0);
    if (o >= 65 && o <= 90) ch = String.fromCodePoint(o + 32);
    out.push(ch);
  }
  return out.join("");
}

export async function sha256Hex(text) {
  const digest = await globalThis.crypto.subtle.digest("SHA-256", encoder.encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

const part = (text) => encoder.encode(text).length + ":" + text;

export function contentHash(prompt) {
  return sha256Hex(VERSION + "/content\n" + flatten(prompt));
}

export function itemCommitment(prompt, answer, salt) {
  return sha256Hex(VERSION + "/item\n" + part(salt) + "\n" + part(answer) + "\n" + part(prompt));
}

const milli = (p, whole) => (whole > 0 ? Math.floor((p * 1000) / whole) : 0);

function signedMilli(a, b, whole) {
  if (whole <= 0) return 0;
  return a >= b ? Math.floor(((a - b) * 1000) / whole) : -Math.floor(((b - a) * 1000) / whole);
}

// The verdict arithmetic of Impeach.rule, on what get_probe returns.
export function ruleOffline(terms, probes) {
  let nLive = 0, pinnedRight = 0, rewriteRight = 0;
  let admissible = 0, inadmissible = 0, stale = 0, dead = 0, deadPinned = 0;
  let recallN = 0, recallHits = 0;
  for (const p of probes) {
    if (p.touched === false) continue;
    if (p.stage_c1 === "INADMISSIBLE" || p.stage_c2 === "INADMISSIBLE") inadmissible += 1;
    const pair = p.stage_c1 === "ADMISSIBLE" && p.stage_c2 === "ADMISSIBLE";
    if (p.recall === "MATCH") { recallN += 1; recallHits += 1; }
    else if (p.recall === "MISS") recallN += 1;
    else if (p.recall === "DEAD") dead += 1;
    if (p.pinned === "DEAD") { dead += 1; deadPinned += 1; }
    if (p.pinned !== "RIGHT" && p.pinned !== "WRONG") continue;
    nLive += 1;
    if (p.pinned === "RIGHT") pinnedRight += 1;
    if (pair && ["RIGHT", "WRONG", "DEAD"].includes(p.rewrite)) {
      admissible += 1;
      if (p.rewrite === "RIGHT") rewriteRight += 1;
      if (p.rewrite === "DEAD") dead += 1;
      if (p.stale) stale += 1;
    } else {
      rewriteRight += 1;
    }
  }
  const delta = signedMilli(pinnedRight, rewriteRight, nLive);
  const recall = milli(recallHits, recallN);
  const shortfall = terms.score_milli - milli(pinnedRight, nLive);
  const gapTrips = admissible >= terms.min_items && delta >= terms.delta_threshold;
  const recallTrips = recallN >= terms.min_items && recall >= terms.recall_threshold;
  let verdict, reason;
  if (gapTrips || recallTrips) {
    verdict = "CONTAMINATED";
    reason = gapTrips && recallTrips ? "GAP_AND_RECALL" : gapTrips ? "GAP" : "RECALL";
  } else if (nLive >= terms.min_items && shortfall >= terms.delta_threshold) {
    verdict = "UNSUPPORTED"; reason = "SCORE_NOT_REPRODUCED";
  } else if (admissible >= terms.min_items) {
    verdict = "CLEAN"; reason = recallN >= terms.min_items ? "" : "RECALL_NOT_MEASURED";
  } else if (nLive < terms.min_items && nLive + deadPinned >= terms.min_items) {
    verdict = "INCONCLUSIVE"; reason = "ENDPOINT_SILENT";
  } else {
    verdict = "INCONCLUSIVE"; reason = "TOO_FEW_ADMISSIBLE";
  }
  return {
    verdict, reason,
    delta_milli: delta,
    recall_milli: recall,
    pinned_milli: milli(pinnedRight, nLive),
    rewrite_milli: milli(rewriteRight, nLive),
    admissible_probes: admissible,
    inadmissible_rewrites: inadmissible,
    stale_answers: stale,
    dead_probes: dead,
    recall_probes: recallN,
    items_probed: nLive,
  };
}

// Word-level diff for showing what a rewrite moved. Longest common subsequence
// over whitespace-separated tokens; returns [{text, kept}] for each side.
export function wordDiff(a, b) {
  const x = a.split(/(\s+)/).filter((t) => t.length);
  const y = b.split(/(\s+)/).filter((t) => t.length);
  const n = x.length, m = y.length;
  const table = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      table[i][j] = x[i] === y[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  const left = [], right = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (x[i] === y[j]) { left.push({ text: x[i], kept: true }); right.push({ text: y[j], kept: true }); i += 1; j += 1; }
    else if (table[i + 1][j] >= table[i][j + 1]) { left.push({ text: x[i], kept: false }); i += 1; }
    else { right.push({ text: y[j], kept: false }); j += 1; }
  }
  while (i < n) { left.push({ text: x[i], kept: false }); i += 1; }
  while (j < m) { right.push({ text: y[j], kept: false }); j += 1; }
  return { left, right };
}
