// The page reads one file, case.json, built by scripts/simulate.py (a rehearsal)
// or scripts/collect.py (settled receipts). It never talks to a chain itself.
//
// Everything in the snapshot that came from a publisher, a challenger or a model
// is untrusted text. It is only ever placed with textContent.

import { contentHash, ruleOffline, wordDiff } from "./seal.js";

const EXPLORER = "https://explorer-bradbury.genlayer.com/transactions/";

const CLASS_NAMES = {
  paraphrase: "reworded",
  numeral_substitution: "numbers substituted",
  option_permutation: "options reordered",
  distractor_swap: "wrong options replaced",
  entity_rename: "names changed",
  unit_change: "units converted",
  format_shift: "layout changed",
};

const VERDICT_TEXT = {
  CONTAMINATED: (c) =>
    ({
      GAP_AND_RECALL: "Both detectors are over the thresholds frozen in the claim: the model lost its answers when the questions were rewritten, and it could continue the sealed items from memory.",
      GAP: "The model answered the sealed items and lost them when the same questions were rewritten. The gap is over the threshold frozen in the claim.",
      RECALL: "The model continued sealed items it was only shown the start of. The recall rate is over the threshold frozen in the claim.",
    })[c.reason] || "Over the thresholds frozen in the claim.",
  CLEAN: (c) =>
    "The admitted rewrite sample met the minimum and the gap stayed below its threshold." +
    (c.reason === "RECALL_NOT_MEASURED" ? " Recall did not meet the minimum measurable sample." : " Verbatim recall also stayed below its threshold.") +
    (c.bond_standing > 0 ? " The bond is still posted, so the next challenger can try again." : " The publisher has since taken the bond back."),
  UNSUPPORTED: (c) =>
    c.reason === "SET_ALREADY_SPENT"
      ? "The claim was sworn on items that were already in the spent registry. No probe can repair that."
      : "The model did not reproduce the sworn score on its own sealed items. Nothing suggests memory; the number was simply not true.",
  INCONCLUSIVE: (c) =>
    c.reason === "ENDPOINT_SILENT"
      ? "The endpoint did not answer enough probes to rule. The publisher paid the challenger's costs, and the claim can be tried again."
      : "Too few rewrites were admitted to rule on the gap. No bond penalty was imposed; rewrite stake was settled according to the referee rulings.",
  DEFAULT: () => "The publisher did not reveal the sealed items inside the window and lost by default. Nothing was burned.",
  UNCONTESTED: () => "Nobody has challenged this claim. That is not a finding: an unchallenged score is never called clean.",
};

const state = { snap: null, caseIndex: 0, item: 0 };

const $ = (id) => document.getElementById(id);

function h(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === false || value == null) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

const permille = (n) => n + "‰";
const when = (seconds) => (seconds ? new Date(seconds * 1000).toISOString().replace("T", " ").slice(0, 16) + " UTC" : "—");
const current = () => state.snap.cases[state.caseIndex];

function scriptedSubject(kase) {
  let params = kase.claim.decode_params;
  if (typeof params === "string") {
    try { params = JSON.parse(params); } catch { params = {}; }
  }
  return String(kase.claim.subject || "").startsWith("scripted/")
    || String(params?.model || "").startsWith("scripted/");
}

function subjectLabel(kase) {
  if (scriptedSubject(kase)) return state.snap.provenance === "bradbury" ? "Scripted control" : kase.label + " (scripted)";
  return kase.claim.subject.startsWith("meta-llama/llama-3.1-8b-instruct") ? "Llama 3.1 8B" : kase.label;
}

function probeFor(kase, itemIndex) {
  return kase.probes.find((p) => p.item_index === itemIndex) || { item_index: itemIndex, touched: false };
}

function admitted(p) {
  return p.stage_c1 === "ADMISSIBLE" && p.stage_c2 === "ADMISSIBLE";
}

function stakeSettlement(kase, p) {
  const settled = p.slice_settled || kase.challenge?.status === "RULED";
  if (!settled) return { text: "still riding", forfeited: false };
  const refused = p.stage_c1 === "INADMISSIBLE" || p.stage_c2 === "INADMISSIBLE";
  const early = kase.certificate.verdict === "DEFAULT" || kase.certificate.reason === "SET_ALREADY_SPENT";
  const returned = !refused && (Boolean(p.rewrite_class) || early);
  return {
    text: String(kase.challenge.slice) + " wei credited to the " + (returned ? "challenger" : "publisher"),
    forfeited: !returned,
  };
}

// ------------------------------------------------------------------ pieces

function questionNode(tokens) {
  const p = h("p", { class: "question" });
  for (const t of tokens) p.append(t.kept ? document.createTextNode(t.text) : h("mark", { text: t.text }));
  return p;
}

function pairNodes(kase, itemIndex) {
  const item = kase.items[itemIndex];
  const p = probeFor(kase, itemIndex);
  if (!item) return [h("div", {}, h("p", { text: "This item is still sealed." }))];

  const has = Boolean(p.rewrite_class);
  const diff = has ? wordDiff(item.prompt, p.rewrite_prompt) : { left: [{ text: item.prompt, kept: true }], right: [] };

  const left = h("div", { class: "sealed" },
    h("div", { class: "side-name", text: "As sealed" }),
    questionNode(diff.left),
    h("dl", { class: "answers" },
      h("dt", { text: "Reference" }), h("dd", { text: item.answer }),
      h("dt", { text: scriptedSubject(kase) ? "Lookup returned" : "Model answered" }),
      h("dd", { class: p.pinned === "RIGHT" ? "" : "bad", text: answerText(p.pinned, p.pinned_answer) }),
    ));

  let right;
  if (!has) {
    right = h("div", { class: "rewritten" },
      h("div", { class: "side-name", text: "As rewritten" }),
      h("p", { text: "The challenger filed no rewrite for this item. It is read as if the rewrite had been answered correctly." }));
  } else {
    const ok = admitted(p);
    right = h("div", { class: "rewritten" },
      h("div", { class: "side-name", text: "As rewritten: " + (CLASS_NAMES[p.rewrite_class] || p.rewrite_class) }),
      questionNode(diff.right),
      h("dl", { class: "answers" },
        h("dt", { text: "Reference" }), h("dd", { text: p.rewrite_answer }),
        h("dt", { text: scriptedSubject(kase) ? "Lookup returned" : "Model answered" }),
        ok || p.rewrite
          ? h("dd", { class: p.rewrite === "RIGHT" ? "" : "bad", text: answerText(p.rewrite, p.rewrite_reply) + (p.stale ? ", the old answer" : "") })
          : h("dd", { text: "no recorded answer" }),
        h("dt", { text: "Referees" }),
        h("dd", { class: ok ? "" : "bad", text: refereeText(p) }),
      ));
  }
  return [left, right];
}

function answerText(status, answer) {
  if (status === "DEAD") return "no reply";
  if (!status) return "no recorded answer";
  const shown = answer === "" ? "nothing readable" : answer;
  return shown + (status === "RIGHT" ? ", right" : ", wrong");
}

function refereeText(p) {
  if (p.stage_c1 === "INADMISSIBLE") return "first framing ruled it a different question";
  if (p.stage_c2 === "INADMISSIBLE") return "second framing ruled it a different question";
  if (p.stage_c2 === "PENDING") return "first framing passed, second not yet run";
  return "both framings agree it is the same question";
}

// ----------------------------------------------------------------- exhibit

function pickExhibit(kase) {
  const pairs = kase.probes.filter((p) => admitted(p) && p.pinned);
  return (
    pairs.find((p) => p.stale) ||
    pairs.find((p) => p.pinned === "RIGHT" && p.rewrite !== "RIGHT") ||
    pairs.find((p) => p.rewrite_class === "numeral_substitution") ||
    pairs[0] || null
  );
}

function renderExhibit(kase) {
  const pair = $("exhibit-pair");
  pair.replaceChildren();
  const pick = pickExhibit(kase);
  if (!pick) {
    $("exhibit-sub").textContent = "";
    pair.append(h("div", {}, h("p", { text: kase.items.length ? "No admitted rewrite to show for this case." : "The items of this claim are still sealed. There is nothing to show until a challenge is accepted." })));
    $("exhibit-note").textContent = "";
    return;
  }
  $("exhibit-sub").textContent = "Item " + (pick.item_index + 1) + " of " + kase.items.length + ", " + (CLASS_NAMES[pick.rewrite_class] || pick.rewrite_class);
  pair.append(...pairNodes(kase, pick.item_index));
  let note;
  if (pick.stale) {
    note = "The numbers moved and the answer moved with them. The model gave the answer to the question it had seen before. Underlined words are the ones that differ.";
  } else if (pick.pinned === "RIGHT" && pick.rewrite !== "RIGHT") {
    note = "The model answered the sealed wording and lost the rewritten one. Underlined words are the ones that differ.";
  } else if (pick.pinned === "RIGHT" && pick.rewrite === "RIGHT") {
    note = "The model answered both. That is what being able to do the task looks like. Underlined words are the ones that differ.";
  } else {
    note = "Underlined words are the ones that differ between the two versions.";
  }
  $("exhibit-note").textContent = note;
  if (scriptedSubject(kase)) {
    $("exhibit-note").textContent = "This control returns stored answers and text; no subject LLM is called. " +
      (pick.stale ? "It deliberately returned the sealed answer after the numbers changed. " : "") +
      "Underlined words are the ones that differ.";
  }
}

// ------------------------------------------------------------------- marks

// One item, three marks. Used by the sheet at the top and the sheet below, so
// the two can never disagree about what was pencilled in.
function marksFor(p) {
  const pinned =
    p.pinned === "RIGHT" ? ["fill", "sealed wording, answered right"]
    : p.pinned === "DEAD" ? ["dead", "sealed wording, no reply"]
    : p.pinned === "WRONG" ? ["", "sealed wording, answered wrong"]
    : ["none", "sealed wording, no recorded result"];
  const rewritten =
    !admitted(p) ? ["none", p.rewrite_class ? "rewrite not admitted" : "no rewrite filed"]
    : p.stale ? ["old", "rewritten, answered with the old answer"]
    : p.rewrite === "RIGHT" ? ["fill", "rewritten, answered right"]
    : p.rewrite === "DEAD" ? ["dead", "rewritten, no reply"]
    : ["", "rewritten, answered wrong"];
  const recall =
    p.recall === "MATCH" ? ["fill", "continued the sealed text verbatim"]
    : p.recall === "DEAD" ? ["dead", "recall probe, no reply"]
    : p.recall === "MISS" ? ["", "did not reproduce the sealed text"]
    : p.recall === "NA" ? ["none", "too short for the recall probe"]
    : ["none", "recall probe has no recorded result"];
  return { pinned, rewritten, recall };
}

// -------------------------------------------------------------------- hero

function renderHero(kase, fresh) {
  const fig = $("hero-sheet");
  const subset = kase.challenge ? kase.challenge.subset : [];
  fig.replaceChildren(h("span", { class: "corner", "aria-hidden": "true" }));
  if (!subset.length) {
    fig.append(h("figcaption", { text: "No trial has run on this claim, so its sheet is blank." }));
    return;
  }
  fig.style.setProperty("--n", subset.length);
  const rows = ["pinned", "rewritten", "recall"].map((name, r) =>
    h("div", { class: "hero-row" + (fresh ? " fresh" : "") + (name === "recall" ? " apart" : ""), style: "--row:" + r, "aria-hidden": "true" }));
  subset.forEach((itemIndex, i) => {
    const m = marksFor(probeFor(kase, itemIndex));
    rows[0].append(h("span", { class: "b " + m.pinned[0], style: "--i:" + i }));
    rows[1].append(h("span", { class: "b " + m.rewritten[0], style: "--i:" + i }));
    rows[2].append(h("span", { class: "b " + m.recall[0], style: "--i:" + i }));
  });
  const cert = kase.certificate;
  fig.append(...rows, h("figcaption", {
    text: "The sheet of " + subjectLabel(kase) + ": " + subset.length + " items, one column each. Row one, answered as sealed. Row two, answered as rewritten. Row three, continued the sealed text.",
  }));
  fig.setAttribute("role", "img");
  fig.setAttribute("aria-label",
    "Answer sheet for " + kase.label + ": " + permille(cert.pinned_milli) + " right as sealed, " +
    permille(cert.rewrite_milli) + " court-adjusted rewrite score, " + permille(cert.recall_milli) + " continued verbatim.");
}

// ------------------------------------------------------------------- slope

const SVG = "http://www.w3.org/2000/svg";
function s(tag, attrs, text) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
  if (text != null) node.textContent = text;
  return node;
}

// Accuracy on the sealed wording at the left, on the rewritten wording at the
// right. The dashed line is how far the frozen threshold lets it fall.
function renderSlope(kase) {
  const fig = $("slope");
  fig.replaceChildren();
  if (!kase.challenge || !kase.certificate.items_probed) return;
  const W = 384, H = 236, x0 = 58, x1 = 306, top = 34, bottom = 196;
  const y = (m) => bottom - (Math.max(0, Math.min(1000, m)) / 1000) * (bottom - top);
  const svg = s("svg", { viewBox: "0 0 " + W + " " + H, role: "img" });
  const cert = kase.certificate;
  const over = cert.verdict === "CONTAMINATED" && cert.reason !== "RECALL";
  svg.append(s("title", {}, "Sealed accuracy " + cert.pinned_milli + " per mille, court-adjusted rewrite score " + cert.rewrite_milli + " per mille."));
  svg.append(s("line", { class: "axis", x1: x0, y1: top - 8, x2: x0, y2: bottom }), s("line", { class: "axis", x1, y1: top - 8, x2: x1, y2: bottom }));
  svg.append(s("text", { x: x0, y: H - 14, "text-anchor": "middle" }, "as sealed"), s("text", { x: x1, y: H - 14, "text-anchor": "middle" }, "rewrite score"));
  // scale ends, on the outside of the left axis where no value label is drawn
  svg.append(s("text", { x: x0 - 10, y: bottom + 4, "text-anchor": "end" }, "0"), s("text", { x: x0 - 10, y: top + 4, "text-anchor": "end" }, "1000‰"));

  for (const other of state.snap.cases) {
    if (other === kase || !other.challenge || !other.certificate.items_probed) continue;
    const c = other.certificate;
    svg.append(
      s("line", { class: "other", x1: x0, y1: y(c.pinned_milli), x2: x1, y2: y(c.rewrite_milli) }),
      s("circle", { class: "other-dot", cx: x0, cy: y(c.pinned_milli), r: 3.5 }),
      s("circle", { class: "other-dot", cx: x1, cy: y(c.rewrite_milli), r: 3.5 }),
      s("text", { class: "other-label", x: x1 + 9, y: y(c.rewrite_milli) + 4 }, subjectLabel(other)),
    );
  }

  const allowed = cert.pinned_milli - kase.claim.delta_threshold;
  if (allowed >= 0) {
    svg.append(s("line", { class: "allowed", x1: x0, y1: y(cert.pinned_milli), x2: x1, y2: y(allowed) }));
  }
  const tone = over ? " over" : "";
  svg.append(
    s("line", { class: "mine" + tone, x1: x0, y1: y(cert.pinned_milli), x2: x1, y2: y(cert.rewrite_milli) }),
    s("circle", { class: "dot" + tone, cx: x0, cy: y(cert.pinned_milli), r: 5.5 }),
    s("circle", { class: "dot" + tone, cx: x1, cy: y(cert.rewrite_milli), r: 5.5 }),
    s("text", { class: "value", x: x0 + 12, y: y(cert.pinned_milli) + (cert.pinned_milli > 880 ? -10 : -12) }, permille(cert.pinned_milli)),
    s("text", { class: "value" + tone, x: x1 - 10, y: y(cert.rewrite_milli) + (over && cert.rewrite_milli > 120 ? 22 : -12), "text-anchor": "end" }, permille(cert.rewrite_milli)),
  );
  fig.append(svg, h("figcaption", {
    text: "Dashed: the furthest the frozen threshold lets it fall. The court counts missing or unadmitted rewrites as correct; this is not accuracy on admitted rewrites alone." +
      (state.snap.cases.length > 1 ? " Pale lines are the other subjects in this file." : "") +
      (state.snap.cases.some(k => k.claim.subject.startsWith("scripted/memoriser-court24-v2"))
        ? " The scripted control shares the live cohort's arithmetic and is not an independent benchmark." : ""),
  }));
}

// ------------------------------------------------------------------- drawn

function countUp(node, target) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches || target < 2) { node.textContent = String(target); return; }
  const started = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - started) / 650);
    node.textContent = String(Math.round(target * (1 - Math.pow(1 - t, 3))));
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function renderDrawn(kase, fresh) {
  const box = $("drawn");
  box.replaceChildren();
  if (!kase.challenge) return;
  const asked = (v) => (v && v !== "NA" ? 1 : 0);
  let calls = 0, rulings = 0;
  for (const p of kase.probes) {
    calls += asked(p.pinned) + asked(p.recall) + asked(p.rewrite);
    rulings += (p.stage_c1 && p.stage_c1 !== "PENDING" ? 1 : 0) + (p.stage_c2 && p.stage_c2 !== "PENDING" ? 1 : 0);
  }
  const txs = Object.keys(kase.txs || {}).length;
  const figures = [
    [kase.certificate.items_burned, "items burned to hear this case"],
    [calls, "model probe outcomes recorded"],
    [rulings, "referee rulings on rewrites"],
    [kase.certificate.admissible_probes, "pairs admitted as the same question"],
  ];
  if (txs) figures.push([txs, "transactions, each with a receipt"]);
  for (const [n, label] of figures) {
    const dd = h("dd", { text: fresh ? "0" : String(n) });
    box.append(h("div", {}, dd, h("dt", { text: label })));
    if (fresh) countUp(dd, n);
  }
}

// ------------------------------------------------------------------- sheet

function bubble(kind, label, itemIndex, i) {
  return h("button", {
    type: "button",
    class: "b " + kind,
    style: "--i:" + i,
    "aria-label": "Item " + (itemIndex + 1) + ": " + label,
    "aria-pressed": state.item === itemIndex ? "true" : "false",
    "data-item": itemIndex,
    title: "Item " + (itemIndex + 1) + ": " + label,
    onclick: () => selectItem(itemIndex, true),
  });
}

function gauge(value, threshold, measured) {
  const clamp = (n) => Math.max(0, Math.min(1000, n)) / 10;
  return h("div", { class: "gauge", role: "img", "aria-label": measured ? value + " per mille against a threshold of " + threshold : "not measured" },
    h("div", { class: "line" }),
    h("div", { class: "at", style: "left:0" }, h("span", { text: "0", style: "transform:none" })),
    h("div", { class: "at", style: "left:" + clamp(threshold) + "%" }, h("span", { text: "threshold " + permille(threshold) })),
    h("div", { class: "at", style: "left:100%" }, h("span", { text: "1000‰", style: "transform:translateX(-100%)" })),
    measured ? h("div", { class: "val" + (value >= threshold ? " over" : ""), style: "left:" + clamp(value) + "%" }) : null,
  );
}

function renderSheet(kase, fresh) {
  const cert = kase.certificate;
  const claim = kase.claim;
  const subset = kase.challenge ? kase.challenge.subset : [];
  const sheet = $("sheet");
  sheet.replaceChildren();
  sheet.style.setProperty("--n", Math.max(subset.length, 1));

  const word = cert.verdict;
  const tone = word === "CONTAMINATED" || word === "UNSUPPORTED" || word === "DEFAULT" ? "bad" : word === "CLEAN" ? "good" : "";
  const verdict = $("verdict");
  verdict.replaceChildren(
    h("div", { class: "word " + tone, text: word.charAt(0) + word.slice(1).toLowerCase() }),
    h("p", { text: (VERDICT_TEXT[word] || (() => ""))(cert) }),
  );

  $("ruling-sub").textContent = subset.length
    ? subset.length + " challenged items. One column per item; select a mark to read that item in full."
    : "No trial has run on this claim.";
  if (!subset.length) { $("legend").replaceChildren(); return; }

  // recompute the verdict here, from the probes on the page
  const mine = ruleOffline(
    { score_milli: claim.score_milli, delta_threshold: claim.delta_threshold, recall_threshold: claim.recall_threshold, min_items: claim.min_items },
    kase.probes,
  );
  const drift = Object.keys(mine).filter((k) => cert[k] !== mine[k]);
  const fixedByReveal = cert.reason === "SET_ALREADY_SPENT";
  if (!fixedByReveal) {
    verdict.append(h("p", {
      class: "recheck" + (drift.length ? " bad" : ""),
      text: drift.length
        ? "Recomputed in this browser from the probes below, the certificate does not match on: " + drift.join(", ") + "."
        : "Recomputed in this browser from the " + kase.probes.length + " items below. It matches the certificate.",
    }));
  }

  const pinned = h("div", { class: "bubbles" });
  const rewritten = h("div", { class: "bubbles" });
  const recall = h("div", { class: "bubbles" });
  const nums = h("div", { class: "nums" });
  subset.forEach((itemIndex, i) => {
    const m = marksFor(probeFor(kase, itemIndex));
    pinned.append(bubble(m.pinned[0], m.pinned[1], itemIndex, i));
    rewritten.append(bubble(m.rewritten[0], m.rewritten[1], itemIndex, i));
    recall.append(bubble(m.recall[0], m.recall[1], itemIndex, i));
    nums.append(h("span", { text: itemIndex + 1 }));
  });

  const gapMeasured = cert.admissible_probes >= claim.min_items;
  const recallMeasured = cert.recall_probes >= claim.min_items;
  sheet.append(
    h("div", { class: "detector" },
      h("div", { class: "name" },
        h("h3", { text: "Detector one: the gap" }),
        h("span", { text: "Sealed accuracy " + permille(cert.pinned_milli) + ", court-adjusted rewrite score " + permille(cert.rewrite_milli) + ". Gap " + permille(cert.delta_milli) + " across " + cert.items_probed + " answered sealed items; " + cert.admissible_probes + " pairs admitted. Missing or unadmitted rewrites count as correct for the publisher." })),
      h("div", { class: "tick" }), h("div", { class: "row-label", text: "Answered as sealed" }), pinned,
      h("div", { class: "tick" }), h("div", { class: "row-label", text: "Answered as rewritten" }), rewritten,
      gauge(cert.delta_milli, claim.delta_threshold, gapMeasured),
    ),
    h("div", { class: "detector" },
      h("div", { class: "name" },
        h("h3", { text: "Detector two: verbatim recall" }),
        h("span", { text: recallMeasured || cert.recall_probes
          ? "Given the first " + claim.recall_prefix_milli / 10 + "% of an item, the " + (scriptedSubject(kase) ? "lookup returned" : "model reproduced") + " the rest on " + permille(cert.recall_milli) + " of " + cert.recall_probes + " items. No language model judges this one."
          : "Not measured on this claim." })),
      h("div", { class: "tick" }), h("div", { class: "row-label", text: "Continued verbatim" }), recall,
      gauge(cert.recall_milli, claim.recall_threshold, recallMeasured),
      h("div", {}), h("div", { class: "row-label low", text: "Item" }), nums,
    ),
  );

  const key = (kind, text) => h("li", {}, h("span", { class: "b " + kind, "aria-hidden": "true" }), text);
  $("legend").replaceChildren(
    key("fill", "yes"), key("", "no"), key("old", "answered with the old answer"),
    key("dead", "endpoint did not reply"), key("none", "not counted"),
  );
}

// ------------------------------------------------------------------ detail

function selectItem(itemIndex, scroll) {
  state.item = itemIndex;
  document.querySelectorAll(".b[data-item]").forEach((b) => b.setAttribute("aria-pressed", Number(b.dataset.item) === itemIndex ? "true" : "false"));
  renderDetail(current());
  if (scroll) $("detail").scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
}

function renderDetail(kase) {
  const section = $("detail");
  if (!kase.items.length) { section.hidden = true; return; }
  section.hidden = false;
  const subset = kase.challenge ? kase.challenge.subset : kase.items.map((_, i) => i);
  if (!subset.includes(state.item)) state.item = subset[0];
  const item = kase.items[state.item];
  const p = probeFor(kase, state.item);

  $("detail-title").textContent = "Item " + (state.item + 1) + " in full";
  $("detail-pair").replaceChildren(...pairNodes(kase, state.item));

  const box = $("detail-recall");
  box.replaceChildren(h("div", { class: "side-name", text: "Recall probe: first part and held-out continuation" }));
  box.append(h("p", {}, item.recall_prefix, h("span", { class: "held", text: item.recall_tail })));
  box.append(h("dl", { class: "answers", style: "margin-top:0.8rem" },
    h("dt", { text: "Held-out part" }), h("dd", { text: "dotted, " + item.recall_tail.length + " characters" }),
    h("dt", { text: "Result" }),
    h("dd", { class: p.recall === "MATCH" ? "bad" : "", text: {
      MATCH: "reproduced it", MISS: "did not reproduce it", DEAD: "no reply", NA: "item too short to test",
    }[p.recall] || "no recorded result" })));

  const facts = $("detail-facts");
  const row = (name, value, bad) => [h("dt", { text: name }), h("dd", { class: bad ? "bad" : "", text: value })];
  const settlement = stakeSettlement(kase, p);
  facts.replaceChildren(
    h("dt", { text: "Sealed hash" }), h("dd", {}, h("code", { text: item.item_hash })),
    h("dt", { text: "Text hash" }), h("dd", {}, h("code", { text: item.content_hash })),
    ...(p.rewrite_hash ? [h("dt", { text: "Rewrite hash" }), h("dd", {}, h("code", { text: p.rewrite_hash }))] : []),
    ...row("Stake slice", settlement.text, settlement.forfeited),
    ...row("Burned", when(kase.claim.burned_at)),
  );

  const at = subset.indexOf(state.item);
  $("prev").onclick = () => selectItem(subset[(at - 1 + subset.length) % subset.length], false);
  $("next").onclick = () => selectItem(subset[(at + 1) % subset.length], false);
}

// ------------------------------------------------------------------ record

function renderRecord(kase) {
  const c = kase.claim;
  const cert = kase.certificate;
  const line = (name, value, long) => h("tr", {}, h("th", { scope: "row", text: name }), h("td", { class: long ? "long" : "", text: value }));
  let template = c.prompt_template;
  try { const t = JSON.parse(c.prompt_template); template = (t.system ? "system: " + t.system + "\n" : "") + "user: " + t.user; } catch { /* shown raw */ }

  $("terms").replaceChildren(
    line("Subject", c.subject),
    line("Subject type", scriptedSubject(kase) ? "Scripted lookup control — no subject LLM" : "Model endpoint"),
    line("Sworn score", permille(c.score_milli)),
    line("Sealed items", String(c.item_hashes.length)),
    line("Endpoint", c.endpoint, true),
    line("Gap threshold", permille(c.delta_threshold)),
    line("Recall threshold", permille(c.recall_threshold)),
    line("Smallest sample", c.min_items + " items"),
    line("Rewrites allowed", c.classes.map((k) => CLASS_NAMES[k] || k).join(", ")),
    line("Recall match", "first " + c.recall_prefix_milli / 10 + "% shown, similarity at least " + c.similarity_milli / 1000),
    line("Decode parameters", c.decode_params, true),
    line("Prompt", template, true),
    line("Scoring rule", c.scoring_rule, true),
    line("Bond (wei)", String(c.bond_sworn)),
    line("Stake per item (wei)", String(c.stake)),
    h("tr", {}, h("th", { scope: "row", text: "Terms hash" }), h("td", {}, h("code", { text: c.spec_hash }))),
  );

  $("cert").replaceChildren(
    line("Claim", String(cert.claim_id)),
    line("Verdict", cert.verdict + (cert.reason ? ", " + cert.reason.toLowerCase().replaceAll("_", " ") : "")),
    line("Gap", permille(cert.delta_milli)),
    line("Recall", permille(cert.recall_milli)),
    line("Sealed accuracy", permille(cert.pinned_milli) + " measured, " + permille(cert.score_sworn_milli) + " sworn"),
    line("Admitted pairs", String(cert.admissible_probes)),
    line("Rewrites refused", String(cert.inadmissible_rewrites)),
    line("Old answers given", String(cert.stale_answers)),
    line("Probes with no reply", String(cert.dead_probes)),
    line("Items burned", String(cert.items_burned)),
    line("The score itself", cert.score_status === "SPENT"
      ? "spent with its items on " + when(cert.score_expired_at) + ". It can never be measured again on unseen text."
      : "still sealed", true),
    line("Challenges survived", String(cert.challenges_survived)),
    line("Bond still posted (wei)", String(cert.bond_standing)),
    line("Ruled", when(cert.ruled_at)),
    line("Claim closed", cert.final ? "yes" : cert.contested ? "no, open to the next challenger" : "no"),
  );

  if (state.certificateUrl) URL.revokeObjectURL(state.certificateUrl);
  state.certificateUrl = URL.createObjectURL(new Blob([JSON.stringify({
    format: "impeach-certificate/1", provenance: state.snap.provenance,
    contract: state.snap.contract, subject_kind: scriptedSubject(kase) ? "scripted-no-llm" : "model-endpoint",
    certificate: cert,
  }, null, 2) + "\n"], { type: "application/json" }));
  $("download-cert").href = state.certificateUrl;
  $("download-cert").download = "impeach-claim-" + cert.claim_id + "-" + (scriptedSubject(kase) ? "scripted" : "model") + "-certificate.json";

  const opening = Object.entries(kase.txs || {}).find(([name]) => name === "open" || name.startsWith("open:"));
  const openingLink = $("opening-link");
  openingLink.hidden = state.snap.provenance !== "bradbury" || !opening;
  if (opening) {
    openingLink.href = EXPLORER + opening[1].tx;
    openingLink.textContent = "Claim " + cert.claim_id + " opening on Bradbury";
  }
  const rehearsalLink = $("rehearsal-link");
  const llama = state.snap.cases.find(k => !scriptedSubject(k) && k.claim.subject.startsWith("meta-llama/llama-3.1-8b-instruct"));
  rehearsalLink.hidden = !llama;
  if (llama) rehearsalLink.href = "https://github.com/Zhekinmaksim/impeach/blob/main/runs/" +
    (llama.claim.subject.includes("/court24-v2/") ? "v2-llama-rehearsal.json" : "llama-rehearsal.json");

  const receipts = $("receipts");
  receipts.replaceChildren();
  const txs = Object.entries(kase.txs || {});
  if (txs.length) {
    const failed = txs.filter(([, t]) =>
      ["UNDETERMINED", "LEADER_TIMEOUT", "VALIDATORS_TIMEOUT", "CANCELED", "ERROR"].includes(t.status) ||
      (t.status === "FINALIZED" && t.consensus_result === "IDLE" && t.execution === "NOT_VOTED") ||
      ["NO_MAJORITY", "TIMEOUT", "DETERMINISTIC_VIOLATION", "DISAGREE", "MAJORITY_DISAGREE"].includes(t.consensus_result) ||
      ["FINISHED_WITH_ERROR", "TIMEOUT", "NONDET_DISAGREE", "DETERMINISTIC_VIOLATION"].includes(t.execution)).length;
    receipts.append(
      h("h3", { text: "Receipts", style: "margin-top:1.4rem" }),
      h("p", { text: txs.length + " transactions." + (failed ? " " + failed + " did not produce an accepted successful execution. Consensus and execution outcomes are retained in the evidence file; these failures are not model answers." : "") }),
      h("p", {}, ...txs.slice(0, 200).flatMap(([name, t]) => [h("a", { href: EXPLORER + t.tx, rel: "noopener", title: [t.status, t.consensus_result, t.execution].filter(Boolean).join(" / "), text: name.includes("@") ? name.split("@")[0] + " (additional attempt)" : name }), " "])),
    );
  }
}

// ---------------------------------------------------------------- registry

function renderRegistry(hit) {
  const rows = state.snap.registry || [];
  $("registry-sub").textContent = rows.length + (rows.length === 1 ? " item burned" : " items burned");
  const table = $("reg");
  table.replaceChildren(h("tr", {},
    h("th", { scope: "col", text: "Burned in" }), h("th", { scope: "col", text: "Item" }), h("th", { scope: "col", text: "Text hash" })));
  for (const r of rows) {
    table.append(h("tr", { class: hit && (r.content_hash === hit || r.item_hash === hit) ? "hit" : "" },
      h("td", { text: "claim " + r.claim_id }),
      h("td", { class: "txt", text: r.preview ? r.preview.slice(0, 96) + (r.preview.length > 96 ? "…" : "") : "text not in this snapshot" }),
      h("td", { class: "mono", text: r.content_hash })));
  }
}

async function checkItem(event) {
  event.preventDefault();
  const raw = $("needle").value.trim();
  const out = $("check-answer");
  if (!raw) { out.className = "answer"; out.textContent = "Paste an item's text or a 64-character hash first."; return; }
  const asHash = raw.toLowerCase().replace(/^0x/, "");
  let key;
  try {
    key = /^[0-9a-f]{64}$/.test(asHash) ? asHash : await contentHash(raw);
  } catch {
    out.className = "answer";
    out.textContent = "This browser cannot hash here. Open the page over https, or use the command below.";
    return;
  }
  const row = (state.snap.registry || []).find((r) => r.content_hash === key || r.item_hash === key);
  if (row) {
    out.className = "answer spent";
    out.textContent = "Spent. Burned in claim " + row.claim_id + " on " + when(row.burned_at) + ". A score measured on this item is no longer evidence.";
  } else {
    out.className = "answer unspent";
    out.textContent = "Not in the registry. Hash checked: " + key.slice(0, 16) + "…";
  }
  renderRegistry(row ? key : null);
}

// -------------------------------------------------------------------- page

function renderTabs() {
  const tabs = $("tabs");
  tabs.replaceChildren();
  state.snap.cases.forEach((kase, i) => {
    tabs.append(h("button", {
      type: "button", class: "tab", role: "tab",
      "aria-selected": i === state.caseIndex ? "true" : "false",
      text: subjectLabel(kase),
      title: kase.note || kase.claim.subject,
      onclick: () => { state.caseIndex = i; state.item = 0; renderTabs(); renderCase(true); },
    }));
  });
  const single = state.snap.cases.length < 2;
  tabs.hidden = single;
  $("tabs-label").hidden = single;
}

function renderCase(fresh) {
  const kase = current();
  const scripted = scriptedSubject(kase);
  $("subject-kind").dataset.kind = scripted ? "scripted" : "model";
  $("subject-kind").textContent = scripted
    ? (state.snap.provenance === "bradbury" ? "On-chain scripted control. " : "Local scripted demonstration. ") +
      "The subject is a stored-answer and text lookup; no subject LLM is called. Its verdict tests the court's control path, not a real model."
    : (state.snap.provenance === "bradbury" ? "On-chain model case. " : "Local model rehearsal. ") +
      "The subject answers through the endpoint frozen in this claim.";
  const pick = pickExhibit(kase);
  if (pick && fresh) state.item = pick.item_index;
  renderHero(kase, fresh);
  renderExhibit(kase);
  renderSheet(kase, fresh);
  renderSlope(kase);
  renderDrawn(kase, fresh);
  renderDetail(kase);
  renderRecord(kase);
}

async function start() {
  const sourceFile = new URLSearchParams(location.search).get("demo") === "1" ? "demo.json" : "case.json";
  for (const id of ["download-case", "download-evidence"]) {
    $(id).href = sourceFile;
    $(id).download = "impeach-" + sourceFile;
  }
  let snap;
  try {
    const response = await fetch(sourceFile, { cache: "no-cache" });
    if (!response.ok) throw new Error(String(response.status));
    snap = await response.json();
  } catch (error) {
    $("main").replaceChildren(h("section", {}, h("h2", { text: "The case file did not load" }),
      h("p", { text: sourceFile + " could not be read (" + error.message + "). Serve the web folder over http, for example with `make serve`, and reload." })));
    return;
  }
  state.snap = snap;
  $("download-case").textContent = snap.cases.length > 1 ? "Download all " + snap.cases.length + " cases" : "Download the case file";
  $("rehearsal").hidden = snap.provenance === "bradbury";
  $("source").textContent = snap.provenance === "bradbury"
    ? "Built from settled receipts of contract " + snap.contract + " on " + when(snap.generated_at) + "."
    : "Built from a local rehearsal. These results are not on-chain evidence.";
  renderTabs();
  renderCase(true);
  renderRegistry(null);
  $("check").addEventListener("submit", checkItem);
  $("copy-cert").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    try {
      await navigator.clipboard.writeText(JSON.stringify(current().certificate, null, 2));
      button.textContent = "Certificate copied";
    } catch {
      button.textContent = "Copy failed; use the case file";
    }
    setTimeout(() => { button.textContent = "Copy certificate"; }, 2200);
  });
}

start();
