# V2 trial: preparation, evidence and safe completion

Status snapshot: **11 October 2026 — scripted certificate finalized; real v2 transactions finalized, but item 14's second admission is not stored.**
The new Bradbury contract is
`0x45F610cefF1ed367d684A1839b1801Af12Cfb038` on chain 4221.
Scripted claim/challenge 0 has a native `CONTAMINATED / RECALL` certificate:
24/24 pinned answers and 24/24 recall matches, 13 admitted rewrites,
court-adjusted rewrite score 833‰, Δ=166‰ and four stale answers. Its
[rule](https://explorer-bradbury.genlayer.com/transactions/0xd2970d5c785db84c92cfbf71924d8b719e29f8e48b29715b9da9c345e9c5ed77)
is finalized with `MAJORITY_AGREE / FINISHED_WITH_RETURN`; all four court queues are empty. See the
[finality handoff](runs/c0-finality-20261011-resume/handoff.json),
[certificate](runs/c0-rule-20261011/certificate.json) and
[all 24 states plus receipts](runs/c0-rule-20261011/after.json).
The recall detector meets its 20-item minimum. The paired detector does not:
unadmitted rewrites are presumed correct for the publisher, so 833‰ is not
accuracy on admitted pairs alone. This control is a stored-answer lookup.
The real Llama gateway was activated until **11 October 2026, 10:38:56 UTC**.
A paid preflight returned the exact reference `ANSWER: 36`, with credit-only
DeepInfra usage and a cost of $0.00000486. Immediately before opening, the real
cohort had 24 unspent content hashes. No completed real native certificate is
asserted here. See [health](runs/v2-live-health-20261011.json),
[raw inference](runs/v2-live-preflight-20261011.json),
[counts](runs/v2-live-before-counts.json), and
[registry](runs/v2-live-before-registry.json).

The [final native audit](runs/v2-live-final-native-audit/audit.json) reads all
24 slots and all 107 manifest receipts after finalization: 24 pinned answers
and rewrites are right, all 24 recall probes miss, all 24 C1 rulings admit,
but only 23 C2 rulings are stored. Item 14 remains `PENDING`. The
[handoff](runs/v2-live-final-native-handoff.json) confirms unchanged frozen
inputs, balanced solvency and empty queues. The successful appeal and both
finalization events do not establish a 24th stored admission. No v2 real
certificate has been ruled. Closing this partial case requires the user's
separate authorization after automatic approval review rejected the action.

A [fresh v3 cohort](calibration/court24-v3-audit.json) adds a disclosed common
prefix and new salts to the same arithmetic. It has no spent-hash overlap,
a six-hour court window and a separate disabled `/api/live-v3/chat/completions`
route. The gateway's four-hour window and shared lifetime $5 budget are
unchanged. Offline reuse of earlier responses is labeled as cross-prompt
regression, not a new model measurement. Subsequent actual calibration passed:
[112 new Sonnet calls](runs/v3-referee-verified.json) admitted all 24 rewrites
and rejected all four controls under both framings. The new Llama rehearsal
made 74 attempts with three no-reply outcomes, leaving one original request
without a response; [one separate actual supplement](runs/v3-llama-supplement.jsonl)
completed it. [Exact offline replay](runs/v3-llama-verified-audit.json) consumes
all 72 distinct new-prompt responses and makes no paid calls: 24 correct pinned
answers, 24 correct rewrites and 24 recall misses, with no dead slots. Its
`CLEAN` result is a local forecast using scripted admission, not a native
certificate. The original failures and partial rehearsal are retained.
See [the generator](scripts/generate_court24_v3.py).

The [deployment record](runs/v2-deployment.json) and
[receipt](runs/v2-deployment-receipt.json) identify the accepted deployment.
Its source SHA256 is
`d7e8f0f1e967dc8f883a5758594325e075711f77a79f8f8229071467db3a704b`,
matching the current [contract source](contracts/impeach.py). The deployment
record also preserves the compact-source and artifact hashes and the AST
equivalence check. Subsequent receipt/output-helper fixes do not change that
deployed contract.

## Two public cohorts on one court

| Role | Frozen claim | Source items | Rewrites |
| --- | --- | --- | --- |
| Real Llama | [claim-court24-v2.json](calibration/claim-court24-v2.json) | [court24-v2.items.json](calibration/court24-v2.items.json), seed 240524 | [court24-v2](examples/court24-v2/rewrites) |
| Scripted memoriser | [claim-court24-v2-scripted.json](calibration/claim-court24-v2-scripted.json) | [court24-v2-scripted.items.json](calibration/court24-v2-scripted.items.json), seed 240525 | [court24-v2-scripted](examples/court24-v2-scripted/rewrites) |

Each cohort has 24 originals and 24 rewrites: five paraphrases, five numeral
substitutions, five entity renames, five unit changes and four format shifts.
The live corpus also has four negative referee controls; controls are not
allowed subject requests.

The scripted cohort prefixes every original and rewrite with exactly
`On a practice worksheet, a student reads this problem: ` (including the final space).

It uses fresh deterministic salts and the same arithmetic, answers and rewrite
classes. Its normalized source content hashes do not intersect the real cohort,
so revealing one does not mark the other as already spent on this contract.
The two [corpus audits](calibration/court24-v2-audit.json) and
[scripted audit](calibration/court24-v2-scripted-audit.json) record the construction,
formulas and hashes. [Endpoint tests](test/test_endpoints_v2.mjs) verify the
disjoint registry hashes and all 72 exact request bodies for each claim.

These are disclosed synthetic demonstrations, **not independent benchmarks**.
The scripted set is a transformed copy of the same mathematics. Prompts, answers,
salts and construction seeds are public. No claim is made that the texts are
secret, globally novel, or absent from model training.

## Frozen scoring and referee policy

Both claims freeze the exact `NUMERIC_LINE_RULE` constant. The last nonempty line
must be literal `ANSWER:` followed by one ASCII decimal number, optionally
negative, and nothing else. The contract canonicalizes leading/trailing zeros
without floats. Units, commas, exponents, Unicode digits, incomplete decimals
and trailing prose are invalid. Different earlier explanations do not matter.
Every validator calls the real subject independently, but numeric marking uses
`strict_eq` on canonical results and correctness, with no LLM marker. Other
scoring-rule strings keep the legacy semantic marker.

Admissibility still requires two framings. Each uses a blind solver with no
answer keys and a separate semantic class judge, both requested with
`response_format="json"`. Numeric solver results and the judge's Boolean use
`strict_eq`; nonnumeric pairs use `prompt_comparative`. A single unambiguous bare
or fenced JSON object may have surrounding prose. Multiple candidates/blocks,
invalid JSON and incorrect field types fail closed. Neither parser handling nor
numeric consensus bypasses the answer-key or class checks.

Both claims retain `min_items=20`, `delta_threshold=250`,
`recall_threshold=150`, recall prefix 400‰ and similarity 900‰. Subject decoding
is temperature 0, top_p 1, max_tokens 512 and seed 7; recall also uses 512 tokens.
The reveal window is 3,600 seconds and trial window 10,800 seconds. Read the
actual on-chain clock and frozen terms before every resumed run.

## Completed local evidence

| Check | Observed result | Evidence |
| --- | --- | --- |
| Sonnet 4.6 referee calibration | 24/24 intended rewrites admitted in both framings; 4/4 controls rejected in both | [verified replay](runs/v2-referee-verified.json), [rulings](runs/v2-referee-verified.rulings.json) |
| Real Llama subject rehearsal | 72 calls, no missing replies; pinned/rewrite 1000‰/1000‰, Δ=0‰, R=0‰, no stale answers | [raw calls](runs/v2-llama-requests.jsonl), [log](runs/v2-llama-rehearsal.log), [simulation snapshot](runs/v2-llama-rehearsal.json) |
| Scripted endpoint/contract test | pinned 1000‰, rewrite 791‰, R=1000‰, five stale answers; local `CONTAMINATED / RECALL` | [offline endpoint tests](test/test_endpoints_v2.mjs) |

The referee evidence contains **112 actual raw model calls**: the initial
[111-call transcript](runs/v2-referee-sonnet-transcript.jsonl) plus
[one separately recorded missing prompt](runs/v2-referee-supplement.jsonl).
The initial [summary](runs/v2-referee-sonnet-transcript.summary.json) did not pass
the gate. The current parser was then checked by exact-prompt replay, preserving
the raw responses; only the missing prompt required an additional real call.
The final verified replay consumes all 112 stored responses and makes no new
calls. Its source hash matches the deployed contract. This is local calibration
of one model, not proof that GenLayer's validator population will agree.

The real rehearsal used real Llama responses in a local contract harness with
scripted referee admission. Its `CLEAN` forecast is not a native verdict. The
scripted control's local result is separate from its finalized native certificate.

## Routes, budget and activation

| Route | Behavior |
| --- | --- |
| `/api/chat/completions` | Original GSM8K allowlist, unchanged; keep `TRIAL_ENABLED=false` |
| `/api/live-v2/chat/completions` | Fixed real claim/corpus; requires separate `TRIAL_V2_ENABLED=true` |
| `/api/scripted-v2/chat/completions` | Fixed scripted claim/corpus and model `scripted/memoriser-court24-v2`; no LLM, key or external API |

Live v2 always applies the narrow credits-only gate: fixed
`meta-llama/llama-3.1-8b-instruct` and `deepinfra/fp8`, no fallback, provider price
caps $0.05/$0.10 per million input/output tokens and zero per-request fee. The
key needs a non-resetting lifetime cap at most $5, known zero BYOK usage and at
least $0.10 remaining. DeepInfra BYOK must remain unconfigured. A returned
completion must explicitly report `usage.is_byok=false`; rejecting a completed
response cannot reverse a charge already incurred. See [OPENROUTER.md](OPENROUTER.md).

`TRIAL_EXPIRES_AT` must be an explicit UTC deadline no more than four hours ahead.
The $5 allowance is **shared with earlier rehearsal and referee spending**. It
does not renew when the endpoint, deployment or claim changes. Public replay of
an allowed request can consume it. Vercel platform costs are not this API cap.

The [preparation health check](runs/v2-live-v2-health.json) records the disabled
route before activation. The [activation audit](runs/v2-live-activation-20261011.json)
verifies the active production policy against all 72 frozen local request bodies,
a real inference, blocked arbitrary/scripted inputs, and the disabled legacy route. The [scripted health check](runs/v2-scripted-v2-health.json)
labels the lookup as scripted/no LLM. A free health/configuration check does not
prove a real inference succeeds. Activate the real route only for its agreed
native window, keep the frozen URL/model/parameters unchanged through ruling,
and disable it when that case ends. Do not enable the old route.

## Completing the native trials safely

The application and local JS suite require Node 22 or later; the verified suite
used Node 24.19.0. The installed official GenLayer CLI bridge uses its own
Node 20 environment and SDK 1.1.8, including the matching Keychain module.

Only one process may sign for the trial account/manifest at a time. The current
scripted manifest is [bradbury-v2-scripted.jsonl](runs/bradbury-v2-scripted.jsonl);
its trial deadline has passed and its certificate is finalized. Do not send
more control probes. The following command illustrates resumption during an
active trial; the fresh real manifest is [bradbury-v2-live.jsonl](runs/bradbury-v2-live.jsonl).
If its completer is already running, inspect its files instead of starting
another sender. After an intentional stop or exit, the same command resumes:

```bash
caffeinate -i python3 -u scripts/complete_case.py \
  --address 0x45F610cefF1ed367d684A1839b1801Af12Cfb038 \
  --claim calibration/claim-court24-v2.json \
  --manifest runs/bradbury-v2-live.jsonl \
  --challenge-id 1 --account impeach-challenger \
  --rpc https://rpc-bradbury.genlayer.com \
  --wait-timeout 100 --poll-interval 5 \
  --max-runtime 900 --deadline-margin 120 --max-recoveries 3 \
  --allow-proven-no-messages --source build/impeach.py \
  >> runs/v2-live-complete.log 2>&1
```

For the real trial, use `calibration/claim-court24-v2.json`,
`runs/bradbury-v2-live.jsonl` and the now-recorded claim/challenge IDs **1/1**.
Its native deadline is **11 October 2026, 09:46:04 UTC**. Do not reuse control IDs. Opening,
challenging and revealing remain explicit earlier steps documented in
[DEPLOY.md](DEPLOY.md). `complete_case.py` starts only from a revealed 24-item
`TRIAL`, verifies its frozen inputs and runs the available PINNED, RECALL,
REWRITE and ADMIT slots. A valid `INADMISSIBLE` ruling is retained.

The helper locks `<manifest>.complete.lock`. Preserve the manifest, its
`.complete/` directory and `.receipts/` recovery markers together. Inspect:

- [progress.json](runs/bradbury-v2-scripted.jsonl.complete/progress.json): phase,
  completed/admitted counts, pending hashes, dead slots and recovery eligibility;
- [events.jsonl](runs/bradbury-v2-scripted.jsonl.complete/events.jsonl): dispatch,
  receipt, failure and recovery history;
- immutable failure receipts under `<manifest>.complete/receipts/`, and each
  recovered row's `previous_tx`, `previous_row` and `previous_receipt`.

Exit **0** means all 24 items have the required answers/recall/referee outcomes.
It does not mean all rewrites were admitted, all receipts finalized, a `CLEAN`
verdict occurred, or a certificate was published. Exit **2** means inspect the
saved reason and resume/reconcile as appropriate. Runtime and deadline checks
stop further submissions at safe boundaries; they do not justify killing a
signing helper before its broadcast hash is recorded.

Decided failures are saved and acknowledged without assuming successful
execution. Initial independent slots are progressed first. By default a failed original
slot can receive **one** guarded recovery only after finalization, while still
unapplied and inside the trial window. Explicit `--max-recoveries 3` permits
three recoveries per slot, each requiring a new finalized failure. Eligible
outcomes are explicit negative consensus, or finalized `NOT_VOTED / IDLE`
showing no execution. The helper checks unchanged inputs and preserves every
original and recovery hash with its ordinal and preceding receipt.
An already applied slot, an `INADMISSIBLE` ruling or an endpoint `DEAD` result is
not automatically resubmitted. The completer does not appeal, finalize, rule,
retire or withdraw.

Unknown dispatch outcomes require reconciliation against the existing hash and
chain state. Never delete a durable dispatch marker to guess-and-resend. A
positive-looking field is insufficient: `FINISHED_WITH_RETURN` alone, `AGREE`
without an accepted/finalized status, an unknown status, or conflicting numeric
and textual fields do not establish success. Unknown/inconsistent terminal
metadata pauses the runner. The receipt normalizer explicitly supports legacy
compact `ACCEPTED` receipts with successful execution and no result fields; this
does not extend to unknown status codes or finalized receipts. `FINALIZED` can
close a failed decision as well as a successful one.

Status **14** is the legacy SDK's `LEADER_REVEALING`, a nonterminal phase. Keep
polling the same hash; do not acknowledge it as failure or rebroadcast it. The historical
[provenance record](runs/v2-status14-provenance.json) first pinned the SDK source.
Subsequent [native source audit](runs/v2-native-status-audit.json) and
[outcome enum audit](runs/v2-native-outcome-enum-audit.json) verified the active
Solidity implementations, registry pointers and exact enums. Stored Main phase
and time-projected SDK status are kept separate.
Do not replace legacy codes 11–13 with the different v0.6 mapping. The
[stdout helper](scripts/output.mjs) now waits for large receipt output to drain
before process exit, covered by [test_output.mjs](test/test_output.mjs). A
truncated transport response is a read failure, not a chain failure.

The ordinary receipt-only recovery rules remain unchanged. Optional
`--allow-proven-no-messages` adds a separate proof path for exactly known
`FINALIZED / FINISHED_WITH_RETURN / IDLE` or
`FINALIZED / NOT_VOTED / MAJORITY_AGREE`. It requires the verified
FinalizationPhase event `TransactionFinalized` with previous status 6, 12 or 13
and `shouldProcessMessages=false`, a canonical successful EVM receipt, current
and historical implementation pins, matching source and original calldata,
and fresh unchanged empty slot/claim/challenge/deadline checks before dispatch.
The Main event with only a hash is insufficient. Missing, conflicting or
unavailable evidence stops the helper; it cannot guess a repeat.

The proof is a `chain_observation` when read from the chain without a matching
service journal; this label does not assert who initiated finalization.
`service_queue` proofs additionally correlate before, dispatch, EVM hash,
receipt, after and done files. Recovery rows and durable dispatch markers carry
the immutable bundle path, SHA256 and failure basis. Every later helper startup
revalidates the whole preserved chain against the frozen claim and artifact.
The read-only [actual C0 proof audit](runs/v2-native-proof-c0-smoke-audit.json)
confirms the distinction between cached outcome fields and native execution.

Between bounded completer runs, release its lock and use
[`service_queue.py`](scripts/service_queue.py) to inspect the recorded native
queue heads. It shares the same lock and signs only with explicit `--execute`,
using exact gas simulation for permissionless Main `finalize` or
`processIdleness`. It cannot appeal or create application calls. All deployed
implementation/source pins and native calldata must match the manifest. Do not
run both helpers together. Late appeals can roll back later unfinalized state;
these helpers never appeal automatically. Preserve `.queue/` evidence as well.

The real trial made one separately reviewed exception for item 14's latest C2
recovery, transaction
`0xa264c36846db3a8a567d3e493ceadfd3ff30d1582aa6f573fe7d42d701ccb40c`.
It had reached a native leader timeout, whose finalization deadline exceeded
the remaining application trial window. The review checked frozen calldata and
source, zero minimum bond, the two remaining court transactions and an exact
Main dry run before sending the zero-value appeal. The
[appeal journal](runs/v2-live-item14-appeal01) preserves the EVM receipt and
every subsequent observation; the GL transaction keeps its original hash.
The replay obtained `MAJORITY_AGREE / FINISHED_WITH_RETURN`, with the blind
solver returning 53 for both texts and the semantic judge returning true.
The application read still reports C2 `PENDING` after both related transactions
are actually finalized. The [raw selector comparison](runs/v2-live-state-filters-after-all-final.json)
and complete audit retain that result; identical selector outputs do not prove
that this RPC honors each version filter. Both
[finalization events](runs/v2-live-two-finalization-events.json) have previous
status 5 and `shouldProcessMessages=true`, so the no-message failure recovery
exception does not apply. No new probe or further appeal is authorized by this
observation. A possible later-snapshot overwrite remains a hypothesis, as
[the read-only investigation](runs/v2-live-state-selector-audit.json) explains.

After completion, inspect each native state, then perform the separately
authorized ruling/settlement steps. Collect the ruled on-chain certificates and
their full receipt histories before publishing. Keep real, scripted and local
simulation provenance explicit. Neither a partially filled progress file nor a
local rehearsal may replace a missing native certificate.

## Offline verification

```bash
node --test test/test_proxy.mjs test/test_endpoints_v2.mjs test/test_output.mjs
python3 scripts/referee_replay.py \
  --claim calibration/claim-court24-v2.json \
  --controls examples/court24-v2/controls \
  --transcript runs/v2-referee-sonnet-transcript.jsonl \
  --transcript runs/v2-referee-supplement.jsonl \
  --out /tmp/impeach-v2-referee-recheck.json
```

The replay command supplies both saved transcripts and deliberately omits
`--supplement`, so a missing prompt fails rather than triggering a paid call.
These checks do not advance the native trial or prove a final verdict.
