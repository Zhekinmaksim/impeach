# Impeach — a court for benchmark scores

A published score says a model can do something. It might instead say the model
has seen the answers. Nothing on chain, and almost nothing off it, can tell those
two apart after the fact.

Impeach is a GenLayer court that cross-examines a score. The publisher swears to
a number and bonds it. A challenger stakes that the number came from memory. The
validator set tests the model on the pinned items and on answer-preserving
rewrites of those items generated at judgment time, and rules on the gap.

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

For each admissible probe pair, the model answers the pinned item and the
rewritten item. Both answers are scored against the pinned ground truth by the
rule frozen at `open_claim`.

```text
Δ = accuracy(pinned items) − accuracy(answer-preserving rewrites)
```

A model that can do the task answers both. A model that memorised the set answers
the first and stumbles on the second. Δ is reported in per-mille integer maths so
the contract can compute it without floats.

### Detector 2 — verbatim recall

The model is given the first 40% of a pinned item and asked to continue. The
continuation is compared to the held-out remainder by normalised edit distance,
deterministically, with `strict_eq` — no LLM in the loop at all.

```text
R = share of items where the continuation matches the held-out remainder
    above the pinned similarity threshold
```

Reproducing an item it was never shown in the prompt is not a capability
argument. It is the single most direct evidence of training-set membership, and
it costs one call per item.

### Verdict

Thresholds are frozen at `open_claim`, not chosen after the numbers are in.

| verdict | condition |
| --- | --- |
| `CONTAMINATED` | `Δ ≥ delta_threshold` **or** `R ≥ recall_threshold`, with `n ≥ min_items` |
| `CLEAN` | both below threshold, with `n ≥ min_items` |
| `INCONCLUSIVE` | too few admissible probes, or the endpoint failed to answer |

`INCONCLUSIVE` is a first-class outcome and pays nobody. Borrowed directly from
Jastrow's gate, where it did more work than the other two.

## 5. Admissibility — the Suborn lesson, reused

This is where the project lives or dies, and it is the same failure mode Suborn
found: an attacker who is allowed to change the question will always win.

A rewrite that changes the correct answer is not evidence of contamination. It is
a different question. So every rewrite faces a referee round before its result
counts:

> Does the rewritten item have the same correct answer as the original, for the
> same reason? Ignore wording, ordering, names and surface form.

Two framings, both must agree — the Suborn stage-B shape, which in the live run
caught all three attempts to move the facts. Failed admissibility forfeits the
challenger's stake into the pool.

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
| publisher | bond, sized to the claim | verdict `CLEAN` | verdict `CONTAMINATED`, bond to the challenger |
| challenger | stake per challenge | any admissible round, win or lose | rewrites ruled inadmissible |
| either | — | — | `INCONCLUSIVE` returns both, minus probe costs |

Griefing funds the next case, as in Suborn. The asymmetry is deliberate: an
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
) payable -> claim_id

challenge(claim_id, subset_json, classes_json) payable -> challenge_id
reveal_items(claim_id, items_json)          # hashes must match, set is burned
probe(challenge_id, item_index, mode)       # mode: PINNED | REWRITE | RECALL
rule(challenge_id) -> verdict               # computes Δ and R, settles bonds
certificate(claim_id) -> {...}              # view, readable by other contracts
is_spent(item_hash) -> bool                 # the registry everyone else reads
```

Storage mirrors Suborn: `TreeMap` keyed by id, pull-based balances with a single
`withdraw`, a solvency view asserted in tests after every state change.

## 8. Equivalence principles

- **answering a probe** — `prompt_comparative` requires matching status and
  correctness fields and equivalent extracted answers, ignoring answer formatting.
- **admissibility** — `prompt_comparative` compares independently computed
  original/rewrite answers and the semantic referee's boolean, in two framings.
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
  "ruled_at_block": 1234567
}
```

An agent marketplace, a grant committee or another contract reads this before
trusting a number. That is the consumer outside the project, and its absence is
what keeps most submissions at 13.

## 10. Defaults to start from

| parameter | default | why |
| --- | --- | --- |
| `min_items` | 20 | below this the gap is noise |
| `delta_threshold` | 250 ‰ | a 25-point drop is not explainable by rewrite friction |
| `recall_threshold` | 150 ‰ | three items in twenty reproduced verbatim |
| recall prefix | 40% | enough context to continue, not enough to infer |
| similarity | normalised Levenshtein ≥ 0.9 | tolerant of whitespace, not of paraphrase |
| referee framings | 2 | one was talked around in the Suborn run |

Publish the defaults and let every claim override them in the open, since a
publisher who insists on a 600‰ threshold has told you something.

## 11. Honest limits, stated in the submission

- **Reachability.** The subject must answer a public endpoint. Models behind a
  paid key cannot be tested without handing out the key, which nobody will do.
  v1 covers public endpoints and on-chain agents; everything else is out of scope
  and should be said so rather than fudged.
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
