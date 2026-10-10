# Impeach — submission

**One line.** A GenLayer court for benchmark scores: a bonded score is tested on
its sealed items and on rewrites the model has not seen, and the items are burned
into a public registry the moment they are shown.

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
| marking a model's answer | `prompt_comparative` | the extracted answer and a boolean, never the prose |
| admissibility | `prompt_comparative` | independently computed answers and the class decision, two framings |
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
- The demonstration set (24 GSM8K test items) was never secret.
- _If the live subject is the scripted memoriser, say so here in one sentence._

## Evidence

_Empty until the live run. Fill from receipts and `web/case.json` only._

| | |
| --- | --- |
| contract | |
| deploy tx | |
| claim id / challenge id | |
| subject and endpoint | |
| terms hash | |
| verdict, reason | |
| Δ / R / sealed accuracy | |
| admitted pairs / refused rewrites / old answers | |
| transactions sent / accepted / undetermined | |
| validator set size, distinct leaders | |
| items burned | |
| GEN spent | |
| page | |
| repository | |

The current trial's transaction hashes are recorded at submission in
`runs/bradbury-vercel.jsonl`; fetched outcomes are included in `web/case.json`.
`runs/bradbury.jsonl` preserves the earlier tunnel trial separately.
