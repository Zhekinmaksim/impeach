# Impeach — a court for benchmark scores

Revision `impeach/1.1` corrections and current validation are tracked in
[REVIEW-FIXES.md](../REVIEW-FIXES.md), dated 16 October 2026.
The following trial history describes the earlier deployment: the scripted control is
finalized `CONTAMINATED / RECALL`. Real C1 has a finalized 23-pair `CLEAN` ruling
and retirement; its incomplete 24-pair record
is tracked in [V2-TRIAL.md](../V2-TRIAL.md). The active fresh run is in
[V3-TRIAL.md](../V3-TRIAL.md). V3 has no native verdict yet. Local calibration
does not establish one.

A published score says a model can do something. It might instead say the model
has seen the answers. Nothing on chain, and almost nothing off it, can tell those
two apart after the fact.

Impeach is a GenLayer court that cross-examines a score. The publisher swears to
a number and bonds it. A challenger stakes that the number came from memory. The
validator set tests the model on pinned items and challenger-proposed rewrites
that preserve declared class invariants, and rules on the gap and recall.

```text
Jastrow  — is this specification decidable at all
Suborn   — does this specification survive a document written to break it
Impeach  — does this score survive items the model has not seen before
```

Same instrument, third subject. Jastrow measured disagreement about a rule.
Suborn attacked the document the rule was applied to. Impeach attacks the claim
that a measurement meant anything.

Name note: `Mutiny` (18, Aug) used "impeachment" for revoking agent authority,
a different sense. If the collision bothers you, `Perjury` and `Laches` are
unused and fit the same vocabulary.

---

## 1. Why this belongs on GenLayer

A single model cannot audit a model. An off-chain harness run by the publisher
measures what the publisher chose to measure, and an off-chain harness run by the
challenger is equally unfalsifiable. The judgment needs a population of
independent judges that neither party picked, applying a rule fixed before the
items were revealed.

That is the GenLayer primitive, and this is one of the few domains where the
slowness of consensus costs nothing: a score is a durable claim, and taking an
hour to rule on it is fine.

## 2. The mechanism nobody else has

**Item sets are consumable.** This is the part that makes the project memorable,
and it falls out of the domain rather than being bolted on.

A contamination case cannot be audited without revealing the items. Revealing the
items contaminates them for everyone, forever. So Impeach treats an evaluation
item set the way a court treats a witness who has testified: once used in public,
it is spent.

- at `open_claim`, the publisher commits only the **hash** of each item
- items stay sealed until a challenge is accepted
- at judgment the items are revealed on chain, in full, permanently
- the moment they are revealed, the set is written into a public **spent
  registry**, and no later claim against that set is admissible

The registry is the thing other people will actually use. Anyone citing a
leaderboard can ask: has this item set been burned? A benchmark whose items are
in the registry is no longer evidence of anything.

## 3. Roles and lifecycle

```text
publisher                    challenger                  validators
    │                             │                           │
    ├─ open_claim ────────────────┼──────────────────────────►│  terms frozen
    │   score, item hashes,       │                           │
    │   prompt template, decode   │                           │
    │   params, endpoint, bond    │                           │
    │                             │                           │
    │                             ├─ challenge ──────────────►│  stake posted
    │                             │   names perturbation      │
    │                             │   classes and subset      │
    │                             │                           │
    ├─ reveal_items ──────────────┼──────────────────────────►│  set burned
    │                             │                           │
    │                             │                      probe rounds
    │                             │                   ┌───────┴────────┐
    │                             │                   │ A: pinned item │
    │                             │                   │ B: rewrite     │
    │                             │                   │ C: admissible? │
    │                             │                   │ D: verbatim?   │
    │                             │                   └───────┬────────┘
    │◄────────────────────────────┴───────────────────────────┤  verdict
    │                                                         │
    └─ certificate written, bond settled, set registered as spent
```

## 4. What is actually measured

Two detectors, deliberately independent. One is semantic and expensive, one is
syntactic and cheap. A verdict that rests on both is much harder to argue with
than either alone.

### Detector 1 — the gap

The model answers the pinned item and the rewritten item. Each is marked against
its own reference answer under the scoring rule frozen at `open_claim`; a
permitted numeral substitution changes the reference. The implemented gap uses
every item with a live pinned answer. A missing or rejected rewrite is presumed
correct, so selectively omitting pairs cannot increase the gap. An admitted
rewrite that fails to answer counts as wrong.

```text
Δ = 1000 × (pinned_right − court_adjusted_rewrite_right) / live_pinned_items
```

A model that can do the task answers both. A model that memorised the set answers
the first and stumbles on the second. Δ is reported in per-mille integer maths so
the contract can compute it without floats.

The optional `NUMERIC_LINE_RULE` is selected only when the claim freezes exactly
the constant in [contracts/impeach.py](../contracts/impeach.py). It requires the
last nonempty, whitespace-trimmed line to begin with literal `ANSWER:` and then
contain one ASCII decimal number, optionally negative, with no other content.
`ANSWER: -003.500` is valid and canonicalizes to `-3.5`; units, commas, `+3`,
exponents, `.5`, `5.`, Unicode digits and text after the answer are invalid.
Leading integer zeros, trailing fractional zeros and negative zero do not change
the value. Equality uses decimal strings, without floating-point rounding.

This rule marks the subject's real response deterministically and compares the
status, canonical answer and correctness across validators with `strict_eq`.
It makes no LLM marking call. A malformed final answer is wrong, not silently
repaired. Every other frozen scoring-rule string retains the semantic LLM marker
and `prompt_comparative` answer equivalence. A publisher cannot switch rules
after opening a claim.

### Detector 2 — verbatim recall

The model is given the first 40% of a pinned item and asked to continue. The
continuation is compared to the held-out remainder by normalised edit distance,
deterministically, with `strict_eq` — no LLM in the loop at all.

```text
R = share of items where the continuation matches the held-out remainder
    above the pinned similarity threshold
```

This costs one subject call per eligible item. Recall is evidence of reproduced
text under this protocol, not proof of training-set membership: public text,
predictable wording or an explicit lookup can also produce recall. The scripted
control deliberately implements such a lookup and is labeled accordingly.

### Verdict

Thresholds are frozen at `open_claim`, not chosen after the numbers are in.

| verdict | condition |
| --- | --- |
| `CONTAMINATED` | gap reaches its threshold with enough admitted pairs, or recall reaches its threshold with enough eligible recall probes |
| `UNSUPPORTED` | enough live pinned items, no contamination detector trips, and sworn accuracy exceeds measured pinned accuracy by at least `delta_threshold` |
| `CLEAN` | neither detector nor score shortfall trips, with at least `min_items` admitted pairs and at least `min_items` measured recall results |
| `INCONCLUSIVE` | too few admissible probes, insufficient measured recall, or the endpoint failed to answer |

`INCONCLUSIVE` is a first-class outcome. Slice refunds/forfeitures and the
`ENDPOINT_SILENT` reimbursement still apply; it does not mean nobody was paid.
`DEFAULT` and `UNSUPPORTED / SET_ALREADY_SPENT` also cover failure to reveal and
reuse of an already burned source, respectively. See [DECISIONS.md](../DECISIONS.md).

Revision `impeach/1.1` returns `INCONCLUSIVE / TOO_FEW_RECALL` when admitted pairs
meet the minimum but recall does not. Only `MATCH` and `MISS` count as measured
recall; `NA`, `DEAD` and missing results never do. Each referee framing also
requires the blind solver's original and rewritten results to match the supplied
answer keys: canonical decimal equality for a numeric pair, deterministic
`norm_answer` equality otherwise. A true semantic Boolean cannot bypass either
comparison. Text aliases beyond that normalization are not admitted automatically.

## 5. Admissibility — the Suborn lesson, reused

This is where the project lives or dies, and it is the same failure mode Suborn
found: an attacker who is allowed to change the question will always win.

A rewrite counts only when it preserves its declared class invariant and both
reference answers are correct. Two referee framings must independently return
`ADMISSIBLE`; rejection in either framing forfeits that item's stake slice to
the publisher. A valid rejection is a completed judgment, not a consensus error
to retry until it passes.

Each framing makes two `exec_prompt(..., response_format="json")` calls. A blind
solver receives the two questions without the answer keys. A separate semantic
class judge checks the keys and invariant. The recorded computed answers come
from the blind solver; the judge supplies a genuine Boolean `same_question`.
For numeric reference pairs, canonical decimal results and that Boolean are
compared by `strict_eq`. Nonnumeric pairs retain `prompt_comparative` equivalence.
After consensus, both computed answers must still match their references.

The response parser accepts one unambiguous JSON object: bare, in a single JSON
code fence, or surrounded by optional prose. It refuses competing objects,
multiple code blocks, non-object JSON and invalid field types. It never chooses
the favorable object or turns a string such as `"true"` into a Boolean. A parse
failure closes admissibility. This also applies to the legacy answer marker.

**Perturbation classes** are declared by the publisher at `open_claim`, so a
challenger cannot demand absurd rewrites, and declared again per challenge, so
the record says which lever was pulled:

| class | invariant that must survive |
| --- | --- |
| `paraphrase` | the question asked, and the answer |
| `numeral_substitution` | the arithmetic structure; the answer changes with it |
| `option_permutation` | the option set; only the order moves |
| `distractor_swap` | the correct option; distractors are replaced |
| `entity_rename` | the relations; names and places change |
| `unit_change` | the quantity; the units are converted |
| `format_shift` | the content; the layout changes |

`numeral_substitution` is the interesting one: the answer is *supposed* to change,
and the referee checks that the new answer follows from the new numbers. A
memorising model answers with the old number, which is a very clean signal.

## 6. Economics

| who | posts | gets it back | loses it |
| --- | --- | --- | --- |
| publisher | bond, sized to the claim | remains posted after `CLEAN`; credited on permitted retirement | `CONTAMINATED`, `UNSUPPORTED` or default, as specified by the settlement |
| challenger | stake per challenge | any admissible round, win or lose | rewrites ruled inadmissible |
| either | — | — | `INCONCLUSIVE` returns both, minus probe costs |

Forfeited slices go to the publisher, not a shared pool. The asymmetry is deliberate: an
honest challenger who fails to find contamination pays nothing beyond gas,
because the published misses are the half of the record that makes a `CLEAN`
certificate worth anything.

## 7. Contract interface

```python
open_claim(
    subject: str,            # model identifier or agent contract address
    endpoint: str,           # public HTTPS endpoint, documented request shape
    score_milli: int,        # the claim, per mille
    item_hashes: str,        # JSON array of sha256, the sealed set
    scoring_rule: str,       # frozen text: how an answer is marked correct
    prompt_template: str,    # frozen, including system prompt
    decode_params: str,      # temperature, top_p, max_tokens, seed if any
    classes: str,            # allowed perturbation classes, comma separated
    delta_threshold: int,    # per mille
    recall_threshold: int,   # per mille
    min_items: int,
    bond: int,
    stake: int,              # stake per challenged item
    extras: str,             # JSON recall and time-window settings
) payable -> claim_id

challenge(claim_id, subset_json, classes_json) payable -> challenge_id
reveal_items(claim_id, items_json)          # hashes must match, set is burned
probe(challenge_id, item_index, mode, payload) # PINNED | REWRITE | RECALL | ADMIT
rule(challenge_id) -> verdict               # computes Δ and R, settles bonds
certificate(claim_id) -> {...}              # view, readable by other contracts
is_spent(item_hash) -> bool                 # sealed commitment or unsalted content hash
```

Storage mirrors Suborn: `TreeMap` keyed by id, pull-based balances with a single
`withdraw`, a solvency view asserted in tests after every state change.

## 8. Equivalence principles

- **answering a numeric-line probe** — `strict_eq` compares canonical numeric
  results and correctness; there is no LLM marker. Other frozen rules use the
  semantic marker and `prompt_comparative`.
- **admissibility** — two framings, each with a blind solver and semantic class
  judge. Numeric pairs use `strict_eq` on canonical results and a Boolean;
  nonnumeric pairs use `prompt_comparative`.
- **verbatim recall** — `strict_eq` on an integer similarity bucket. No LLM.
- **the model call itself** — each validator calls the endpoint independently.
  Receipts preserve a failure to reach consensus. An undetermined result can
  arise from timeouts or execution violations; it does not by itself establish
  that the subject gave inconsistent answers. Inspect the vote reasons before
  attributing a failed round to the model.

## 9. The certificate

```json
{
  "claim_id": 7,
  "subject": "vendor/model-name@2026-09",
  "verdict": "CONTAMINATED",
  "delta_milli": 412,
  "recall_milli": 180,
  "admissible_probes": 48,
  "inadmissible_rewrites": 6,
  "items_burned": 24,
  "spec_hash": "…",
  "ruled_at": 1791633600
}
```

An agent marketplace, a grant committee or another contract reads this before
trusting a number. That is the consumer outside the project, and its absence is
what keeps most submissions at 13.

### Native finality and recovery evidence

Application ruling and native transaction finalization are separate facts.
A transaction may finalize automatically or through an explicit Main call;
both need a fresh native receipt. A successful EVM transaction alone does not
prove native consensus or application execution. Preserve original native
hashes, failed receipts, recovery links and any EVM finalization evidence.

The active Bradbury deployment is chain 4221, ConsensusMain proxy
`0x0112Bf6e83497965A5fdD6Dad1E447a6E004271D`, implementation
`0x0a2C393975dA79505ED930eFC55ae4AEB88b0d62`, `VERSION=2.0.0`, release
`v0.5:9c68608`. Its [verified status table](../runs/v2-native-status-audit.json)
has 11 `READY_TO_FINALIZE`, 12 `VALIDATORS_TIMEOUT`, 13 `LEADER_TIMEOUT` and
14 `LEADER_REVEALING`; the v0.6 reassignment does not apply. Status 14 remains
pending. The [verified outcome table](../runs/v2-native-outcome-enum-audit.json)
is:

| Code | Consensus result | Vote / execution result |
| --- | --- | --- |
| 0 | `IDLE` | `NOT_VOTED` |
| 1 | `MAJORITY_AGREE` | `FINISHED_WITH_RETURN` |
| 2 | `MAJORITY_DISAGREE` | `FINISHED_WITH_ERROR` |
| 3 | `MAJORITY_TIMEOUT` | `TIMEOUT` |
| 4 | `DETERMINISTIC_VIOLATION` | `NONDET_DISAGREE` |
| 5 | `NO_MAJORITY` | undefined |

Saved raw SDK labels are unchanged. The result normalizer accepts old `AGREE`,
`DISAGREE` and `TIMEOUT` names as aliases; unknown numeric codes and conflicting
fields stop processing. A leader returning a value does not establish majority
agreement. `FINALIZED` may close a failed transaction: stored `UNDETERMINED` (6),
`VALIDATORS_TIMEOUT` (12) and `LEADER_TIMEOUT` (13) can retain stale outcome fields.
Queue evidence records their numeric `beforeStoredFailurePhase` and
`native_success=false`; `beforeStoredUND` is true specifically for phase 6.
These annotations alone do not prove that a replacement probe is safe.

The completion helper defaults to one recovery per slot. Explicit
`--max-recoveries 3` permits at most three new transactions after the original.
The receipt-only path requires a fresh finalized negative result or finalized
`IDLE / NOT_VOTED`, unchanged inputs, an unapplied slot and an open trial.
It preserves each previous row, receipt hash and ordinal. Pending/replaying,
applied, inadmissible and dead slots are not resent. Ambiguous `RETURN / IDLE`
without the explicit proof below remains blocked.

V3 explicitly opts into `complete_case.py --subject-first`: all 72
PINNED/RECALL/REWRITE states and eligible subject recoveries must apply before
any ADMIT. A subject awaiting finality causes a bounded exit and releases the
lock for queue service/resume. `DEAD`, first-framing rejection and a positive
receipt with an unapplied slot do not permit blind retries or entry into C2.
The default per-item scheduling is unchanged.

The optional `--subject-deadline` is a positive integer UTC epoch; completion
requires `--subject-first` when it is supplied. V3 sets it to API expiry.
Completion identity freezes this policy and the input hash. Standalone recovery
inherits the saved deadline if omitted and rejects a mismatched deadline or
identity. UTC wall time and a fresh chain clock must both be below expiry minus
120 seconds immediately before subject dispatch markers; recovery repeats the
check after proof lookup and final reads. Once all subjects apply, ADMIT and
eligible ADMIT recoveries can continue inside the court window after API expiry.
Already queued calls cannot be canceled and may execute after expiry. This
dispatch limit does not guarantee execution before the endpoint closes.

The baseline run policy uses no automatic appeals, since they can rewind later
calls. A single separately reviewed exception was made for the latest item 14
ADMIT recovery after `LEADER_TIMEOUT`: one zero-bond appeal, with the same native
hash and unchanged payload. Its [dispatch](../runs/v2-live-item14-appeal01/dispatch.json)
and [EVM receipt](../runs/v2-live-item14-appeal01/evm-receipt.json) preserve the
action (`0xd6e15fa9…`). This exception does not authorize additional probe calls
or appeals, and does not change the completion or recovery helpers' behavior.

The optional `--allow-proven-no-messages` flag in both helpers, together with
`--source` naming the exact deployed artifact (default `build/impeach.py`),
permits only two additional combinations: `FINALIZED / FINISHED_WITH_RETURN /
IDLE` and `FINALIZED / NOT_VOTED / MAJORITY_AGREE`, in status/execution/result
order. Ordinary receipt classification and retry predicates are unchanged.
The proof must contain a unique canonical EVM receipt with a matching
`TransactionFinalized` event from the pinned FinalizationPhase proxy
`0x7de0FF58B401F2D800470e4390e24fF2bAa02AaE`, previous status in `{6,12,13}` and
`shouldProcessMessages=false`. The same-named Main event is insufficient.
Current and event-block protocol pins, event/transaction/block identities,
frozen source and claim, original calldata/value and fresh native `FINALIZED`
state must match. Recovery rechecks exact slot identities, unchanged empty
state and the frozen deadline after lookup. Unavailable or missing evidence
halts this path.

An RPC-observed proof without a linked local service journal has origin
`chain_observation`, which makes no claim about automatic versus manual
finalization. Origin `service_queue` additionally binds the matching
before/dispatch/EVM receipt/after/done evidence. Each recovery row and durable
marker stores the failure basis, relative proof path and SHA256; whole-history
validation binds these to the original row, receipt and current frozen
claim/source. Raw receipts remain unchanged. See
[decision 16](../DECISIONS.md#16-recover-an-ambiguous-finalized-failure-only-with-a-bound-event-proof).

After a bounded completer exits and releases its exclusive manifest lock,
`service_queue.py` may hold the same lock to service known native heads. It is
read-only by default. Explicit execution permits only zero-value Main finalize
or mature-phase idleness calls after protocol/source/claim/calldata checks and
exact gas simulation. Known stored failure phases 6/12/13 are eligible only at
the actual finalized-queue head, with fresh source/calldata checks and exact
Main simulation, even if their outcome fields are stale. Main simulation can
establish eligibility even when the older `ConsensusData.canFinalize` view is
false. An idleness attempt is limited
to one per hash/phase/round/timestamp fingerprint; unresolved dispatch or lack
of native progress prevents blind repetition. A previously recorded, verified
zero-value rule can be finalized, but the service never creates rules, probes,
appeals, retirements or withdrawals. Resume completion only after its lock is
free. Trial deadlines and ordinary receipt-only recovery predicates remain
unchanged.

The finalized [scripted control proof](../runs/c0-finality-20261011-resume/handoff.json)
records 24 pinned answers, 24 recall matches, 13 admitted pairs, rewrite score
833‰, Δ=166‰, four stale answers and R=1000‰. The recall detector has enough
items; the paired detector does not. The rewrite score is court-adjusted across
all 24 live pinned items, including presumed-correct unadmitted rewrites. This
is a native certificate for an explicitly scripted lookup, not a real LLM
result or a completed real-case certificate.

The real C1 [handoff at 11 October 2026, 10:14 UTC](../runs/v2-live-final-native-handoff.json)
and [full audit](../runs/v2-live-final-native-audit/audit.json) establish 107/107
recorded native hashes `FINALIZED` and empty queues. Application getters still
record 24 pinned `RIGHT`, 24 recall `MISS`, 24 rewrite `RIGHT` and 24
first-framing `ADMISSIBLE` outcomes, but only 23 second-framing `ADMISSIBLE`
outcomes. Item 14 remains C2 `PENDING` after its positive finalized receipt
`0xa264c368…`, `MAJORITY_AGREE / FINISHED_WITH_RETURN`, round 2 and referee
output `53 / 53 / true`.

Both item 14 and item 23 [Phase finalization events](../runs/v2-live-two-finalization-events.json)
have `previousStatus=5` and `shouldProcessMessages=true`. This does not meet
the no-messages proof predicate above. Native finality has not repaired the
missing applied pair; its cause remains unresolved. Automatic approval review
initially rejected partial 23-pair closure before broadcast; the user later
authorized that closure and bond return. The
[rule](../runs/v2-live-rule01/result.json), `0x58bffcd…`, was `ACCEPTED`, and its
[certificate](../runs/v2-live-rule01/after.json) records `CLEAN`, n=23, Δ=0‰ and
R=0‰. The [retirement](../runs/v2-live-retire01/result.json), `0x39c253d…`, was
also `ACCEPTED`: [state](../runs/v2-live-retire01/after.json) is `RETIRED`, bond
zero, and 0.1 GEN credited internally. No wallet withdrawal has been sent.
Both the [rule](../runs/v2-c1-rule-final-native.json) and
[retirement](../runs/v2-c1-retire-final-native.json) now have actual stored native
`FINALIZED / FINISHED_WITH_RETURN` receipts. The
[collected case](../runs/v2-live-case.json) records n=23 and 109 finalized native
transactions. Application `final=true` denotes retirement; native finality is
established by the receipts. The result does not complete the 24-pair objective
or change item 14's pending C2.

## 10. Defaults to start from

| parameter | default | why |
| --- | --- | --- |
| `min_items` | 20 | below this the gap is noise |
| `delta_threshold` | 250 ‰ | frozen operational cutoff for the gap and sworn-score shortfall |
| `recall_threshold` | 150 ‰ | three items in twenty reproduced verbatim |
| recall prefix | 40% | enough context to continue, not enough to infer |
| similarity | normalised Levenshtein ≥ 0.9 | tolerant of whitespace, not of paraphrase |
| referee framings | 2 | one was talked around in the Suborn run |

Publish the defaults and let every claim override them in the open, since a
publisher who insists on a 600‰ threshold has told you something.

The current v2 trials keep `min_items=20`, `delta_threshold=250` and
`recall_threshold=150`; changing parsing or consensus representation did not
lower these thresholds. The public synthetic cohorts use seeds 240524 and
240525. The scripted cohort adds a disclosed worksheet prefix to the same
arithmetic and uses fresh salts, giving disjoint registry content hashes. It is
not an independent benchmark, secret data, or evidence of worldwide novelty or
absence from model training. See the two audits linked in [V2-TRIAL.md](../V2-TRIAL.md).

The separate frozen [v3 claim](../calibration/claim-court24-v3.json) uses seed
240526 and adds `An independent arithmetic exercise states: ` exactly once
to each of the 24 originals, 24 rewrites and four controls. Answers, formulas
and classes are copied from v2; this prefix is not evidence of an independent
benchmark. The [generator audit](../calibration/court24-v3-audit.json) verifies
fresh salts and no content-hash or commitment collisions with the three prior
claimed corpora. Previous corpora, contract source and build are unchanged.

V3 retains the numeric rule, decoding, Llama 3.1 8B/DeepInfra subject, 1000‰ oath
and detector thresholds. Its reveal window is 3,600 seconds and trial window
21,600 seconds. The active `/api/live-v3/chat/completions` route is separately
gated by `TRIAL_V3_ENABLED=true`. The inference API retains its four-hour
expiry limit and the same shared $5 lifetime key cap; six hours of trial time
does not extend endpoint access.

The 72 old-response replay in the generator audit remains a cross-prompt local
regression check with scripted referee decisions, not a new subject measurement.
The separate [Sonnet calibration](../runs/v3-referee-verified.json) completed
112 actual new calls at `max_tokens=512`: 24/24 intended rewrites admitted in
both framings and 4/4 controls rejected in both, at a recorded cost of $0.375864.
The [raw transcript](../runs/v3-referee-sonnet-transcript.jsonl) is preserved.
The run stayed within its $1.80 cap and $4.80 total-key stop under the hard $5 cap.

The [initial Llama run](../runs/v3-llama-initial-coverage-audit.json) made 74
attempts with three no-reply outcomes and 71 unique successful requests. One
actual [supplement](../runs/v3-llama-supplement.jsonl) supplied missing PINNED
item index 21. The [exact new-prompt replay audit](../runs/v3-llama-verified-audit.json)
then consumed all 72 recorded responses without more network calls: 24 correct
originals, 24 correct rewrites, 24 recall misses, n=24, Δ=0‰ and R=0‰. Recorded
successful responses cost $0.00035026; initial errors remain saved. The
[local snapshot](../runs/v3-llama-verified.json) forecasts `CLEAN` with scripted
admission, not native validator consensus.

V3 [claim/challenge 2/2](../runs/v3-native-setup/result.json) entered `TRIAL` at
11:00:47 UTC on 11 October; its court deadline is 17:00:47 UTC. Subject probing
has begun and no V3 native verdict is asserted. The
[verified gateway](../runs/v3-live-activation-verified.json) is active until
14:51:29 UTC (19:51:29 Tashkent), fixed epoch `1791730289`, with subject dispatch
cutoff 14:49:29 UTC. Legacy and v2 paid routes are off. The existing Vercel
project and key are reused without another key upload. Follow
[V3-TRIAL.md](../V3-TRIAL.md) for the active run and final-certificate gates.
The [10:47 UTC pre-activation snapshot](../runs/v3-budget-before-activation.json)
records $2.02391728 used and $2.97608272 remaining under the shared $5 lifetime
key cap, zero BYOK usage and no limit reset.

## 11. Honest limits, stated in the submission

- **Reachability.** The implemented subject interface is public HTTPS without
  validator credentials. A bounded server-side proxy can hold a paid provider
  key without revealing it. An on-chain subject interface is not implemented.
- **Δ is evidence, not proof.** Some drop on rewrites is normal for every model.
  The threshold is a convention, and the certificate carries the raw numbers so a
  reader can disagree with it.
- **Burning items is irreversible.** A challenge destroys the evaluation value of
  the set. That is correct, and it means a frivolous challenge has a real cost to
  the commons, which is an argument for a higher stake than Suborn used.
- **Temperature.** A model served at temperature > 0 will produce spread that is
  not contamination. Decode params are frozen at `open_claim` and the certificate
  records them.

## 12. Build order

1. contract with the two detectors, offline tests against a stub model, solvency
   invariant — this is most of the work and it is all testable without a chain
2. a scripted model population for tests: one that memorised the set, one that
   can do the task, one that does neither. The suite asserts the court separates
   all three
3. perturbation corpus for one real public benchmark subset, with the
   admissibility referee run over it before anything goes near Bradbury
4. CLI: `impeach probe`, `impeach rule`, and `impeach check <item-hash>` against
   the spent registry — the last one is the piece other builders install
5. deploy, one live case against a reachable open model, receipts collected the
   Jastrow way: record the hash at submit, build the report later
6. page: the claim, the two detectors side by side, every probe pair readable in
   full, and the spent registry as a searchable list

The current offline `make check` baseline is 184 stub contract checks,
173 Python tests, 47 browser-arithmetic parity checks and 38 Node tests on
Node 24, plus fixture consistency and published-snapshot recomputation. The
Python total includes 31 focused queue-service tests; the separate pinned-SDK
suite remains 150 checks. These checks cover contract behavior and orchestration
guards without establishing
native validator agreement or a real-subject verdict.

## 13. Open questions worth deciding before writing code

**Who pays for the model calls?** Each validator calling an endpoint 48 times is
48 × validator-set-size requests. Either the publisher funds it as part of the
bond, or probes are sampled rather than exhaustive. Sampling is cheaper and
weakens the number; decide explicitly and say which.

**Should `CLEAN` be purchasable?** A publisher can open a claim against a set
nobody will ever challenge and wave the certificate around. Either require a
minimum challenge window with an open bounty before `CLEAN` is issued, or mark
uncontested certificates differently. The second is simpler and more honest.

**Does a burned set retire the score too?** If the items are spent, the original
score can never be re-verified. Arguably the certificate should carry the score's
own expiry. This is the kind of detail that reads as rigour in a submission.
