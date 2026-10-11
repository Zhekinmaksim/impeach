# Decisions

The spec left three questions open on purpose. The decisions below record how
the implementation resolves them and later implementation issues. Changing a
future deployment does not change terms already frozen in an existing claim.

## The three open questions

### 1. Who pays for the model calls?

**No sampling inside a challenge. The subset is the sample.**

The challenger names the items blind, at least `min_items` of them, and every
named item is probed in full. A second layer of sampling inside that would
weaken a number that is already small.

Costs fall where they arise. The challenger sends the probe transactions and
pays their gas. The publisher serves the endpoint and pays the inference. An
honest challenger who finds nothing gets the whole stake back, as the spec asks.

"`INCONCLUSIVE` returns both, minus probe costs" is implemented as: when the
reason is `ENDPOINT_SILENT`, the publisher pays the challenger an amount equal
to the challenger's stake out of the bond. The silent party pays the other
side's costs.

*Test:* `silence` — "silence is not free".

### 2. Should `CLEAN` be purchasable?

**No, in two ways.**

By absence: a claim nobody challenged reads `UNCONTESTED`, before and after the
publisher retires it. It is never upgraded.

By a friendly challenger: `CLEAN` does not close the case. The bond stays posted
and the claim stays open (`STANDING`). Anyone can challenge again. Because the
items are now public, a later challenger must take the whole set — choosing
which questions to ask after reading them is how a gap gets manufactured. The
certificate carries `challenges_survived` and `bond_standing`, so a reader can
tell a score that has stood through three challenges from one whose publisher
took the bond and left after the first.

*Test:* `standing` — "a CLEAN certificate does not protect the next trial".

### 3. Does a burned set retire the score?

**Yes.** The certificate carries `score_status`: `SEALED` until reveal, `SPENT`
after, with `score_expired_at` set to the burn time. Once the items are public
the score can never again be measured on text the subject has not seen, so from
that moment the number is worth exactly what the certificate says and nothing
more.

## Departures from the spec

### 4. A fourth verdict: `UNSUPPORTED`

The build order asks the suite to separate three subjects: one that memorised,
one that can do the task, one that does neither. Under the spec's verdict table
the third one has no gap and no recall, so it is `CLEAN` and takes its bond
home — for a score it cannot reproduce.

The publisher *swears to a number*. If measured accuracy on the sealed items
falls short of the sworn score by `delta_threshold` or more, the verdict is
`UNSUPPORTED` and the bond goes to the challenger. One threshold now guards two
links of the same chain: sworn → sealed, sealed → rewritten.

The same verdict, reason `SET_ALREADY_SPENT`, is given at reveal when any item
was already in the registry before the claim was opened. Re-salting hides a
spent item from `open_claim`; it does not hide it from the reveal.

A bad model that swears to a bad score is `CLEAN`. The court tries the oath, not
the model.

*Tests:* `three_populations`, `registry`.

### 5. Default judgment

A publisher who expects to lose simply never reveals. Without a rule for that,
the sealed set is an exit. After `reveal_window_s` anyone may call
`claim_default`; the bond and the stake go to the challenger. Nothing is burned,
because nothing was shown.

This is the one place the contract depends on transaction time. `clock()`
exposes it for a smoke test after deploy.

### 6. Silence on a rewrite is an answer

An endpoint that holds a lookup table can answer the items it knows and return
an error on everything else, turning every losing probe into a dead one. If the
sealed item was answered and the admitted rewrite was not, the rewrite counts as
wrong. A fully dead endpoint is different and stays `INCONCLUSIVE`.

*Test:* `silence` — "going quiet on the rewrites is read as an answer".

### 7. The gap is counted over every probed item

The spec computes Δ over admissible pairs. A challenger can query the public
endpoint first, file rewrites only for items the model got right, and drop the
rest. That removes every pair that would have pulled the gap down. In the test
this turns an honest model with a 30% error rate into a conviction.

The contract counts over every item with a live sealed answer, and reads an item
with no admitted rewrite as if the rewrite had been answered correctly. The
`min_items` requirement still applies to admitted pairs.

*Test:* `omission` — "counted over those pairs alone, the gap would convict".

### 8. Forfeited stake goes to the publisher, not a pool

"Griefing funds the next case" worked in Suborn because a sponsor owned the pool
and wanted it paid out. Here there is no sponsor. Any shared pool that pays
winners can be drained by a publisher who opens a doomed claim and challenges it
from a second address. Money that only ever moves between the two parties cannot
be farmed, and the publisher is the one whose set was burned to hear a question
that should not have been asked.

### 9. The challenger writes the rewrites

The spec says rewrites are "generated at judgment time" and also that failed
admissibility costs the challenger. Both hold if the challenger authors them
after the reveal. So `probe` takes a fourth argument (the rewrite envelope) and
there is a fourth mode, `ADMIT`, for the second referee framing — the same split
as Suborn's `submit` and `confirm`, and the fourth box in the spec's own diagram.

One rewrite per item. The stake is divided per item: an admitted rewrite gets
its slice back win or lose, an inadmissible one forfeits it, an unfiled one
forfeits it at ruling.

### 10. `ruled_at` is a time, not a block

The pinned SDK does not expose a block number to contracts. The certificate
carries the transaction time in seconds.

### 11. HTTPS subjects only

The spec's v1 covers public endpoints and on-chain agents. `impeach/1` covers
public endpoints. Calling another contract as the subject needs an agreed
interface that does not exist yet.

### 12. An exact numeric rule is an explicit claim term

The v2 arithmetic claims freeze `NUMERIC_LINE_RULE` verbatim. Only the last
nonempty line is marked: literal `ANSWER:` followed by an ASCII decimal with an
optional minus sign, and nothing else. Canonical decimal strings remove leading
integer zeros, trailing fractional zeros and negative zero without using floats.
A missing or invalid final line is wrong. Validators compare the status,
canonical answer and correctness using `strict_eq`; this path does not call an
LLM marker. Other frozen rule strings keep the semantic marker and
`prompt_comparative`.

The rule makes an arithmetic answer decidable without treating a particular
explanation as authoritative. It does not script the live subject: every
validator still calls the frozen Llama endpoint. It cannot be enabled after a
claim opens. The thresholds remain 20 items, a 250‰ gap/score shortfall and
150‰ recall in both v2 claims.

Both referee framings remain required. Each has a blind solver without answer
keys and a separate semantic class judge, requested with `response_format="json"`.
For numeric pairs, canonical solver results and the judge's Boolean are compared
by `strict_eq`; nonnumeric pairs retain `prompt_comparative`. The shared parser
accepts a single unambiguous bare or fenced object with optional surrounding
prose. It rejects multiple objects/blocks and invalid types; it does not alter
the judge's decision. These representation changes do not waive either framing,
the correct-answer checks or the class invariant.

Evidence: [contract](contracts/impeach.py),
[exact-prompt replay](runs/v2-referee-verified.json), and
[referee transcript](runs/v2-referee-sonnet-transcript.jsonl). The 112 real model
calls comprise 111 initial calls plus one separately recorded missing prompt;
the subsequent replay made no new calls. Both framings admitted 24/24 intended
rewrites and rejected 4/4 controls. This is calibration of one off-chain model,
not evidence that native validators have completed a trial.

### 13. Separate public cohorts for the live subject and scripted control

The new live cohort uses construction seed 240524. The scripted cohort uses seed
240525, fresh salts and the exact prefix
`On a practice worksheet, a student reads this problem: `
on each original and its rewrite. The arithmetic, references and
rewrite classes are shared. The source content hashes are disjoint, allowing
both claims on one contract without reusing an already spent source.

This is an explicit control construction, not a second independent benchmark.
Both corpora and their salts are public. They are neither secret evaluation
material nor proof of worldwide novelty or absence from a model's training data.
The scripted endpoint is a sealed-answer/tail lookup labeled `scripted` and
`llm: false`; it makes no external model calls. Its five changed-number rewrites
intentionally receive stale answers and its recall probes receive exact tails.

Evidence: [live audit](calibration/court24-v2-audit.json),
[scripted audit](calibration/court24-v2-scripted-audit.json), and
[endpoint tests](test/test_endpoints_v2.mjs). The real Llama rehearsal made 72
calls and measured pinned/rewrite accuracy 1000‰/1000‰, Δ=0‰ and R=0‰. See the
[raw calls](runs/v2-llama-requests.jsonl) and [report](runs/v2-llama-rehearsal.log).
The native scripted claim 0 on
`0x45F610cefF1ed367d684A1839b1801Af12Cfb038` is now finalized
`CONTAMINATED / RECALL`. Its [finality handoff](runs/c0-finality-20261011-resume/handoff.json)
and [certificate](runs/c0-finality-20261011-resume/certificate.json) record 24
pinned answers, 24 recall matches, 13 admitted pairs, court-adjusted rewrite
score 833‰, Δ=166‰, four stale answers and R=1000‰. Recall meets the 20-item
minimum; the paired detector does not. The 833‰ score includes the presumption
of correctness for unadmitted rewrites, rather than measuring only admitted
pairs. This proves the disclosed lookup control's result, not a finding about
the real Llama subject.

Real claim 1 has an unresolved application-state discrepancy. The
[11 October 2026, 10:14 UTC handoff](runs/v2-live-final-native-handoff.json) and
[complete native audit](runs/v2-live-final-native-audit/audit.json) confirm that
all 107 recorded native transaction hashes are `FINALIZED` and all four queue
heads are empty. The actual getters show 24 pinned `RIGHT`, 24 recall `MISS`,
24 rewrite `RIGHT` and 24 first-framing `ADMISSIBLE` outcomes, but only 23
second-framing `ADMISSIBLE` outcomes: item 14 remains C2 `PENDING`.

Item 14's `0xa264c368…` is a positive finalized receipt with
`MAJORITY_AGREE / FINISHED_WITH_RETURN`, round 2 and referee output
`53 / 53 / true`. Both its and item 23's
[FinalizationPhase events](runs/v2-live-two-finalization-events.json) have
`previousStatus=5` and `shouldProcessMessages=true`. This is not a no-messages
failure eligible for the proof-based retry path. Finalizing the native queue
did not establish 24 applied pairs, and the storage discrepancy's cause remains
unresolved.

No `rule`, retirement or withdrawal has been sent for C1. Automatic approval
review rejected closing the partial 23-pair result before broadcast because the
authorized goal was all 24 pairs; explicit user authorization for that partial
closure has been requested. The saved `CLEAN` calculation is an offline forecast,
not a native certificate. C1 remains `TRIAL`, without a ruled verdict.

### 14. Preserve unknown transactions instead of guessing a result

`complete_case.py` locks its manifest, checks the frozen claim and records a
durable marker before sending. It progresses the independent initial slots
before recovering failed ones. Recovery defaults to one new transaction per
slot; the explicit `--max-recoveries 3` limit permits at most three, excluding
the original. Receipt-only recovery requires a freshly verified `FINALIZED`
negative consensus result, or `FINALIZED / IDLE / NOT_VOTED`, and an unchanged,
unapplied slot in the active trial. The explicit proof path in decision 16 adds
two precisely bounded cases. The original payload, every hash, previous row,
receipt hash and recovery ordinal remain recorded. Pending/replaying calls,
applied slots, `INADMISSIBLE` and `DEAD` do not gain permission to resend.
Ambiguous `RETURN / IDLE` without the required proof remains blocked.
Unknown dispatches and inconsistent fields pause for
reconciliation. Deleting a dispatch marker is not recovery.

The active Bradbury enums are verified against the deployed implementation,
not inferred from an SDK label. Chain 4221's ConsensusMain
`0x0112Bf6e83497965A5fdD6Dad1E447a6E004271D` points to
`0x0a2C393975dA79505ED930eFC55ae4AEB88b0d62`, `VERSION=2.0.0`, network release
`v0.5:9c68608`. The [deployment/source audit](runs/v2-native-status-audit.json)
and [outcome enum audit](runs/v2-native-outcome-enum-audit.json) establish:

| Enum | Verified numeric mapping |
| --- | --- |
| Status 11–14 | 11 `READY_TO_FINALIZE`, 12 `VALIDATORS_TIMEOUT`, 13 `LEADER_TIMEOUT`, 14 `LEADER_REVEALING` |
| Result | 0 `IDLE`, 1 `MAJORITY_AGREE`, 2 `MAJORITY_DISAGREE`, 3 `MAJORITY_TIMEOUT`, 4 `DETERMINISTIC_VIOLATION`, 5 `NO_MAJORITY` |
| Vote / execution | 0 `NOT_VOTED`, 1 `FINISHED_WITH_RETURN`, 2 `FINISHED_WITH_ERROR`, 3 `TIMEOUT`, 4 `NONDET_DISAGREE` |

The v0.6 status reassignment does not apply to this deployment. Status 14 is
pending and only extends polling of the original hash. Raw SDK labels remain
unchanged in saved receipts; the normalizer treats result names `AGREE`,
`DISAGREE` and `TIMEOUT` as legacy aliases. Result codes 6/7, execution code 5
and genuinely conflicting fields remain unknown and stop processing. Vote 4
is not a deterministic violation; result 4 is.

### 15. Service the native queue without replaying application calls

The baseline policy has no automatic appeals because an appeal can rewind
later calls. There was one separately reviewed exception for the latest item 14
ADMIT recovery after `LEADER_TIMEOUT`: one zero-bond appeal of the same native
hash, with unchanged payload. Its EVM transaction is
`0xd6e15fa9b664d490c6094444f330b6647236f7c4d18baa43a772c5378fabe851`.
The [before evidence](runs/v2-live-item14-appeal01/before.json),
[single-appeal dispatch](runs/v2-live-item14-appeal01/dispatch.json),
[EVM receipt](runs/v2-live-item14-appeal01/evm-receipt.json) and subsequent
native receipts remain saved. This exception does not enable an appeal loop.
Its native transaction is now finalized, but item 14's C2 state remains pending;
no further probe call or appeal is authorized by this exception.

After a bounded completer exits and releases
`<manifest>.complete.lock`, `service_queue.py` may take the same exclusive lock.
The completer, queue service and any manual signer must never run concurrently
for that court/account. An unresolved bridge can retain the lock; wait for
reconciliation rather than killing a submission whose hash is not recorded.

The queue service is read-only by default. `--execute` permits only bounded,
zero-value Main `finalize` or `processIdleness` operations. It checks the live
implementation pins, exact deployed source, frozen claim, manifest, decoded
call/value and explicit-recipient queue heads. An unknown head stops the run.
An exact Main gas simulation is authoritative even when the older
`ConsensusData.canFinalize` view says false. Idleness is considered only for a
mature deferred phase, once per hash/phase/round/timestamp fingerprint. A fresh
state check precedes dispatch; EVM hash, receipt and native before/after evidence
are retained. No-progress or unknown outcomes cannot be retried blindly.

Native finalization can happen automatically or through an explicitly recorded
Main transaction. Both require fresh native evidence: an EVM receipt's success
alone is insufficient. `FINALIZED` can close a failed transaction. Stored
`UNDETERMINED` (6), `VALIDATORS_TIMEOUT` (12) and `LEADER_TIMEOUT` (13) can retain
stale outcome fields. The queue service may finalize these known failure phases
only at the actual finalized-queue head, after exact Main simulation and fresh
source/calldata checks. It does not require proof that their application calls
were applied. Evidence records the numeric `beforeStoredFailurePhase` and
`native_success=false`; `beforeStoredUND` remains true specifically for phase 6.
These fields do not by themselves authorize a new probe. An already recorded
zero-value `rule` may be finalized
after its exact signature/challenge checks; the service never creates a rule,
probe, appeal, retirement or withdrawal. Resume the completer only after the
queue service exits and releases its lock.

The CLI's [output helper](scripts/output.mjs) waits for stdout writes to drain
before exit so a large receipt is not truncated in a Python pipe. These runner
and output fixes do not change contract scoring, the deployed source or the
meaning of a receipt. See [V2-TRIAL.md](V2-TRIAL.md) for recovery and completion
criteria; the helper itself never rules, retires or withdraws.

### 16. Recover an ambiguous finalized failure only with a bound event proof

`complete_case.py` and `retry_finalized_probe.py` offer the explicit flag
`--allow-proven-no-messages`, with `--source build/impeach.py` identifying the
exact deployed artifact. The flag defaults to false. Ordinary
`retryable_receipt()` and `classify()` remain strict and unchanged. The proof
path accepts only these two otherwise non-retryable combinations:

| Native status | Execution | Consensus result |
| --- | --- | --- |
| `FINALIZED` | `FINISHED_WITH_RETURN` | `IDLE` |
| `FINALIZED` | `NOT_VOTED` | `MAJORITY_AGREE` |

The [read-only collector](scripts/native_finality_proof.mjs) requires a unique,
canonical EVM receipt containing `TransactionFinalized` from the pinned
FinalizationPhase proxy `0x7de0FF58B401F2D800470e4390e24fF2bAa02AaE` for the exact
native hash. Its `previousStatus` must be 6, 12 or 13 and
`shouldProcessMessages` must be false. The Main event with the same name does
not carry those fields and is insufficient. Receipt, transaction, block and
log identities must agree, the log must not be removed, and protocol pins must
match both the current chain and the event's historical block. Lookup is bounded
to 20,000 blocks in 1,000-block chunks, with at most four concurrent requests;
a recorded EVM hash can be read directly. Missing evidence or RPC failure stops
the proof path without guessing an outcome.

The [bundle validator](scripts/native_failure_proof.py) binds the proof to the
frozen claim, deployed source, original calldata, zero value and native hash.
Before recovery it obtains fresh native `FINALIZED` evidence, checks the exact
claim/challenge/item identities and empty slot, and rechecks unchanged contract
state and the frozen deadline after lookup. Pending, applied, rejected, dead,
unknown or conflicting outcomes do not become eligible through this flag.

`origin: chain_observation` means RPC-observed evidence without a matching local
service journal. It does **not** establish whether finalization was automatic
or submitted by another operator. `origin: service_queue` additionally requires
the matching before/dispatch/EVM hash/receipt/after/done journal and exact Main
finalization call. A stored timeout 12/13 may become 6 before the Phase event;
the validator permits that specific transition while preserving the evidence.

Each recovery row and durable prebroadcast marker stores
`previous_failure_basis=verified_finalized_no_messages`, the relative
`previous_finalization_proof` path and its SHA256. Whole-history validation
rechecks the immutable bundle, original row, receipt, current frozen claim and
artifact; removing or changing evidence prevents further recovery. The limit
of three explicit recoveries, locks and deadline checks still apply. Raw SDK
receipts are never rewritten to make them look negative or successful.

The offline verification baseline is **184 stub contract checks, 156 Python
tests, 47 browser-arithmetic parity checks and 38 Node tests** under supported
Node 24, plus fixture consistency and published-snapshot recomputation. The
Python total includes 31 focused queue-service tests. The separate pinned-SDK
suite remains 150 checks. These tests validate implementation and guards; they
do not establish a real native
verdict or guarantee that validators will finish before a trial deadline.

### 17. Prepare a separate v3 claim without replacing the v2 record

The frozen [v3 claim](calibration/claim-court24-v3.json) uses seed 240526 and
adds the exact prefix `An independent arithmetic exercise states: ` once to
every v2 original, rewrite and control. Arithmetic, answers and classes remain
unchanged; the word “independent” is part of the prompt, not an assertion of an
independent benchmark. Fresh deterministic salts and text hashes are disjoint
from all three earlier claimed corpora. The
[generator](scripts/generate_court24_v3.py) and
[offline audit](calibration/court24-v3-audit.json) record 24 items, 24 rewrites,
four controls and the preserved formulas. Previous claims, contract source and
deployed build remain unchanged.

V3 keeps Llama 3.1 8B on `deepinfra/fp8`, the numeric scoring rule, decoding,
1000‰ oath and thresholds. Its trial window is 21,600 seconds (six hours),
with the same 3,600-second reveal window. The prepared
`/api/live-v3/chat/completions` route has its own `TRIAL_V3_ENABLED` switch,
currently false. The API's four-hour expiry limit and shared $5 lifetime key
cap are unchanged; a longer trial does not extend endpoint access or reset
credit.

The audit's 72-response cross-prompt replay is a local regression check using
unaltered v2 response objects and scripted referee decisions. It is explicitly
not a measurement of the newly prefixed prompts. A separate real Sonnet
calibration is in progress, targeting 112 calls at `max_tokens=512`, with a
$1.80 run cap and total key usage capped at $4.80 below the hard $5 limit. The
[in-progress raw transcript](runs/v3-referee-sonnet-transcript.jsonl) and
[calibration log](runs/v3-referee-calibration.log) do not yet establish a passed
calibration or native result. The full offline checks passed in
[v3-offline-check.log](runs/v3-offline-check.log).

## Found on the way: `withdraw` in Suborn and Jastrow

Impeach's `withdraw` was first copied from Suborn:

```python
_Recipient(Address(gl.message.sender_address)).emit_transfer(value=u256(amount))
```

On the pinned SDK `gl.message.sender_address` is already an `Address`, and
`Address(Address)` raises `TypeError`. The real-SDK run caught it; the stub
cannot, because its `Address` accepts itself.

If Suborn's `withdraw` has never been called on Bradbury, it probably reverts.
Jastrow wraps the same line in `try/except`, which would mean the balance is
zeroed and no transfer is emitted. This was observed in direct mode, not on
chain — check both before anyone relies on them. The fix is to pass the address
through unwrapped.
