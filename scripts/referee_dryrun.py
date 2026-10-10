#!/usr/bin/env python3
"""Run the admissibility referee over the perturbation corpus before any of it
goes near Bradbury.

The prompts are the contract's own: this loads contracts/impeach.py on the local
stub and replaces only the LLM call. Every rewrite in examples/rewrites should
come back ADMISSIBLE under both framings; every control in examples/controls
should be stopped by at least one. Anything else is a reason to fix the rewrite
or the framing before a stake rides on it.

    export OPENAI_BASE_URL=https://api.openai.com/v1   # any OpenAI-shaped endpoint
    export OPENAI_API_KEY=…
    export REFEREE_MODEL=…
    python3 scripts/referee_dryrun.py --out runs/referee-dryrun.json

One model is one judge, not a validator set. This run tells you whether the
corpus is sane; it says nothing about how often five independent validators
agree. Jastrow is the instrument for that.
"""

import argparse
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "test"))

import population as pop  # noqa: E402
from drivers import StubDriver  # noqa: E402
from local_env import load_local_env, model_key  # noqa: E402


def live_llm(prompt: str) -> str:
    base = os.environ["OPENAI_BASE_URL"].rstrip("/")
    body = json.dumps({
        "model": os.environ["REFEREE_MODEL"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": int(os.environ.get("REFEREE_MAX_TOKENS", "2048")),
    }).encode("utf-8")
    headers = {"content-type": "application/json"}
    if model_key():
        headers["authorization"] = "Bearer " + model_key()
    req = urllib.request.Request(
        base + "/chat/completions",
        data=body,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"]


def main() -> int:
    load_local_env()
    if os.environ.get("OPENROUTER_API_KEY"):
        os.environ.setdefault("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    ap = argparse.ArgumentParser(prog="referee_dryrun")
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "referee-dryrun.json"))
    ap.add_argument("--claim", default="", help="explicit claim for an additional demonstration corpus")
    ap.add_argument("--controls", default="", help="control directory for that corpus")
    ap.add_argument("--print-prompts", action="store_true", help="print the two prompts for the first rewrite and exit")
    args = ap.parse_args()

    if args.claim:
        from run_case import load_claim, load_rewrites
        claim = load_claim(args.claim)
        if not args.controls:
            raise SystemExit("--controls is required with --claim")
        controls = [json.load(open(os.path.join(args.controls, name), encoding="utf-8"))
                    for name in sorted(os.listdir(args.controls)) if name.endswith(".json")]
        corpus = {"items": claim["_items"], "rewrites": load_rewrites(claim), "controls": controls}
    else:
        corpus = pop.load_corpus()
    world = pop.World(corpus)
    d = StubDriver(world)

    if args.print_prompts:
        seen = []
        d.gl.nondet.handler = lambda prompt: (seen.append(prompt), '{"same_question": true}')[1]
    else:
        for name in ("OPENAI_BASE_URL", "REFEREE_MODEL"):
            if not os.environ.get(name):
                raise SystemExit("set %s (see the docstring)" % name)
        d.gl.nondet.handler = live_llm

    rows = []
    cases = [(env, "ADMISSIBLE") for _, env in sorted(corpus["rewrites"].items())]
    cases += [(env, "INADMISSIBLE") for env in corpus["controls"]]
    if args.print_prompts:
        cases = cases[:1]
    for env, expect in cases:
        item = corpus["items"][env["item_index"]]
        rulings = [
            d.contract._referee(f, env["class"], item["prompt"], item["answer"], env["prompt"], env["answer"])
            for f in (1, 2)
        ]
        both = "ADMISSIBLE" if rulings == ["ADMISSIBLE", "ADMISSIBLE"] else "INADMISSIBLE"
        rows.append({"item_index": env["item_index"], "class": env["class"], "expect": expect,
                     "framing_1": rulings[0], "framing_2": rulings[1], "ok": both == expect})
        if not args.print_prompts:
            print("%s item %2d %-22s f1=%s f2=%s" % ("ok  " if both == expect else "MISS", env["item_index"], env["class"], *rulings))

    if args.print_prompts:
        print(("\n" + "=" * 78 + "\n").join(seen))
        return 0

    wrong = [r for r in rows if not r["ok"]]
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as output:
        json.dump({"model": os.environ["REFEREE_MODEL"], "rows": rows}, output, indent=1)
    print("%d of %d as expected -> %s" % (len(rows) - len(wrong), len(rows), args.out))
    return 1 if wrong else 0


if __name__ == "__main__":
    raise SystemExit(main())
