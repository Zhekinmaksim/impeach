# Impeach — submission

**One line.** A GenLayer court for benchmark scores: validators test bonded
claims with semantic rewrites and verbatim recall, then publish a verdict and
an irreversible registry of revealed test items.

The 16 October steward corrections are documented in
[REVIEW-FIXES.md](REVIEW-FIXES.md). Revision `impeach/1.1` is deployed at
[the corrected Bradbury court](https://explorer-bradbury.genlayer.com/address/0xCB67936d0b00b82Ea73611b3C8353a21EBdc7261).
The corrected real-model case is native FINALIZED / CLEAN with all 24 admitted
pairs and 24 measured recall results. The retired certificate is final; its
Δ and R are both zero. The new scripted control is still being completed.

## What it is

A publisher swears to a score and bonds it, committing only hashes of the
evaluation items. A challenger stakes that the score came from memory. The
validator set asks the model each sealed question, a rewritten version of it,
and to continue the first 40% of it. The contract rules on two numbers and
writes a certificate another contract can read.

## Why it needs GenLayer

A harness run by the publisher measures what the publisher chose to measure. A
harness run by the challenger is no more falsifiable. The judgment needs judges
neither side picked, applying terms frozen before the items were revealed, each
calling the model themselves. The resulting certificate exposes settled answers
and failed consensus rounds under the same frozen terms.

## The mechanism that is new

**Evaluation items are consumable.** A contamination case cannot be tried
without showing the items, and showing them contaminates them for everyone. So
the reveal and the burn are one transaction, and the spent registry is the
output other people use: `is_spent(hash)` for contracts, `impeach check` for
humans and CI.

## What is reused from Jastrow and Suborn

- Two referee framings that must agree before a rewrite counts (Suborn stage B).
- `INCONCLUSIVE` retains the bond and settles stake according to the referee decisions.
- Pull-based balances, one `withdraw`, a solvency view asserted after every call.
- Record the hash at submit, build the report from receipts later.

## Equivalence principles

| where | principle | on what |
| --- | --- | --- |
| numeric answer marking | `strict_eq` | deterministic final-line parsing and canonical numeric equality |
| legacy semantic answer marking | `prompt_comparative` | matching status and correctness, and equivalent extracted answers; ignores prose |
| admissibility | `prompt_comparative` plus deterministic key checks | two blind solutions and the class decision in each of two framings; both solutions must match their respective committed keys |
| verbatim recall | `strict_eq` | an integer bucket from bounded edit distance; no LLM |

Each validator calls the endpoint itself. A round that fails consensus does not
apply a probe result. Receipts distinguish disagreement, timeouts and execution
violations; these failures alone do not establish what the model answered.

## The consumer outside the project

`certificate(claim_id)` and `is_spent(item_hash)` are views meant for an agent
marketplace, a grant committee or another contract. `cli/impeach.py check`
uses the installed GenLayer SDK and exits 1 when an item is spent.

## What was decided beyond the spec

Six verdict states instead of three, a default judgment, a presumption that
closes selective omission, and where forfeited stake goes. Each with its reason
and its test in `DECISIONS.md`.

## Honest limits

- Only subjects that answer a public HTTPS endpoint without a key.
- Δ is evidence, not proof; the certificate carries raw counts.
- Burning is irreversible, whatever the verdict.
- The original GSM8K demo and the current synthetic regression corpora are public.
  Reusing a disclosed corpus on a corrected deployment does not make it secret.
- The lookup-table control is explicitly scripted; its conviction is a control,
  not a finding about a real LLM.
- `CLEAN` requires at least `min_items` admitted pairs and measured recall results.
  Missing, `NA` and `DEAD` recall cannot support a clean certificate.

## Evidence

- Website: [impeach.click](https://impeach.click).
- Source: [Zhekinmaksim/impeach](https://github.com/Zhekinmaksim/impeach).
- Corrections, regression coverage and native status: [REVIEW-FIXES.md](REVIEW-FIXES.md).
- Corrected deployment: [receipt](runs/review-deploy-receipt.json) and
  [source/protocol verification](runs/review-protocol-and-source-preflight.json).
- Real-model claim/challenge `1/1`: [frozen claim](calibration/claim-review-live.json),
  [transaction journal](runs/review-live.jsonl).
- Scripted control claim/challenge `0/0`: [frozen claim](calibration/claim-review-scripted.json);
  its full corrected native certificate is pending.
- Local calibration: [72 real subject responses](runs/review-live-rehearsal-audit.json)
  and [112-response exact referee replay](runs/review-referee-replay.json).
  Neither is presented as a native verdict.

The public site displays the corrected real-model native snapshot. Its local
recomputation agrees with the on-chain certificate. The previous site record is
preserved in [the historical snapshot](runs/review-previous-site-case.json).

## Review path

1. Open https://impeach.click and inspect claim 1, the real Llama model.
2. Inspect the 24 original/rewrite pairs and both admission decisions per item.
3. Open the ruling: CLEAN, admitted 24, recall 24, Δ=0‰, R=0‰.
4. Follow the rule transaction to the Bradbury explorer and inspect the
   [native finality proof](runs/review-live-rule-final-native.json).
5. Download the record and run `python3 cli/impeach.py recompute web/case.json`.
   The result must agree with the stored certificate.

The website is a record viewer; signed contract operations run through the
included CLI. The paid subject endpoint is disabled after completion.
