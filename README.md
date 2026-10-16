<img src="web/assets/logo.svg" alt="Impeach" width="320">

# Impeach — a court for benchmark scores

A published score says a model can do something. It might instead say the model
has seen the answers. Impeach is a GenLayer Intelligent Contract that
cross-examines the score: the publisher swears to a number and bonds it, a
challenger stakes that it came from memory, and the validator set asks the model
the sealed questions and their committed rewrites, then tests verbatim recall.

```text
Jastrow  — is this specification decidable at all
Suborn   — does this specification survive a document written to break it
Impeach  — does this score survive rewritten items and verbatim recall
```

> **Status.** [Live case](https://impeach.click) ·
> [Scripted examples](https://impeach.click/?demo=1) ·
> [Source](https://github.com/Zhekinmaksim/impeach).
> Corrected court `impeach/1.1`: the real-model case is **native FINALIZED / CLEAN**,
> with all **24 admitted pairs and 24 measured recall results**, Δ=0‰ and R=0‰.
> The claim was retired after ruling; its certificate is final.
> [Corrections and native proofs](REVIEW-FIXES.md) document the answer-key and recall
> fixes. The separate 24-item scripted control is also **native FINALIZED**,
> with **CONTAMINATED / RECALL**, 24 admitted pairs and 24 recall matches.

The corrected court is deployed on [Bradbury, chain 4221](https://explorer-bradbury.genlayer.com/address/0xCB67936d0b00b82Ea73611b3C8353a21EBdc7261).
The [build manifest](build/impeach.manifest.json) and
[source verification](runs/review-protocol-and-source-preflight.json) bind the
exact deployed artifact. Previous deployments and their partial trials remain
historical records in [V2-TRIAL.md](V2-TRIAL.md) and [V3-TRIAL.md](V3-TRIAL.md).

## Run it

```bash
make check        # contract, runner regressions, JS parity, verdict recomputation
make check-sdk    # the same scenarios on the real SDK, at the pinned runner hash
make serve        # http://localhost:8000
```

`make check` needs Python 3.10+ and Node 22+, nothing else. `make check-sdk`
needs `pip install -r requirements-dev.txt` and downloads one GenVM release the
first time. In an isolated environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
make check-sdk PY=.venv/bin/python
```

The corrected revision passes 203 local contract assertions, 169 pinned-SDK
assertions, 187 Python regression tests and 52 browser parity checks, together
with the endpoint, gas, receipt and native queue checks. CI runs both local and
pinned-SDK jobs.

## The three mechanisms

**Item sets are consumable.** `open_claim` commits only the hash of each item.
The items stay sealed until a challenge is accepted. `reveal_items` puts them on
chain in full and, in the same transaction, writes every one into the spent
registry — under its sealed commitment and under the hash of its text. Burning
happens at reveal, not at verdict, and it covers the whole set, not only the
items the challenger picked. `is_spent(hash)` is the view other contracts read;
`impeach check` is the command other people run.

**Two independent detectors.**

- *The gap.* For every item the model answers the sealed wording and an
  answer-preserving rewrite. `Δ = accuracy(sealed) − accuracy(rewritten)`, in
  per-mille integers.
- *Verbatim recall.* The model gets the first 40% of a sealed item and is asked
  to continue. The continuation is compared to the held-out part by bounded
  Levenshtein distance, under `strict_eq`. There is no language model anywhere
  in this detector.

**Admissibility.** A rewrite that changes the correct answer is a different
question, not evidence. Every rewrite passes a deterministic gate, then two
referee rounds with different framings; both must agree it is the same question.
A rewrite ruled inadmissible forfeits its share of the stake.

`numeral_substitution` is the sharp one. The answer is required to move with the
numbers, and the contract records when the model answers a rewrite with the
*old* answer (`stale_answers` in the certificate).

## Verdicts

Court revision `impeach/1.1` compares both blind referee results with their
committed answer keys, including text answers. Text comparison normalizes case,
spacing, quote marks, commas, currency signs and trailing periods using `norm_answer`; unlisted synonyms are conservatively
rejected. A semantic `same_question: true` cannot override a mismatched key.
`CLEAN` requires at least `min_items` admitted pairs **and** `min_items` measured
recall results (`MATCH` or `MISS`). Missing, dead and ineligible (`NA`) recall
probes cannot count as negative recall evidence. See [review corrections](REVIEW-FIXES.md).

| verdict | condition | bond |
| --- | --- | --- |
| `CONTAMINATED` | `Δ ≥ delta_threshold` or `R ≥ recall_threshold`, each on at least `min_items` | to the challenger |
| `UNSUPPORTED` | the sworn score does not reproduce on its own sealed items, or the set was already spent | to the challenger |
| `CLEAN` | both under threshold, with at least `min_items` admitted pairs and measured recall results | stays posted |
| `INCONCLUSIVE` | too few admitted pairs or measured recall results, or the endpoint did not answer | stays posted |
| `DEFAULT` | the publisher did not reveal inside the window | to the challenger |
| `UNCONTESTED` | nobody challenged; not a verdict | publisher may retire it |

Two of these are not in the spec. [DECISIONS.md](DECISIONS.md) says why each was
added, along with the answers to the spec's three open questions and five other
places where the build departs from it.

## Lifecycle

```text
open_claim      publisher   terms frozen, bond posted, items sealed
challenge       challenger  subset named blind, stake posted
reveal_items    publisher   items on chain, set burned
probe PINNED    anyone      model answers the sealed item
probe RECALL    anyone      model continues the first 40%
probe REWRITE   challenger  rewrite filed, referee framing one, model answers it
probe ADMIT     anyone      referee framing two
rule            anyone      Δ and R computed, bond and stake settled
certificate     view        what everyone else reads
```

Also: `claim_default` (publisher never revealed), `retire_claim` (publisher takes
the bond back while nobody is challenging), `withdraw`.

## What is in here

```text
contracts/impeach.py       the court
cli/impeach.py             seal · check · envelope · recompute · probe · rule
calibration/               original GSM8K and two frozen synthetic v2 cohorts
examples/rewrites/         24 rewrites across five classes, arithmetic machine-checked
examples/controls/         4 rewrites that change the answer; a referee must stop them
test/                      scenarios, scripted subjects, stub, real-SDK runner
scripts/                   rehearsal, referee replay, native trial/queue helpers, collection
web/                       the page; case.json for the current case, demo.json for examples
spec/SPEC.md               the specification this was built from
```

## How it is tested

`test/scenarios.py` is written against a small driver interface and runs twice:
on a local stub with no dependencies, and on the real GenLayer SDK at the exact
`py-genlayer` runner hash in the contract header, through `genlayer-test`'s
direct mode. The second run uses real typed storage, real calldata round-trips
and the real eq-principle wrappers, and checks that every closure handed to
consensus can be pickled. Only the network is scripted.

The subjects are in `test/population.py`:

| subject | what it is | verdict | Δ | R |
| --- | --- | --- | --- | --- |
| memoriser | lookup table over the sealed set | `CONTAMINATED` | 750‰ | 1000‰ |
| capable | solves the task, 8% honest error | `CLEAN` | 125‰ | 0‰ |
| neither | cannot do it, has not seen it, swears to 90% | `UNSUPPORTED` | 0‰ | 0‰ |

Beyond those three the suite covers: a dead endpoint, a flaky one, one that goes
silent only on questions it does not recognise, a challenger who files rewrites
only where the model was right, a challenger who burns the set and walks away, a
publisher who refuses to reveal, re-salted spent items, one referee framing
fooled, both fooled, a second challenge after `CLEAN`, and solvency after every
single call.

The hashing, flattening and verdict arithmetic exist three times (contract, CLI,
browser). The suite holds the three equal.

## Live validation

The current real subject is `meta-llama/llama-3.1-8b-instruct`, fixed to
DeepInfra FP8, with frozen decode parameters and an allowlisted public Vercel
endpoint. Its fresh trial contains 24 disclosed synthetic arithmetic items.
A separate scripted control uses a stored-answer lookup and a transformed
cohort with disjoint source content hashes. These demonstrations are public,
not independent benchmarks; they make no claim about absence from model training.

The corrected real-model [case record](runs/review-live-final-case.json) contains
24/24 correct original and rewritten answers, 24 recall misses, and both referee
framings admitting all 24 pairs. Its [rule transaction](https://explorer-bradbury.genlayer.com/transactions/0x9e0a82eaee891864a753cdd9dab304368d649ab5d299de91c728fd437a106bec)
is native FINALIZED. The [native proof](runs/review-live-rule-final-native.json)
checks actual TransactionManager state, execution and the deployed source hash.
All 113 transactions in the collected case are finalized, including unsuccessful
consensus attempts, which remain visible rather than being counted as answers.
The [retirement proof](runs/review-live-retire-final-native.json) confirms the
final certificate and return of the 0.1 test GEN bond to internal credit.
The [wallet payment proof](runs/review-withdraw-alice-wallet-final.json) verifies
an exact increase of 0.1 test GEN after native finalization of the withdrawal.

The new scripted control has all 24 original answers correct, all 24 held-out
continuations matching, and all 24 pairs admitted by both framings. Its native FINALIZED
verdict is `CONTAMINATED / RECALL`, with R=1000‰, Δ=208‰ and five stale answers.
See the [control record](runs/review-scripted-final-case.json) and
[native rule proof](runs/review-scripted-rule-final-native.json). The historical
scripted `CONTAMINATED / RECALL` certificate belongs to the previous court and is
preserved in [V2-TRIAL.md](V2-TRIAL.md).

A preceding 72-request real-model rehearsal and an exact-prompt replay of 112
recorded referee responses are calibration evidence, not native verdicts. The
corpora are public regression fixtures and may already have appeared on chain.
They do not establish absence from model training.

The paid route was disabled after the last real subject result finalized. A valid
model POST now returns `503 / trial_disabled`; the scripted route remains free.
Both withdrawals are native FINALIZED, with exact wallet increases of 0.1 and
0.148 test GEN verified. The court owes nothing and holds zero native assets;
[settlement proofs](runs/review-final-settlement.json) retain both payments.
All 254 case transactions and both withdrawals are finalized. Recorded lifetime
OpenRouter usage is approximately $2.03 under the shared $5 cap.
See [OPENROUTER.md](OPENROUTER.md) for gateway policy and prior trial history.

## Limits

- **Reachability.** The subject must answer a public HTTPS endpoint in the
  OpenAI chat-completions shape, with no key. On-chain agents as subjects are
  not implemented in `impeach/1`.
- **Δ is evidence, not proof.** Every model drops a little on rewrites. The
  threshold is a convention; the certificate carries the raw counts so a reader
  can disagree.
- **Burning is irreversible.** A challenge destroys the evaluation value of the
  whole set whatever the verdict.
- **Temperature.** Decode parameters are frozen at `open_claim`. At temperature
  above zero, validator disagreement is expected and shows up as undetermined
  receipts.
- **The demonstration set is not secret.** GSM8K has been public since 2021 and
  the salts are in this repository. The first live case shows the mechanism; it
  cannot show that sealing works, because nothing here was ever sealed.

MIT. Third-party material is listed in [NOTICE.md](NOTICE.md).
