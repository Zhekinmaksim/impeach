"""Every claim the README makes about the contract, as an assertion.

Written against the driver interface in test/drivers.py, so the whole file runs
once on the local stub and once on the real pinned SDK.
"""

import json
import ast
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "cli"))
sys.path.insert(0, os.path.join(ROOT, "test"))

import impeach as tool  # noqa: E402
import population as pop  # noqa: E402

BOND = 1_000_000
STAKE = 10_000          # per challenged item
PARAMS = {"temperature": 0, "top_p": 1, "max_tokens": 256, "seed": 7}
GSM_CLASSES = ["paraphrase", "numeral_substitution", "entity_rename", "unit_change", "format_shift"]
WINDOWS = {"reveal_window_s": 3600, "trial_window_s": 7200}

CORPUS = pop.load_corpus()
ITEMS = CORPUS["items"]
REWRITES = CORPUS["rewrites"]
CONTROLS = CORPUS["controls"]
ALL = list(range(len(ITEMS)))


class Checker:
    def __init__(self, label: str, quiet: bool = False):
        self.label = label
        self.passed = []
        self.failed = []
        self.quiet = quiet

    def section(self, title: str):
        if not self.quiet:
            print("\n" + title)

    def __call__(self, name: str, cond, detail=""):
        (self.passed if cond else self.failed).append(name)
        if not self.quiet or not cond:
            print(("  ok   " if cond else "  FAIL ") + name + ("  -> " + str(detail) if detail != "" and not cond else ""))


def resalt(items: list, tag: str) -> list:
    return [dict(it, salt=it["salt"] + tag) for it in items]


def hashes_of(items: list) -> list:
    return [tool.item_commitment(it["prompt"], it["answer"], it["salt"]) for it in items]


def reveal_payload(items: list) -> str:
    return json.dumps(
        [{"prompt": it["prompt"], "answer": it["answer"], "salt": it["salt"]} for it in items],
        ensure_ascii=False,
    )


def open_claim(d, url, items=None, score=900, min_items=20, delta=250, recall=150,
               bond=BOND, stake=STAKE, classes=None, extras=None, sender=None, value=None,
               subject="vendor/model@2026-09", scoring_rule=pop.SCORING_RULE):
    items = ITEMS if items is None else items
    return d.call(
        d.addr(1) if sender is None else sender,
        "open_claim",
        subject,
        url,
        score,
        json.dumps(hashes_of(items)),
        scoring_rule,
        json.dumps(pop.TEMPLATE),
        json.dumps(PARAMS),
        ",".join(GSM_CLASSES if classes is None else classes),
        delta,
        recall,
        min_items,
        bond,
        stake,
        json.dumps(WINDOWS if extras is None else extras),
        value=bond if value is None else value,
    )


def challenge(d, cid, subset=None, classes=None, sender=None, value=None):
    subset = ALL if subset is None else subset
    return d.call(
        d.addr(2) if sender is None else sender,
        "challenge",
        cid,
        json.dumps(subset),
        json.dumps(GSM_CLASSES if classes is None else classes),
        value=STAKE * len(subset) if value is None else value,
    )


def reveal(d, cid, items=None, sender=None):
    return d.call(d.addr(1) if sender is None else sender, "reveal_items", cid,
                  reveal_payload(ITEMS if items is None else items))


def run_trial(d, hid, subset=None, envelopes=None, rewrite_only=None, challenger=None, retries=False):
    """Every probe round for every item. `envelopes` maps item index to the
    rewrite filed for it; `rewrite_only` limits which items get one."""
    subset = ALL if subset is None else subset
    envelopes = REWRITES if envelopes is None else envelopes
    who = d.addr(2) if challenger is None else challenger
    crank = d.addr(3)
    out = {}
    for i in subset:
        r = {}
        r["pinned"] = d.call(crank, "probe", hid, i, "PINNED", "")
        if retries and r["pinned"] == "DEAD":
            r["pinned"] = d.call(crank, "probe", hid, i, "PINNED", "")
        r["recall"] = d.call(crank, "probe", hid, i, "RECALL", "")
        if retries and r["recall"] == "DEAD":
            r["recall"] = d.call(crank, "probe", hid, i, "RECALL", "")
        if i in envelopes and (rewrite_only is None or i in rewrite_only):
            r["rewrite"] = d.call(who, "probe", hid, i, "REWRITE", tool.canonical_envelope(envelopes[i]))
            if retries and r["rewrite"] == "DEAD":
                r["rewrite"] = d.call(who, "probe", hid, i, "REWRITE", "")
            if r["rewrite"] != "INADMISSIBLE":
                r["admit"] = d.call(crank, "probe", hid, i, "ADMIT", "")
        out[i] = r
    return out


def probes_of(d, hid, subset=None):
    return [d.view("get_probe", hid, i) for i in (ALL if subset is None else subset)]


def full_case(d, url, **claim_kw):
    """Open, challenge everything, reveal, probe everything, rule."""
    cid = open_claim(d, url, **claim_kw)
    hid = challenge(d, cid)
    reveal(d, cid)
    run_trial(d, hid)
    verdict = d.call(d.addr(3), "rule", hid)
    return cid, hid, verdict


def numeric_scoring(check, make):
    check.section("frozen numeric scoring without a model marker")
    tree = ast.parse(open(os.path.join(ROOT, "contracts", "impeach.py"), encoding="utf-8").read())
    rule = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "NUMERIC_LINE_RULE" for t in n.targets))
    d, world = make()
    url = world.serve("https://numeric.example/v1/chat/completions", pop.Memoriser(CORPUS))
    cid, hid, verdict = full_case(d, url, score=1000, scoring_rule=rule)
    cert = d.view("certificate", cid)
    check("numeric rule is frozen verbatim", d.view("get_claim", cid)["scoring_rule"] == rule)
    check("all sealed answers are measured", cert["items_probed"] == 24 and cert["pinned_milli"] == 1000)
    check("no LLM marker is invoked", world.judge_calls == 0)
    check("recall still convicts the lookup control", verdict == "CONTAMINATED" and cert["recall_milli"] == 1000)
    check("all numeric referee framings are applied", cert["admissible_probes"] == 24)
    check("offline arithmetic agrees", offline_agrees(d, cid, hid))
    check("numeric path preserves solvency", d.broken == [])
    d.close()


def terms_of(d, cid) -> dict:
    c = d.view("get_claim", cid)
    return {k: c[k] for k in ("score_milli", "delta_threshold", "recall_threshold", "min_items")}


def offline_agrees(d, cid, hid, subset=None) -> bool:
    cert = d.view("certificate", cid)
    mine = tool.rule_offline(terms_of(d, cid), probes_of(d, hid, subset))
    return all(cert[k] == mine[k] for k in mine)


# ---------------------------------------------------------------- scenarios


def pure_functions(check, module):
    """The copies in the CLI against the copies the contract runs."""
    check.section("hashing, flattening, distance: contract and cli agree")
    it = ITEMS[0]
    check("commitment matches", module.item_commitment(it["prompt"], it["answer"], it["salt"])
          == tool.item_commitment(it["prompt"], it["answer"], it["salt"]))
    check("commitment depends on the salt",
          tool.item_commitment(it["prompt"], it["answer"], "a") != tool.item_commitment(it["prompt"], it["answer"], "b"))
    check("fields cannot bleed into each other",
          tool.item_commitment("ab", "c", "") != tool.item_commitment("a", "bc", ""))
    check("content hash matches", module.content_hash(it["prompt"]) == tool.content_hash(it["prompt"]))
    check("content hash ignores case, spacing and curly quotes",
          tool.content_hash("Janet’s  ducks\nLAY 16 eggs") == tool.content_hash("janet's ducks lay 16 eggs"))
    check("content hash does not ignore a changed number",
          tool.content_hash("lay 16 eggs") != tool.content_hash("lay 17 eggs"))

    samples = [it["prompt"] for it in ITEMS] + ["  a\tb\u00a0c  ", "“Q” ‘x’", "", "ÀÉ İ ß", "x\r\n\r\ny"]
    check("flatten agrees on every sample", all(module.flatten(s) == tool.flatten(s) for s in samples))
    check("squash agrees on every sample", all(module.squash(s) == tool.squash(s) for s in samples))

    answers = ["$1,234.50", "18.", " 18.0 ", "-3.10", "57,500", "ten", "1.2.3", "$ 7"]
    check("norm_answer agrees", all(module.norm_answer(a) == tool.norm_answer(a) for a in answers))
    check("norm_answer: money and trailing zeros",
          tool.norm_answer("$1,234.50") == "1234.5" and tool.norm_answer("18.0") == "18" and tool.norm_answer("18.") == "18")
    check("numerals agree", all(module.numerals(s) == tool.numerals(s) for s in samples))
    check("numerals keep decimals, drop thousands separators",
          tool.numerals("$80,000 and 1.5 each, 3.") == ["80000", "1.5", "3"])

    def reference(a, b):
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            cur = [i]
            for j, cb in enumerate(b, 1):
                cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
            prev = cur
        return prev[-1]

    rng = random.Random(1899)
    ok_c = ok_t = True
    for _ in range(400):
        a = "".join(rng.choice("abc ") for _ in range(rng.randint(0, 40)))
        b = "".join(rng.choice("abc ") for _ in range(rng.randint(0, 40)))
        k = rng.randint(0, 12)
        want = min(reference(a, b), k + 1)
        ok_c = ok_c and module.bounded_distance(a, b, k) == want
        ok_t = ok_t and tool.bounded_distance(a, b, k) == want
    check("banded distance equals full Levenshtein, 400 random pairs (contract)", ok_c)
    check("banded distance equals full Levenshtein, 400 random pairs (cli)", ok_t)

    prefix, tail = tool.split_for_recall(it["prompt"], 400)
    check("recall: verbatim tail matches", module.recall_match(prefix, tail, tail, 900))
    check("recall: restated prefix is stripped first", module.recall_match(prefix, tail, prefix + tail, 900))
    check("recall: whitespace noise tolerated", module.recall_match(prefix, tail, "  " + tail.replace(" ", "  \n"), 900))
    check("recall: a paraphrase does not match",
          not module.recall_match(prefix, tail, "She sells what is left at the market each day for two dollars an egg. How many dollars per day?", 900))
    check("recall: empty continuation does not match", not module.recall_match(prefix, tail, "", 900))
    typo = tail[:10] + "X" + tail[11:]
    check("recall: one typo is inside 0.9", module.recall_match(prefix, tail, typo, 900))
    check("recall: one typo is outside 1.0", not module.recall_match(prefix, tail, typo, 1000))
    check("recall match agrees with cli", all(
        module.recall_match(*tool.split_for_recall(x["prompt"], 400), x["prompt"][len(x["prompt"]) * 400 // 1000:], 900)
        == tool.recall_match(*tool.split_for_recall(x["prompt"], 400), x["prompt"][len(x["prompt"]) * 400 // 1000:], 900)
        for x in ITEMS))
    check("every corpus item is long enough for the recall detector",
          all(module.recall_eligible(x["prompt"], 400) for x in ITEMS))
    check("a short item is not", not module.recall_eligible("What is 17 + 25?", 400))

    check("class vocabularies agree", tuple(module.CLASSES.keys()) == tool.CLASSES)
    orig, ans = it["prompt"], it["answer"]
    cases = [
        ("paraphrase", orig, ans, "identical"),
        ("paraphrase", orig.replace(" ", "  "), ans, "whitespace"),
        ("paraphrase", "How much does Janet make daily?", "19", "may not move"),
        ("numeral_substitution", orig.replace("Janet", "Maria"), "20", "no numeral"),
        ("numeral_substitution", orig.replace("16", "17"), ans, "must move"),
        ("vibes", "x", "1", "unknown"),
        ("format_shift", orig.replace(". ", ".\n"), ans, ""),
        ("numeral_substitution", orig.replace("16", "17"), "20", ""),
    ]
    check("precheck agrees and rules as documented", all(
        module.precheck_rewrite(c, orig, ans, p, a) == tool.precheck_rewrite(c, orig, ans, p, a)
        and (want in tool.precheck_rewrite(c, orig, ans, p, a) if want else tool.precheck_rewrite(c, orig, ans, p, a) == "")
        for c, p, a, want in cases))


def corpus(check):
    check.section("perturbation corpus")
    check("24 items, one rewrite each", len(ITEMS) == 24 and sorted(REWRITES) == ALL)
    check("every rewrite passes the deterministic gate and its own derivation",
          all(tool.validate_envelope(REWRITES[i], ITEMS[i]) == [] for i in ALL))
    check("every numeral_substitution carries a derivation",
          all(e.get("derivation") for e in REWRITES.values() if e["class"] == "numeral_substitution"))
    check("all five declared classes are exercised",
          {e["class"] for e in REWRITES.values()} == set(GSM_CLASSES))
    check("controls pass the deterministic gate: only a referee can stop them",
          all(tool.precheck_rewrite(e["class"], ITEMS[e["item_index"]]["prompt"], ITEMS[e["item_index"]]["answer"],
                                    e["prompt"], e["answer"]) == "" for e in CONTROLS))
    check("controls really do change the answer",
          all(tool.norm_answer(e["true_answer"]) != tool.norm_answer(e["answer"]) for e in CONTROLS))
    lying = dict(REWRITES[0], answer="37")
    check("a derivation that disagrees with the sworn answer is caught before any stake",
          any("derivation" in p for p in tool.validate_envelope(lying, ITEMS[0])))
    hostile = dict(REWRITES[0], derivation="__import__('os').system('true')")
    check("a derivation is arithmetic only", any("derivation" in p for p in tool.validate_envelope(hostile, ITEMS[0])))


def lifecycle(check, make):
    check.section("opening a claim")
    d, w = make()
    url = w.serve("https://capable.example/v1/chat/completions", pop.Capable(CORPUS))
    pub, chal, other = d.addr(1), d.addr(2), d.addr(3)

    def refused(match, **kw):
        base = dict(url=url)
        base.update(kw)
        items = base.pop("items", ITEMS)
        args = [
            base.get("subject", "m"), base["url"], base.get("score", 900), json.dumps(base.get("hashes", hashes_of(items))),
            base.get("rule", pop.SCORING_RULE), base.get("template", json.dumps(pop.TEMPLATE)), json.dumps(PARAMS),
            base.get("classes", ",".join(GSM_CLASSES)), base.get("delta", 250), base.get("recall", 150),
            base.get("min_items", 20), base.get("bond", BOND), base.get("stake", STAKE), json.dumps(base.get("extras", WINDOWS)),
        ]
        return d.reverts(pub, "open_claim", *args, value=base.get("value", BOND), match=match)

    check("http endpoint refused", refused("https", url="http://plain.example/v1"))
    check("score above 1000 refused", refused("per mille", score=1001))
    check("fewer items than min_items refused", refused("between min_items", items=ITEMS[:10]))
    check("min_items below the floor refused", refused("floor", min_items=4))
    check("unknown class refused", refused("unknown perturbation class", classes="paraphrase,vibes"))
    check("template without the item slot refused", refused("{{item}}", template=json.dumps({"user": "solve it"})))
    check("bond not attached refused", refused("bond not attached", value=BOND - 1))
    check("stake that outweighs the bond refused", refused("stake per item too high", stake=BOND))
    check("malformed hash refused", refused("sha256", hashes=["zz"] * 24))
    check("duplicate hash refused", refused("duplicate", hashes=[hashes_of(ITEMS)[0]] * 24))
    check("threshold of zero refused", refused("delta_threshold", delta=0))
    check("ten-second window refused", refused("windows", extras={"reveal_window_s": 10}))

    cid = open_claim(d, url)
    c = d.view("get_claim", cid)
    check("claim opens sealed with the full bond", c["status"] == "SEALED" and c["bond"] == BOND and len(c["item_hashes"]) == 24)
    check("spec hash is pinned", len(c["spec_hash"]) == 64)
    check("items are not readable while sealed", d.reverts(other, "get_item", cid, 0, match="sealed"))
    check("nothing is spent yet", not d.view("is_spent", c["item_hashes"][0]))
    cert = d.view("certificate", cid)
    check("an unchallenged claim reads UNCONTESTED, never CLEAN",
          cert["verdict"] == "UNCONTESTED" and not cert["contested"] and cert["score_status"] == "SEALED")

    check.section("who may do what")
    check("publisher cannot challenge themselves",
          d.reverts(pub, "challenge", cid, json.dumps(ALL), json.dumps(GSM_CLASSES), value=STAKE * 24, match="own claim"))
    check("subset under min_items refused",
          d.reverts(chal, "challenge", cid, json.dumps(ALL[:5]), json.dumps(GSM_CLASSES), value=STAKE * 5, match="min_items"))
    check("subset index out of range refused",
          d.reverts(chal, "challenge", cid, json.dumps(ALL[:23] + [99]), json.dumps(GSM_CLASSES), value=STAKE * 24, match="out of range"))
    check("class the claim did not allow refused",
          d.reverts(chal, "challenge", cid, json.dumps(ALL), json.dumps(["option_permutation"]), value=STAKE * 24, match="not allowed"))
    check("understaked challenge refused",
          d.reverts(chal, "challenge", cid, json.dumps(ALL), json.dumps(GSM_CLASSES), value=STAKE * 24 - 1, match="stake not attached"))
    check("reveal before any challenge refused", d.reverts(pub, "reveal_items", cid, reveal_payload(ITEMS), match="nothing to reveal"))

    hid = challenge(d, cid, value=STAKE * 24 + 500)
    check("overpaid stake is credited back, not kept", d.view("balance_of", d.hex(chal)) == 500)
    check("claim is now CHALLENGED and cannot be retired", d.view("get_claim", cid)["status"] == "CHALLENGED"
          and d.reverts(pub, "retire_claim", cid, match="cannot be retired"))
    check("second challenge while one is open refused",
          d.reverts(other, "challenge", cid, json.dumps(ALL), json.dumps(GSM_CLASSES), value=STAKE * 24, match="not open"))
    check("probe before reveal refused", d.reverts(other, "probe", hid, 0, "PINNED", "", match="not in trial"))
    check("only the publisher reveals", d.reverts(other, "reveal_items", cid, reveal_payload(ITEMS), match="only publisher"))
    tampered = [dict(it) for it in ITEMS]
    tampered[3]["answer"] = "261"
    check("a reveal that does not match the seal is refused",
          d.reverts(pub, "reveal_items", cid, reveal_payload(tampered), match="item 3 does not match"))
    check("a partial reveal is refused", d.reverts(pub, "reveal_items", cid, reveal_payload(ITEMS[:20]), match="every sealed item"))

    stale = reveal(d, cid)
    c = d.view("get_claim", cid)
    check("reveal moves the claim to TRIAL and burns the set", stale == 0 and c["status"] == "TRIAL" and c["burned_at"] > 0)
    item = d.view("get_item", cid, 0)
    check("items are now on chain in full", item["prompt"] == ITEMS[0]["prompt"] and item["answer"] == ITEMS[0]["answer"])

    check("only the challenger files rewrites",
          d.reverts(other, "probe", hid, 0, "REWRITE", tool.canonical_envelope(REWRITES[0]), match="only the challenger"))
    check("ADMIT before a rewrite refused", d.reverts(other, "probe", hid, 0, "ADMIT", "", match="nothing to admit"))
    check("unknown mode refused", d.reverts(other, "probe", hid, 0, "GUESS", "", match="mode must be"))
    wrong_class = dict(REWRITES[0], **{"class": "option_permutation"})
    check("rewrite in an undeclared class refused",
          d.reverts(chal, "probe", hid, 0, "REWRITE", tool.canonical_envelope(wrong_class), match="not declared"))
    lazy = dict(REWRITES[0], prompt=ITEMS[0]["prompt"])
    check("rewrite identical to the item refused without costing a stake",
          d.reverts(chal, "probe", hid, 0, "REWRITE", tool.canonical_envelope(lazy), match="identical")
          and d.view("get_challenge", hid)["stake_locked"] == STAKE * 24)
    check("rule with probes outstanding refused", d.reverts(other, "rule", hid, match="still have open probes"))

    d.call(chal, "probe", hid, 0, "REWRITE", tool.canonical_envelope(REWRITES[0]))
    check("one rewrite per item",
          d.reverts(chal, "probe", hid, 0, "REWRITE", tool.canonical_envelope(REWRITES[0]), match="one rewrite per item"))
    d.call(other, "probe", hid, 0, "PINNED", "")
    check("a pinned probe is answered once", d.reverts(other, "probe", hid, 0, "PINNED", "", match="already answered"))
    check("solvency held through every call", d.broken == [], d.broken[:1])
    d.close()


def three_populations(check, make):
    check.section("the court separates the three populations")
    verdicts = {}

    d, w = make()
    url = w.serve("https://memoriser.example/v1/chat/completions", pop.Memoriser(CORPUS))
    cid, hid, v = full_case(d, url)
    cert = d.view("certificate", cid)
    claim = d.view("get_claim", cid)
    verdicts["memoriser"] = v
    check("memoriser: CONTAMINATED on both detectors", v == "CONTAMINATED" and cert["reason"] == "GAP_AND_RECALL", (v, cert["reason"]))
    check("memoriser: pinned accuracy is perfect and the gap is wide",
          cert["pinned_milli"] == 1000 and cert["delta_milli"] >= 250, cert)
    check("memoriser: reproduces every held-out tail", cert["recall_milli"] == 1000 and cert["recall_probes"] == 24)
    numeral = sum(1 for e in REWRITES.values() if e["class"] == "numeral_substitution")
    check("memoriser: answers every numeral substitution with the old number",
          cert["stale_answers"] == numeral, (cert["stale_answers"], numeral))
    check("memoriser: bond goes to the challenger, stake comes back",
          d.view("balance_of", d.hex(d.addr(2))) == BOND + STAKE * 24 and claim["bond"] == 0 and claim["status"] == "CONTAMINATED")
    check("memoriser: certificate is final and the score is spent",
          cert["final"] and cert["score_status"] == "SPENT" and cert["items_burned"] == 24)
    check("memoriser: verdict recomputes offline from the published probes", offline_agrees(d, cid, hid))
    check("memoriser: a contaminated claim takes no further challenge",
          d.reverts(d.addr(3), "challenge", cid, json.dumps(ALL), json.dumps(GSM_CLASSES), value=STAKE * 24, match="not open"))
    check("memoriser: solvency held through every call", d.broken == [], d.broken[:1])
    d.close()

    d, w = make()
    url = w.serve("https://capable.example/v1/chat/completions", pop.Capable(CORPUS))
    cid, hid, v = full_case(d, url)
    cert = d.view("certificate", cid)
    claim = d.view("get_claim", cid)
    verdicts["capable"] = v
    check("capable: CLEAN", v == "CLEAN" and cert["reason"] == "", (v, cert))
    check("capable: both numbers under threshold with a full sample",
          cert["delta_milli"] < 250 and cert["recall_milli"] == 0 and cert["admissible_probes"] == 24, cert)
    check("capable: the sworn score reproduces", cert["score_sworn_milli"] - cert["pinned_milli"] < 250)
    check("capable: honest challenger pays nothing: full stake back",
          d.view("balance_of", d.hex(d.addr(2))) == STAKE * 24)
    check("capable: bond stays posted and the claim stays open to the next challenger",
          claim["status"] == "STANDING" and claim["bond"] == BOND and cert["challenges_survived"] == 1 and not cert["final"])
    check("capable: verdict recomputes offline", offline_agrees(d, cid, hid))
    check("capable: solvency held through every call", d.broken == [], d.broken[:1])
    d.close()

    d, w = make()
    url = w.serve("https://neither.example/v1/chat/completions", pop.Neither(CORPUS))
    cid, hid, v = full_case(d, url)
    cert = d.view("certificate", cid)
    verdicts["neither"] = v
    check("neither: UNSUPPORTED, the sworn number does not reproduce",
          v == "UNSUPPORTED" and cert["reason"] == "SCORE_NOT_REPRODUCED", (v, cert["reason"]))
    check("neither: no gap and no recall, so it is not called contaminated",
          cert["delta_milli"] < 250 and cert["recall_milli"] == 0 and cert["pinned_milli"] == 0)
    check("neither: a false oath costs the bond", d.view("balance_of", d.hex(d.addr(2))) == BOND + STAKE * 24)
    check("neither: verdict recomputes offline", offline_agrees(d, cid, hid))
    check("neither: solvency held through every call", d.broken == [], d.broken[:1])
    d.close()

    check("three subjects, three different verdicts", len(set(verdicts.values())) == 3, verdicts)

    d, w = make()
    url = w.serve("https://modest.example/v1/chat/completions", pop.Neither(CORPUS))
    cid, hid, verdict = full_case(d, url, score=120)
    check("a bad model that swears to a bad score is CLEAN: the court tries the oath, not the model",
          verdict == "CLEAN", verdict)
    d.close()


def registry(check, make):
    check.section("the spent registry")
    d, w = make()
    url = w.serve("https://capable.example/v1/chat/completions", pop.Capable(CORPUS))
    cid = open_claim(d, url)
    sealed = hashes_of(ITEMS)
    check("sealed: neither commitment nor text is in the registry",
          not d.view("is_spent", sealed[0]) and not d.view("is_spent", tool.content_hash(ITEMS[0]["prompt"])))
    hid = challenge(d, cid, subset=ALL[:20])
    check("challenged but unrevealed: still unspent", not d.view("is_spent", sealed[0]) and d.view("counts")["spent"] == 0)
    reveal(d, cid)
    check("revealed: every commitment is spent, including items the challenger did not pick",
          all(d.view("is_spent", h) for h in sealed))
    check("revealed: every item is spent by the hash of its text",
          all(d.view("is_spent", tool.content_hash(it["prompt"])) for it in ITEMS))
    check("the text is recognised through case and spacing changes",
          d.view("is_spent", tool.content_hash(ITEMS[5]["prompt"].upper().replace(" ", "   "))))
    check("a different item is not spent", not d.view("is_spent", tool.content_hash(ITEMS[5]["prompt"] + " extra")))
    info = d.view("spent_info", tool.content_hash(ITEMS[5]["prompt"]))
    check("registry names the claim that burned it", info["spent"] and info["claim_id"] == cid and info["burned_at"] > 0)
    page = d.view("registry", 0, 10)
    rest = d.view("registry", 10, 100)
    check("registry pages in burn order", page["total"] == 24 and len(page["rows"]) == 10 and len(rest["rows"]) == 14
          and page["rows"][0]["content_hash"] == tool.content_hash(ITEMS[0]["prompt"]))
    check("burning is at reveal, not at verdict", d.view("get_challenge", hid)["verdict"] == "PENDING")

    check("the same sealed hashes cannot open another claim",
          d.reverts(d.addr(4), "open_claim", "other/model", url, 900, json.dumps(sealed), pop.SCORING_RULE,
                    json.dumps(pop.TEMPLATE), json.dumps(PARAMS), ",".join(GSM_CLASSES), 250, 150, 20, BOND, STAKE,
                    json.dumps(WINDOWS), value=BOND, match="already spent"))

    # The same items under new salts get past open_claim: the seal hides them.
    # They do not get past the reveal.
    d.warp(60)
    again = resalt(ITEMS, "-second-try")
    cid2 = open_claim(d, url, items=again, sender=d.addr(4), subject="other/model@2026-10")
    hid2 = challenge(d, cid2, sender=d.addr(5))
    stale = d.call(d.addr(4), "reveal_items", cid2, reveal_payload(again))
    cert = d.view("certificate", cid2)
    check("re-salted spent items are caught at reveal", stale == 24, stale)
    check("a claim sworn on spent items is UNSUPPORTED on the spot",
          cert["verdict"] == "UNSUPPORTED" and cert["reason"] == "SET_ALREADY_SPENT" and cert["final"])
    check("its bond goes to the challenger with the whole stake",
          d.view("balance_of", d.hex(d.addr(5))) == BOND + STAKE * 24)
    check("the registry does not double count", d.view("counts")["spent"] == 24)
    check("the first burner stays on record", d.view("spent_info", tool.content_hash(ITEMS[0]["prompt"]))["claim_id"] == cid)
    check("solvency held through every call", d.broken == [], d.broken[:1])
    d.close()


def admissibility(check, make):
    check.section("admissibility: a rewrite that changes the question")
    d, w = make()
    subject = pop.Capable(CORPUS, miss=0)
    url = w.serve("https://capable.example/v1/chat/completions", subject)
    envelopes = dict(REWRITES)
    for env in CONTROLS:
        envelopes[env["item_index"]] = env
    bad = sorted(e["item_index"] for e in CONTROLS)

    cid = open_claim(d, url)
    hid = challenge(d, cid)
    reveal(d, cid)
    before = subject.calls
    out = run_trial(d, hid, envelopes=envelopes)
    check("all four controls are ruled INADMISSIBLE by framing one", all(out[i]["rewrite"] == "INADMISSIBLE" for i in bad))
    check("an inadmissible rewrite is never put to the model",
          subject.calls - before == 24 + 24 + 20, subject.calls - before)
    check("framing two is not spent on them", w.referee_calls == {1: 24, 2: 20}, w.referee_calls)
    check("each forfeits its slice to the publisher, at once",
          d.view("balance_of", d.hex(d.addr(1))) == STAKE * 4)
    verdict = d.call(d.addr(3), "rule", hid)
    cert = d.view("certificate", cid)
    check("the capable model stays CLEAN", verdict == "CLEAN" and cert["delta_milli"] == 0, (verdict, cert))
    check("certificate counts 20 admissible and 4 inadmissible",
          cert["admissible_probes"] == 20 and cert["inadmissible_rewrites"] == 4)
    check("challenger gets back exactly the admissible slices", d.view("balance_of", d.hex(d.addr(2))) == STAKE * 20)
    check("solvency held through every call", d.broken == [], d.broken[:1])
    d.close()

    # one referee framing talked around: the second one is what stands
    d, w = make()
    w.referee_fooled = {1}
    url = w.serve("https://capable.example/v1/chat/completions", pop.Capable(CORPUS, miss=0))
    cid = open_claim(d, url)
    hid = challenge(d, cid)
    reveal(d, cid)
    out = run_trial(d, hid, envelopes=envelopes)
    check("with framing one fooled, the controls reach the model and it is marked wrong",
          all(out[i]["rewrite"] == "WRONG" for i in bad), [out[i] for i in bad])
    check("framing two rejects all four", all(out[i]["admit"] == "INADMISSIBLE" for i in bad))
    verdict = d.call(d.addr(3), "rule", hid)
    cert = d.view("certificate", cid)
    check("the manufactured wrong answers do not reach the gap", verdict == "CLEAN" and cert["delta_milli"] == 0, cert)
    check("the griefer still loses the four slices", d.view("balance_of", d.hex(d.addr(1))) == STAKE * 4)
    d.close()

    # what the second framing is for: with both fooled, a gap is manufactured
    d, w = make()
    w.referee_fooled = {1, 2}
    url = w.serve("https://capable.example/v1/chat/completions", pop.Capable(CORPUS, miss=0))
    cid = open_claim(d, url, min_items=8, delta=150)
    hid = challenge(d, cid)
    reveal(d, cid)
    run_trial(d, hid, envelopes=envelopes)
    verdict = d.call(d.addr(3), "rule", hid)
    check("with both framings fooled, four changed questions convict a clean model at a 150‰ threshold",
          verdict == "CONTAMINATED" and d.view("certificate", cid)["delta_milli"] == 166, d.view("certificate", cid))
    d.close()


def omission(check, make):
    check.section("selective omission: dropping the items the model got wrong")
    d, w = make()
    # an honest model with a real error rate, failing independently on old and new wording
    subject = pop.Capable(CORPUS, miss=30, seed="k3")
    url = w.serve("https://modest.example/v1/chat/completions", subject)
    cid = open_claim(d, url, score=700, min_items=12)
    hid = challenge(d, cid)
    reveal(d, cid)
    # the challenger asks the public endpoint first, like anyone can
    right = []
    for i in ALL:
        status, body = subject.handle(json.dumps({"messages": [{"role": "user", "content": pop.TEMPLATE_HEAD + ITEMS[i]["prompt"]}]}))
        answer = json.loads(body)["choices"][0]["message"]["content"].split("ANSWER:")[-1].strip()
        if tool.norm_answer(answer) == tool.norm_answer(ITEMS[i]["answer"]):
            right.append(i)
    run_trial(d, hid, rewrite_only=set(right))
    probes = probes_of(d, hid)
    pairs = [p for p in probes if p["stage_c2"] == "ADMISSIBLE"]
    naive = sum(1 for p in pairs if p["rewrite"] == "WRONG") * 1000 // len(pairs)
    d.warp(WINDOWS["trial_window_s"] + 1)
    verdict = d.call(d.addr(3), "rule", hid)
    cert = d.view("certificate", cid)
    check("the challenger filed rewrites only where the model was right", len(pairs) == len(right) and 12 <= len(right) < 24, len(right))
    check("counted over those pairs alone, the gap would convict", naive >= 250, naive)
    check("counted the way the contract counts, it does not", verdict == "CLEAN" and cert["delta_milli"] < 250, (verdict, cert["delta_milli"]))
    check("the unfiled slices went to the publisher",
          d.view("balance_of", d.hex(d.addr(1))) == STAKE * (24 - len(right)))
    check("offline recomputation applies the same presumption", offline_agrees(d, cid, hid))
    check("solvency held through every call", d.broken == [], d.broken[:1])
    d.close()


def silence(check, make):
    check.section("an endpoint that does not answer")
    d, w = make()
    url = w.serve("https://dead.example/v1/chat/completions", pop.Dead(CORPUS))
    cid = open_claim(d, url)
    hid = challenge(d, cid)
    reveal(d, cid)
    out = run_trial(d, hid, retries=True)
    check("every model call comes back DEAD, twice", all(out[i]["pinned"] == "DEAD" and out[i]["recall"] == "DEAD" for i in ALL))
    check("a dead probe has two attempts and no third", d.reverts(d.addr(3), "probe", hid, 0, "PINNED", "", match="no attempts left"))
    verdict = d.call(d.addr(3), "rule", hid)
    cert = d.view("certificate", cid)
    claim = d.view("get_claim", cid)
    check("INCONCLUSIVE, and the reason is on the record", verdict == "INCONCLUSIVE" and cert["reason"] == "ENDPOINT_SILENT", cert)
    check("silence is not free: the publisher pays the challenger's costs out of the bond",
          claim["bond"] == BOND - STAKE * 24 and d.view("balance_of", d.hex(d.addr(2))) == STAKE * 24 * 2)
    check("the claim is still standing, its set burned, and can be tried again",
          claim["status"] == "STANDING" and cert["items_burned"] == 24 and not cert["final"])
    check("offline recomputation agrees", offline_agrees(d, cid, hid))
    check("solvency held through every call", d.broken == [], d.broken[:1])
    d.close()

    d, w = make()
    url = w.serve("https://flaky.example/v1/chat/completions", pop.Flaky(CORPUS))
    cid = open_claim(d, url)
    hid = challenge(d, cid)
    reveal(d, cid)
    crank = d.addr(3)
    first = d.call(crank, "probe", hid, 0, "PINNED", "")
    second = d.call(crank, "probe", hid, 0, "PINNED", "")
    check("a transient failure is retried once and then answers", first == "DEAD" and second == "RIGHT", (first, second))
    r1 = d.call(d.addr(2), "probe", hid, 0, "REWRITE", tool.canonical_envelope(REWRITES[0]))
    r2 = d.call(d.addr(2), "probe", hid, 0, "REWRITE", "")
    check("a dead rewrite answer is retried without refiling the rewrite", r1 == "DEAD" and r2 == "RIGHT", (r1, r2))
    check("the retry does not pay the referee again", w.referee_calls[1] == 1)
    d.close()

    d, w = make()
    url = w.serve("https://quiet.example/v1/chat/completions", pop.SelectiveSilence(CORPUS))
    cid = open_claim(d, url, score=1000)
    hid = challenge(d, cid)
    reveal(d, cid)
    out = run_trial(d, hid, retries=True)
    verdict = d.call(d.addr(3), "rule", hid)
    cert = d.view("certificate", cid)
    check("answers what it has seen, errors on what it has not",
          all(out[i]["pinned"] == "RIGHT" and out[i]["rewrite"] == "DEAD" for i in ALL))
    check("going quiet on the rewrites is read as an answer: CONTAMINATED",
          verdict == "CONTAMINATED" and cert["delta_milli"] == 1000 and cert["dead_probes"] == 24, cert)
    check("offline recomputation agrees", offline_agrees(d, cid, hid))
    d.close()


def text_answer_admissibility(check, make):
    check.section("text answer keys survive the real SDK boundary")
    for framing in (1, 2):
        d, w = make()
        items = [dict(prompt="Capital question %d: Name the capital city of France." % i,
                      answer="Paris", salt="text-adversary-%d" % i) for i in range(8)]
        cid = open_claim(d, "https://text.example/v1/chat/completions", items=items,
                         min_items=8, classes=["paraphrase"])
        hid = challenge(d, cid, subset=list(range(8)), classes=["paraphrase"])
        reveal(d, cid, items=items)
        # Both framings claim semantic validity; the blind solver supplies a
        # wrong text answer in the round under attack. The committed key wins.
        def llm(prompt):
            wrong = "BLIND SOLVE. REFEREE FRAMING: %d" % framing in prompt
            return json.dumps({"original_result": "London" if wrong else "Paris",
                               "rewrite_result": "Paris", "same_question": True})
        w._solve = llm
        w._referee = llm
        env = dict(version=tool.VERSION, **{"class": "paraphrase"},
                   prompt="For capital question zero, which city is France's capital?", answer="Paris")
        first = d.call(d.addr(2), "probe", hid, 0, "REWRITE", tool.canonical_envelope(env))
        result = first if framing == 1 else d.call(d.addr(3), "probe", hid, 0, "ADMIT", "")
        check("framing %d: a true Boolean cannot admit a wrong text result" % framing,
              result == "INADMISSIBLE", result)
        check("framing %d: rejected slice settles once with solvent accounting" % framing,
              d.view("balance_of", d.hex(d.addr(1))) == STAKE and d.broken == [])
        d.close()


def recall_coverage(check, make):
    check.section("CLEAN requires measured evidence from both detectors")
    for measured in (0, 19, 20):
        d, w = make()
        subject = pop.Capable(CORPUS, miss=0)
        reply = subject.reply
        measured_prefixes = {
            pop.RECALL_INSTRUCTION + tool.split_for_recall(it["prompt"], 400)[0]
            for it in ITEMS[:measured]
        }
        subject.reply = lambda user: (
            None if user.startswith(pop.RECALL_INSTRUCTION) and user not in measured_prefixes
            else reply(user)
        )
        url = w.serve("https://recall-coverage.example/v1/chat/completions", subject)
        cid = open_claim(d, url, score=1000)
        hid = challenge(d, cid)
        reveal(d, cid)
        run_trial(d, hid, retries=True)
        verdict = d.call(d.addr(3), "rule", hid)
        cert = d.view("certificate", cid)
        expected = "CLEAN" if measured >= 20 else "INCONCLUSIVE"
        reason = "" if measured >= 20 else "TOO_FEW_RECALL"
        check("%d recall results: %s" % (measured, expected),
              verdict == expected and cert["reason"] == reason
              and cert["recall_probes"] == measured and cert["admissible_probes"] == 24,
              cert)
        check("%d recall results: offline recomputation agrees" % measured,
              offline_agrees(d, cid, hid))
        check("%d recall results: solvency held" % measured, d.broken == [])
        d.close()

    d, w = make()
    items = [dict(prompt="Case %d: A baker has 12 loaves and sells 5. How many remain?" % i,
                  answer="7", salt="short-recall-%d" % i) for i in range(8)]
    rewrites = {i: dict(version=tool.VERSION, **{"class": "paraphrase"}, item_index=i,
                        prompt="Case %d: After selling 5 of 12 loaves, how many are left?" % i,
                        answer="7") for i in range(8)}
    corpus = dict(items=items, rewrites=rewrites, controls=[])
    w.corpus = corpus
    w.honest = {tool.rewrite_hash(e["class"], e["prompt"], e["answer"]) for e in rewrites.values()}
    url = w.serve("https://short-recall.example/v1/chat/completions", pop.Capable(corpus, miss=0))
    cid = open_claim(d, url, items=items, score=1000, min_items=8, classes=["paraphrase"])
    hid = challenge(d, cid, subset=list(range(8)), classes=["paraphrase"])
    reveal(d, cid, items=items)
    out = run_trial(d, hid, subset=list(range(8)), envelopes=rewrites)
    verdict = d.call(d.addr(3), "rule", hid)
    cert = d.view("certificate", cid)
    check("ineligible short tails are NA, never negative recall evidence",
          all(p["recall"] == "NA" for p in out.values()) and cert["recall_probes"] == 0)
    check("NA cannot produce a CLEAN certificate despite eight admitted pairs",
          verdict == "INCONCLUSIVE" and cert["reason"] == "TOO_FEW_RECALL"
          and cert["admissible_probes"] == 8, cert)
    check("NA result recomputes offline and preserves solvency",
          offline_agrees(d, cid, hid, list(range(8))) and d.broken == [])
    d.close()

    d, w = make()
    url = w.serve("https://missing-recall.example/v1/chat/completions", pop.Capable(CORPUS, miss=0))
    cid = open_claim(d, url, score=1000)
    hid = challenge(d, cid)
    reveal(d, cid)
    for i in ALL:
        d.call(d.addr(3), "probe", hid, i, "PINNED", "")
        d.call(d.addr(2), "probe", hid, i, "REWRITE", tool.canonical_envelope(REWRITES[i]))
        d.call(d.addr(3), "probe", hid, i, "ADMIT", "")
    check("unasked recall cannot be ruled before the deadline",
          d.reverts(d.addr(3), "rule", hid, match="open probes"))
    d.warp(WINDOWS["trial_window_s"] + 1)
    verdict = d.call(d.addr(3), "rule", hid)
    cert = d.view("certificate", cid)
    check("deadline expiry cannot turn missing recall into CLEAN",
          verdict == "INCONCLUSIVE" and cert["reason"] == "TOO_FEW_RECALL"
          and cert["recall_probes"] == 0 and cert["admissible_probes"] == 24, cert)
    check("missing recall recomputes offline and preserves solvency",
          offline_agrees(d, cid, hid) and d.broken == [])
    d.close()


def defaults_and_windows(check, make):
    check.section("windows: refusing to reveal, walking away")
    d, w = make()
    url = w.serve("https://memoriser.example/v1/chat/completions", pop.Memoriser(CORPUS))
    cid = open_claim(d, url)
    hid = challenge(d, cid)
    check("default cannot be claimed while the reveal window is open",
          d.reverts(d.addr(2), "claim_default", cid, match="still open"))
    d.warp(WINDOWS["reveal_window_s"] + 1)
    check("a late reveal is refused", d.reverts(d.addr(1), "reveal_items", cid, reveal_payload(ITEMS), match="window has closed"))
    out = d.call(d.addr(3), "claim_default", cid)
    cert = d.view("certificate", cid)
    check("a publisher who never opens the set loses by default",
          out == "DEFAULT" and cert["verdict"] == "DEFAULT" and cert["reason"] == "NO_REVEAL" and cert["final"])
    check("bond and stake both go to the challenger", d.view("balance_of", d.hex(d.addr(2))) == BOND + STAKE * 24)
    check("nothing was burned: the items were never shown",
          cert["items_burned"] == 0 and cert["score_status"] == "SEALED" and d.view("counts")["spent"] == 0)
    check("solvency held through every call", d.broken == [], d.broken[:1])
    d.close()

    d, w = make()
    url = w.serve("https://capable.example/v1/chat/completions", pop.Capable(CORPUS))
    cid = open_claim(d, url)
    hid = challenge(d, cid)
    reveal(d, cid)
    check("the publisher cannot rule early on an idle challenger",
          d.reverts(d.addr(1), "rule", hid, match="still have open probes"))
    d.warp(WINDOWS["trial_window_s"] + 1)
    check("probing after the trial window is refused", d.reverts(d.addr(3), "probe", hid, 0, "PINNED", "", match="window has closed"))
    verdict = d.call(d.addr(1), "rule", hid)
    cert = d.view("certificate", cid)
    check("a challenger who burns the set and walks away gets INCONCLUSIVE",
          verdict == "INCONCLUSIVE" and cert["reason"] == "TOO_FEW_ADMISSIBLE", cert)
    check("and forfeits the whole stake to the publisher whose set was burned",
          d.view("balance_of", d.hex(d.addr(1))) == STAKE * 24 and d.view("balance_of", d.hex(d.addr(2))) == 0)
    check("the bond is untouched", d.view("get_claim", cid)["bond"] == BOND)
    check("solvency held through every call", d.broken == [], d.broken[:1])
    d.close()


def standing(check, make):
    check.section("CLEAN is not final while the bond stands")
    d, w = make()
    subject = pop.Capable(CORPUS)
    url = w.serve("https://capable.example/v1/chat/completions", subject)
    cid = open_claim(d, url)
    hid = challenge(d, cid, subset=ALL[:20])
    reveal(d, cid)
    run_trial(d, hid, subset=ALL[:20])
    check("probing an item outside the challenged subset is refused",
          d.reverts(d.addr(3), "probe", hid, 23, "PINNED", "", match="not in the challenged subset"))
    v1 = d.call(d.addr(3), "rule", hid)
    check("first challenge, 20 items chosen blind: CLEAN", v1 == "CLEAN" and offline_agrees(d, cid, hid, ALL[:20]))
    check("ruling twice is refused", d.reverts(d.addr(3), "rule", hid, match="not in trial"))

    second = d.addr(5)
    check("a second challenger has seen the items, so cannot pick among them",
          d.reverts(second, "challenge", cid, json.dumps(ALL[:20]), json.dumps(GSM_CLASSES), value=STAKE * 20, match="challenged whole"))
    hid2 = challenge(d, cid, sender=second)
    check("the second challenge goes straight to trial: there is nothing left to reveal",
          d.view("get_challenge", hid2)["status"] == "TRIAL" and d.view("get_claim", cid)["status"] == "TRIAL")
    # same subject, now gone bad: the endpoint was swapped for a lookup table
    w.endpoints[url] = pop.Memoriser(CORPUS)
    run_trial(d, hid2, challenger=second)
    v2 = d.call(d.addr(3), "rule", hid2)
    cert = d.view("certificate", cid)
    check("a CLEAN certificate does not protect the next trial", v2 == "CONTAMINATED" and cert["verdict"] == "CONTAMINATED" and cert["final"])
    check("the certificate still says it survived one challenge first", cert["challenges_survived"] == 1 and cert["challenge_id"] == hid2)
    check("the second challenger takes the bond", d.view("balance_of", d.hex(second)) == BOND + STAKE * 24)
    check("solvency held through every call", d.broken == [], d.broken[:1])
    d.close()

    check.section("retiring a claim")
    d, w = make()
    url = w.serve("https://capable.example/v1/chat/completions", pop.Capable(CORPUS))
    cid = open_claim(d, url)
    check("only the publisher retires", d.reverts(d.addr(2), "retire_claim", cid, match="only publisher"))
    back = d.call(d.addr(1), "retire_claim", cid)
    cert = d.view("certificate", cid)
    check("retired without a challenge: bond back, certificate UNCONTESTED for good",
          back == BOND and cert["verdict"] == "UNCONTESTED" and cert["final"] and cert["bond_standing"] == 0)
    check("a retired claim takes no challenge",
          d.reverts(d.addr(2), "challenge", cid, json.dumps(ALL), json.dumps(GSM_CLASSES), value=STAKE * 24, match="not open"))

    d.close()

    d, w = make()
    url = w.serve("https://capable.example/v1/chat/completions", pop.Capable(CORPUS))
    cid, hid, verdict = full_case(d, url)
    d.call(d.addr(1), "retire_claim", cid)
    cert = d.view("certificate", cid)
    check("retired after CLEAN: verdict kept, bond no longer standing, marked final",
          cert["verdict"] == "CLEAN" and cert["final"] and cert["bond_standing"] == 0 and cert["state"] == "RETIRED")

    check.section("withdrawals")
    pub = d.addr(1)
    owed = d.view("balance_of", d.hex(pub))
    got = d.call(pub, "withdraw")
    check("withdraw pays exactly the credited balance", got == owed == BOND)
    check("and only once", d.reverts(pub, "withdraw", match="nothing to withdraw"))
    check("challenger withdraws the returned stake", d.call(d.addr(2), "withdraw") == STAKE * 24)
    check("the two transfers left the contract as native value", d.sent() == [BOND, STAKE * 24], d.sent())
    s = d.view("solvency")
    check("the contract holds nothing after everyone is paid", s["held"] == 0 and s["escrowed"] == 0 and s["credited"] == 0, s)
    check("solvency held through every call", d.broken == [], d.broken[:1])
    d.close()


def run_all(make, label: str, module=None, quiet: bool = False) -> Checker:
    check = Checker(label, quiet)
    if module is not None:
        pure_functions(check, module)
        corpus(check)
    lifecycle(check, make)
    three_populations(check, make)
    registry(check, make)
    admissibility(check, make)
    omission(check, make)
    silence(check, make)
    recall_coverage(check, make)
    text_answer_admissibility(check, make)
    defaults_and_windows(check, make)
    standing(check, make)
    numeric_scoring(check, make)
    return check
