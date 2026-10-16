# Steward corrections — 16 October 2026

Court revision: `impeach/1.1`. The previous deployed contracts are immutable;
their certificates remain historical evidence under their original rules.

## Admissibility

Previously, the final answer-key comparison was conditional on a numeric key.
A nonempty but wrong text result could pass if the semantic referee returned
`same_question: true`. Both blind results are now compared with their respective
committed keys regardless of answer type. Numeric pairs use canonical decimal
equality; other pairs use deterministic `norm_answer` equality. Unlisted text
synonyms are conservatively rejected. The independent solver still cannot see
either answer key, and both referee framings remain mandatory.

Regression tests cover wrong original and rewritten text results, mixed
text/numeric keys, false-positive semantic Booleans, malformed results and both
framings. The text bypass reproduced seven failing assertions before the fix.
The public `probe` workflow is also tested with the real pinned SDK.

## Certificate evidence

`CLEAN` now requires both `admissible >= min_items` and
`recall_probes >= min_items`, with neither detector nor score shortfall tripping.
Only `MATCH` and `MISS` are measured recall. `DEAD`, `NA` and missing responses
cannot establish absence of recall. Insufficient recall produces
`INCONCLUSIVE / TOO_FEW_RECALL`. Positive contamination evidence and a proven
score shortfall still retain their independent verdict paths.

The contract, offline Python recomputation and browser recomputation use the
same rule. Coverage tests include zero recall results, one below the minimum,
exactly the minimum and ineligible short tails; browser parity also covers
missing recall slots. Solvency is checked after every public write.

## Corrected deployment and trial

The corrected Bradbury contract is
`0xCB67936d0b00b82Ea73611b3C8353a21EBdc7261` (chain 4221).
Deployment transaction:
`0x664310c1df84a6271f19da43affa696c3460e8aad7f0b02aa49318bc3c5dfcbe`.
The [receipt](runs/review-deploy-receipt.json) initially confirms
`ACCEPTED / AGREE / FINISHED_WITH_RETURN`; finalization is verified separately.
The [build manifest](build/impeach.manifest.json) binds source, readable compact
code and exact deployment artifact.

The [real-model claim](calibration/claim-review-live.json) requires **all 24**
admitted pairs and **24** measured recall results. Its model, provider and
decoding parameters remain frozen. The paid endpoint expires automatically
within four hours and shares the original lifetime $5 key limit; the
[budget preflight](runs/review-budget-preflight.json) recorded $2.02616946 spent.

This is a regression run of the corrected court on the previously disclosed
`court24-v3` corpus, not a new secret benchmark or a claim that these items have
not already appeared on chain. The new deployment has its own spent registry.
Original source and previous burns are retained; no old certificate is rewritten.

An [exact-prompt offline replay](runs/review-referee-replay.json) consumed all
112 previously recorded Sonnet responses: 24 intended rewrites admitted and four
negative controls rejected by both framings, with no missing prompts or new
model calls. This establishes calibration consistency, not validator consensus.

Native trial evidence will be added only after reading the corrected contract's
stored probes, ruling it and checking successful native finalization. No completed
corrected native verdict is claimed by this document yet.

## Verification

- Local contract scenarios: 203 passed.
- Real pinned SDK scenarios: 169 passed (GenVM v0.2.16).
- `make check` also checks Python regressions, deployment AST equivalence,
  endpoint constraints, receipt/finality safeguards and browser parity.
- Node runtime requirement remains 22 or later.
