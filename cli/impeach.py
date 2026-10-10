#!/usr/bin/env python3
"""impeach — the command line half of the court.

    impeach seal      items.json                 hashes to pass to open_claim
    impeach check     <hash> | --text "…"        has this item been burned?
    impeach envelope  rewrites/*.json --items …  lint rewrites before they cost a stake
    impeach recompute case.json                  rebuild a verdict from published probes
    impeach probe     <challenge> <item> <mode>  one probe round
    impeach rule      <challenge>                compute Δ and R, settle

`check` can use a published snapshot with this file alone. Live contract reads
also require scripts/genlayer_write.mjs and the installed GenLayer SDK.

The hashing, the flattening and the edit distance below are copies of the ones
in contracts/impeach.py. test/run_tests.py holds the two equal.
"""

import argparse
import ast
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.request

VERSION = "impeach/1"

MAX_ITEM_CHARS = 2000
MAX_ANSWER_CHARS = 200
MIN_RECALL_TAIL = 48
RECALL_COMPARE_CAP = 400

CLASSES = (
    "paraphrase",
    "numeral_substitution",
    "option_permutation",
    "distractor_swap",
    "entity_rename",
    "unit_change",
    "format_shift",
)
ANSWER_FIXED = ("paraphrase", "format_shift")

_SPACE = (" ", "\t", "\n", "\r", "\x0b", "\x0c", "\u00a0")
_QUOTES = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'}


# ------------------------------------------------------------ mirrored core


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _part(text: str) -> str:
    return "%d:%s" % (len(text.encode("utf-8")), text)


def item_commitment(prompt: str, answer: str, salt: str) -> str:
    return _sha(VERSION + "/item\n" + _part(salt) + "\n" + _part(answer) + "\n" + _part(prompt))


def squash(text: str) -> str:
    out = []
    gap = False
    for ch in text:
        if ch in _SPACE:
            gap = True
            continue
        if gap and out:
            out.append(" ")
        gap = False
        out.append(ch)
    return "".join(out)


def flatten(text: str) -> str:
    out = []
    for ch in squash(text):
        if ch in _QUOTES:
            ch = _QUOTES[ch]
        o = ord(ch)
        if 65 <= o <= 90:
            ch = chr(o + 32)
        out.append(ch)
    return "".join(out)


def content_hash(prompt: str) -> str:
    return _sha(VERSION + "/content\n" + flatten(prompt))


def norm_answer(text: str) -> str:
    out = []
    for ch in flatten(text):
        if ch in ("$", ","):
            continue
        out.append(ch)
    s = squash("".join(out))
    while s.endswith("."):
        s = s[:-1]
    if "." in s:
        head, _, tail = s.partition(".")
        digits = head[1:] if head.startswith("-") else head
        if digits.isdigit() and tail.isdigit() and digits.isascii() and tail.isascii():
            tail = tail.rstrip("0")
            s = head + ("." + tail if tail else "")
    return s


def numerals(text: str) -> list:
    out = []
    cur = ""
    n = len(text)
    for i in range(n):
        ch = text[i]
        if "0" <= ch <= "9":
            cur += ch
        elif ch in (",", ".") and cur and i + 1 < n and "0" <= text[i + 1] <= "9":
            if ch == ".":
                cur += ch
        else:
            if cur:
                out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return out


def bounded_distance(a: str, b: str, k: int) -> int:
    la = len(a)
    lb = len(b)
    if la - lb > k or lb - la > k:
        return k + 1
    big = k + 1
    prev = [j if j <= k else big for j in range(lb + 1)]
    for i in range(1, la + 1):
        lo = max(1, i - k)
        hi = min(lb, i + k)
        cur = [big] * (lb + 1)
        if i <= k:
            cur[0] = i
        best = cur[0]
        ca = a[i - 1]
        for j in range(lo, hi + 1):
            v = min(prev[j - 1] + (0 if ca == b[j - 1] else 1), prev[j] + 1, cur[j - 1] + 1, big)
            cur[j] = v
            if v < best:
                best = v
        if best > k:
            return big
        prev = cur
    return prev[lb] if prev[lb] <= k else big


def split_for_recall(prompt: str, prefix_milli: int) -> tuple:
    cut = len(prompt) * prefix_milli // 1000
    return (prompt[:cut], prompt[cut:])


def recall_eligible(prompt: str, prefix_milli: int) -> bool:
    return len(squash(split_for_recall(prompt, prefix_milli)[1])) >= MIN_RECALL_TAIL


def recall_match(prefix: str, tail: str, continuation: str, similarity_milli: int) -> bool:
    want = squash(tail)[:RECALL_COMPARE_CAP]
    got = squash(continuation)
    head = squash(prefix)
    if head and got.startswith(head):
        got = squash(got[len(head):])
    got = got[: len(want)]
    longest = max(len(want), len(got))
    if longest == 0:
        return False
    k = (1000 - similarity_milli) * longest // 1000
    return bounded_distance(want, got, k) <= k


def rewrite_hash(cls: str, prompt: str, answer: str) -> str:
    return _sha(VERSION + "/rewrite\n" + _part(cls) + "\n" + _part(answer) + "\n" + _part(prompt))


def precheck_rewrite(cls: str, original: str, answer: str, prompt: str, new_answer: str) -> str:
    if cls not in CLASSES:
        return "unknown perturbation class"
    if len(prompt) == 0 or len(prompt) > MAX_ITEM_CHARS:
        return "rewrite prompt empty or too large"
    if len(new_answer) == 0 or len(new_answer) > MAX_ANSWER_CHARS:
        return "rewrite answer empty or too large"
    if prompt == original:
        return "rewrite is identical to the pinned item"
    if cls != "format_shift" and flatten(prompt) == flatten(original):
        return "only whitespace moved; that is a format_shift"
    same = norm_answer(new_answer) == norm_answer(answer)
    if cls in ANSWER_FIXED and not same:
        return "this class may not move the answer"
    if cls == "numeral_substitution":
        if numerals(prompt) == numerals(original):
            return "no numeral was substituted"
        if same:
            return "numeral_substitution must move the answer"
    return ""


def _milli(part: int, whole: int) -> int:
    return part * 1000 // whole if whole > 0 else 0


def _signed_milli(a: int, b: int, whole: int) -> int:
    if whole <= 0:
        return 0
    if a >= b:
        return (a - b) * 1000 // whole
    return -((b - a) * 1000 // whole)


def rule_offline(terms: dict, probes: list) -> dict:
    """The verdict arithmetic of Impeach.rule, on published probe records.

    `terms` needs score_milli, delta_threshold, recall_threshold, min_items.
    Each probe is what get_probe returns. Anyone holding a snapshot can run
    this and disagree with the certificate in public.
    """
    n_live = pinned_right = rewrite_right = 0
    admissible = inadmissible = stale = dead = dead_pinned = 0
    recall_n = recall_hits = 0
    for p in probes:
        if not p.get("touched", True):
            continue
        if p.get("stage_c1") == "INADMISSIBLE" or p.get("stage_c2") == "INADMISSIBLE":
            inadmissible += 1
        pair = p.get("stage_c1") == "ADMISSIBLE" and p.get("stage_c2") == "ADMISSIBLE"
        if p.get("recall") == "MATCH":
            recall_n += 1
            recall_hits += 1
        elif p.get("recall") == "MISS":
            recall_n += 1
        elif p.get("recall") == "DEAD":
            dead += 1
        if p.get("pinned") == "DEAD":
            dead += 1
            dead_pinned += 1
        if p.get("pinned") not in ("RIGHT", "WRONG"):
            continue
        n_live += 1
        if p["pinned"] == "RIGHT":
            pinned_right += 1
        if pair and p.get("rewrite") in ("RIGHT", "WRONG", "DEAD"):
            admissible += 1
            if p["rewrite"] == "RIGHT":
                rewrite_right += 1
            if p["rewrite"] == "DEAD":
                dead += 1
            if p.get("stale"):
                stale += 1
        else:
            rewrite_right += 1

    min_items = int(terms["min_items"])
    delta = _signed_milli(pinned_right, rewrite_right, n_live)
    recall = _milli(recall_hits, recall_n)
    shortfall = int(terms["score_milli"]) - _milli(pinned_right, n_live)
    gap_trips = admissible >= min_items and delta >= int(terms["delta_threshold"])
    recall_trips = recall_n >= min_items and recall >= int(terms["recall_threshold"])

    if gap_trips or recall_trips:
        verdict = "CONTAMINATED"
        reason = "GAP_AND_RECALL" if gap_trips and recall_trips else ("GAP" if gap_trips else "RECALL")
    elif n_live >= min_items and shortfall >= int(terms["delta_threshold"]):
        verdict, reason = "UNSUPPORTED", "SCORE_NOT_REPRODUCED"
    elif admissible >= min_items:
        verdict, reason = "CLEAN", ("" if recall_n >= min_items else "RECALL_NOT_MEASURED")
    elif n_live < min_items and n_live + dead_pinned >= min_items:
        verdict, reason = "INCONCLUSIVE", "ENDPOINT_SILENT"
    else:
        verdict, reason = "INCONCLUSIVE", "TOO_FEW_ADMISSIBLE"

    return {
        "verdict": verdict,
        "reason": reason,
        "delta_milli": delta,
        "recall_milli": recall,
        "pinned_milli": _milli(pinned_right, n_live),
        "rewrite_milli": _milli(rewrite_right, n_live),
        "admissible_probes": admissible,
        "inadmissible_rewrites": inadmissible,
        "stale_answers": stale,
        "dead_probes": dead,
        "recall_probes": recall_n,
        "items_probed": n_live,
    }


# ------------------------------------------------------------------- envelope


def canonical_envelope(env: dict) -> str:
    """What is sent on chain: the four fields the contract reads, nothing else.
    Derivations and notes stay in the repository."""
    return json.dumps(
        {"version": env["version"], "class": env["class"], "prompt": env["prompt"], "answer": env["answer"]},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def check_derivation(env: dict) -> str:
    """A rewrite that moves numbers carries the arithmetic that produced its
    answer. Only integer arithmetic is evaluated."""
    expr = env.get("derivation")
    if not expr:
        return ""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return "derivation is not an expression"
    allowed = (
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Add, ast.Sub,
        ast.Mult, ast.FloorDiv, ast.USub, ast.Mod,
    )
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            return "derivation may only use integers and + - * // %"
        if isinstance(node, ast.Constant) and type(node.value) is not int:
            return "derivation may only use integers"
    value = eval(compile(tree, "<derivation>", "eval"), {"__builtins__": {}})  # noqa: S307
    if norm_answer(str(value)) != norm_answer(str(env.get("answer", ""))):
        return "derivation gives %s, envelope swears to %s" % (value, env.get("answer"))
    return ""


def validate_envelope(env: dict, item: dict) -> list:
    problems = []
    if env.get("version") != VERSION:
        problems.append("version must be " + VERSION)
    for field in ("class", "prompt", "answer"):
        if not isinstance(env.get(field), str) or not env.get(field):
            problems.append("missing " + field)
    if problems:
        return problems
    reason = precheck_rewrite(env["class"], item["prompt"], item["answer"], env["prompt"], env["answer"])
    if reason:
        problems.append(reason)
    reason = check_derivation(env)
    if reason:
        problems.append(reason)
    return problems


# ---------------------------------------------------------------------- chain


def extract_json(text: str):
    """`genlayer call` prints a JS-ish literal after a `Result:` line."""
    markers = list(re.finditer(r"(?m)^Result:\s*$", text))
    if not markers:
        stripped = text.strip()
        if stripped in ("true", "false"):
            return stripped == "true"
        return json.loads(stripped) if stripped[:1] in ("{", "[") else None
    payload = text[markers[-1].end():]
    payload = re.split(r"\n\s*[✔✖]", payload, maxsplit=1)[0].strip()
    if payload in ("true", "false"):
        return payload == "true"
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        quoted = re.sub(r"([,{]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', payload)
        quoted = re.sub(r"\btrue\b", "True", quoted)
        quoted = re.sub(r"\bfalse\b", "False", quoted)
        quoted = re.sub(r"\bnull\b", "None", quoted)
        return ast.literal_eval(quoted)


def chain_call(address: str, method: str, args: list, rpc: str = "", timeout: int = 60):
    bridge = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "scripts", "genlayer_write.mjs")
    command = ["node", bridge, "--read", address, method,
               "--args-json", json.dumps(args, ensure_ascii=False)]
    if rpc:
        command += ["--rpc", rpc]
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError((result.stdout + result.stderr).strip())
    return json.loads(result.stdout)


def chain_write_command(address: str, method: str, args: list, rpc: str = "") -> list:
    command = ["genlayer", "write", address, method, "--args"] + [str(a) for a in args]
    if rpc:
        command += ["--rpc", rpc]
    return command


# ------------------------------------------------------------------- commands


def load_items(path: str) -> list:
    with open(path, encoding="utf-8") as source:
        data = json.load(source)
    return data["items"] if isinstance(data, dict) else data


def cmd_seal(args) -> int:
    items = load_items(args.path)
    sealed = []
    for i, it in enumerate(items):
        if not it.get("salt"):
            print("warning: item %d has no salt; a public item is recognisable by its hash" % i, file=sys.stderr)
        sealed.append(
            {
                "index": i,
                "item_hash": item_commitment(it["prompt"], it["answer"], it.get("salt", "")),
                "content_hash": content_hash(it["prompt"]),
                "recall_eligible": recall_eligible(it["prompt"], args.prefix),
            }
        )
    out = {
        "format": "impeach-sealed/1",
        "count": len(sealed),
        "item_hashes": [s["item_hash"] for s in sealed],
        "items": sealed,
    }
    text = json.dumps(out, indent=1)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(text + "\n")
        print("%d items sealed -> %s" % (len(sealed), args.out))
    else:
        print(text)
    return 0


def cmd_check(args) -> int:
    if args.text is not None:
        key = content_hash(args.text)
        label = "content hash"
    elif args.hash:
        key = args.hash.lower().removeprefix("0x")
        label = "hash"
    else:
        print("give a hash or --text", file=sys.stderr)
        return 2
    if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        print("not a sha256 hex digest: " + key, file=sys.stderr)
        return 2

    info = None
    if args.address:
        info = chain_call(args.address, "spent_info", [key], args.rpc)
        source = args.address
    else:
        source = args.snapshot
        if source.startswith("http://") or source.startswith("https://"):
            with urllib.request.urlopen(source, timeout=30) as r:
                snap = json.loads(r.read().decode("utf-8"))
        else:
            snap = json.load(open(source, encoding="utf-8"))
        if snap.get("provenance") != "bradbury":
            print("note: %s is a %s snapshot, not a chain record" % (source, snap.get("provenance")), file=sys.stderr)
        for row in snap.get("registry", []):
            if key in (row.get("content_hash"), row.get("item_hash")):
                info = {"spent": True, "claim_id": row.get("claim_id"), "burned_at": row.get("burned_at")}
                break
        if info is None:
            info = {"spent": False}

    if args.json:
        print(json.dumps({"hash": key, "source": source, **info}))
    elif info.get("spent"):
        print("SPENT   %s %s" % (label, key))
        print("        burned in claim %s at %s" % (info.get("claim_id"), info.get("burned_at")))
        print("        a score measured on this item is no longer evidence of anything")
    else:
        print("UNSPENT %s %s" % (label, key))
        print("        not in the registry at " + source)
    # exit status is the answer, so the command can gate a CI job
    return 1 if info.get("spent") else 0


def cmd_envelope(args) -> int:
    items = load_items(args.items)
    bad = 0
    for path in args.paths:
        env = json.load(open(path, encoding="utf-8"))
        idx = env.get("item_index")
        if type(idx) is not int or idx < 0 or idx >= len(items):
            print("FAIL %s: item_index out of range" % path)
            bad += 1
            continue
        problems = validate_envelope(env, items[idx])
        if problems:
            bad += 1
            print("FAIL %s: %s" % (path, "; ".join(problems)))
        else:
            print("ok   %s  %s  %s" % (rewrite_hash(env["class"], env["prompt"], env["answer"])[:12], env["class"], path))
    return 1 if bad else 0


def cmd_recompute(args) -> int:
    snap = json.load(open(args.path, encoding="utf-8"))
    bad = 0
    for case in snap.get("cases", []):
        terms = {
            "score_milli": case["claim"]["score_milli"],
            "delta_threshold": case["claim"]["delta_threshold"],
            "recall_threshold": case["claim"]["recall_threshold"],
            "min_items": case["claim"]["min_items"],
        }
        mine = rule_offline(terms, case["probes"])
        cert = case["certificate"]
        diff = [k for k in mine if cert.get(k) != mine[k]]
        tag = "ok  " if not diff else "DIFF"
        print("%s claim %s  %s  Δ=%d‰ R=%d‰ n=%d" % (
            tag, case["claim"]["claim_id"], mine["verdict"], mine["delta_milli"],
            mine["recall_milli"], mine["admissible_probes"],
        ))
        for k in diff:
            bad += 1
            print("     %s: certificate says %r, probes give %r" % (k, cert.get(k), mine[k]))
    return 1 if bad else 0


def cmd_probe(args) -> int:
    payload = ""
    if args.mode == "REWRITE" and args.envelope:
        env = json.load(open(args.envelope, encoding="utf-8"))
        if args.items:
            problems = validate_envelope(env, load_items(args.items)[args.item])
            if problems:
                for p in problems:
                    print("error: " + p, file=sys.stderr)
                return 2
        payload = canonical_envelope(env)
    command = chain_write_command(
        args.address or "$CONTRACT", "probe", [args.challenge, args.item, args.mode, payload], args.rpc
    )
    if args.dry_run or not args.address:
        print(" ".join(shlex.quote(c) if c != "$CONTRACT" else c for c in command))
        return 0
    return subprocess.run(command).returncode


def cmd_rule(args) -> int:
    command = chain_write_command(args.address or "$CONTRACT", "rule", [args.challenge], args.rpc)
    if args.dry_run or not args.address:
        print(" ".join(shlex.quote(c) if c != "$CONTRACT" else c for c in command))
        return 0
    return subprocess.run(command).returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="impeach", description="A court for benchmark scores.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("seal", help="hash an item set for open_claim")
    s.add_argument("path")
    s.add_argument("--out", default="")
    s.add_argument("--prefix", type=int, default=400, help="recall prefix, per mille")
    s.set_defaults(fn=cmd_seal)

    c = sub.add_parser("check", help="ask the spent registry about one item")
    c.add_argument("hash", nargs="?", default="")
    c.add_argument("--text", default=None, help="the item text; hashed locally, never sent anywhere")
    c.add_argument("--address", default=os.environ.get("IMPEACH_CONTRACT", ""))
    c.add_argument("--rpc", default="")
    c.add_argument("--snapshot", default=os.environ.get("IMPEACH_SNAPSHOT", "web/case.json"))
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_check)

    e = sub.add_parser("envelope", help="lint rewrite envelopes against their items")
    e.add_argument("paths", nargs="+")
    e.add_argument("--items", required=True)
    e.set_defaults(fn=cmd_envelope)

    r = sub.add_parser("recompute", help="rebuild verdicts from a published snapshot")
    r.add_argument("path")
    r.set_defaults(fn=cmd_recompute)

    p = sub.add_parser("probe", help="run one probe round")
    p.add_argument("challenge", type=int)
    p.add_argument("item", type=int)
    p.add_argument("mode", choices=("PINNED", "REWRITE", "ADMIT", "RECALL"))
    p.add_argument("--envelope", default="")
    p.add_argument("--items", default="")
    p.add_argument("--address", default=os.environ.get("IMPEACH_CONTRACT", ""))
    p.add_argument("--rpc", default="")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_probe)

    u = sub.add_parser("rule", help="compute the verdict and settle")
    u.add_argument("challenge", type=int)
    u.add_argument("--address", default=os.environ.get("IMPEACH_CONTRACT", ""))
    u.add_argument("--rpc", default="")
    u.add_argument("--dry-run", action="store_true")
    u.set_defaults(fn=cmd_rule)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
