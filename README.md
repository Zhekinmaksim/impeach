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

> **Status.** [Live case](https://impeach.vercel.app) ·
> [Scripted examples](https://impeach.vercel.app/?demo=1) ·
> [Source](https://github.com/Zhekinmaksim/impeach).
> The v2 scripted lookup control is finalized `CONTAMINATED / RECALL`:
> all 24 pinned answers and recall matches, with 13 admitted rewrite pairs.
> The real v2 attempt finalized all 107 transactions, but its stored C2 results
> contain only 23 admitted pairs; item 14 remains pending after one reviewed
> leader-timeout appeal. It has not been ruled or presented as a full trial.
> A fresh v3 cohort passed real model and referee calibration for a six-hour court window, with
> finalized recovery and no automatic appeals. Its model route stays disabled
> until verification; its public inference window remains at most four hours.
> [V2-TRIAL.md](V2-TRIAL.md) records the evidence and limits.
> [V3-TRIAL.md](V3-TRIAL.md) records the fresh cohort and model deadline policy.
> Submission will be filled together after completion.

The current court is deployed on Bradbury (chain 4221) at
`0x45F610cefF1ed367d684A1839b1801Af12Cfb038`.
The [deployment transaction](https://explorer-bradbury.genlayer.com/transactions/0x2cce6952dc55539449ee434cd50dc6cd91357ec3bff37876ee97f4a9c1d2c941)
is finalized with `MAJORITY_AGREE / FINISHED_WITH_RETURN`. The
[deployment record](runs/v2-deployment.json) preserves exact source and artifact
hashes. The old partial real trial is retained in
[runs/v1-final-case.json](runs/v1-final-case.json).

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

The verified baseline is 184 contract assertions, 150 pinned-SDK assertions,
173 Python runner/regression tests, 47 browser-arithmetic checks and 38 Node
tests for the endpoints, gas guards, receipt output and native queue inspection. The page has also been checked at desktop and mobile widths.

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

| verdict | condition | bond |
| --- | --- | --- |
| `CONTAMINATED` | `Δ ≥ delta_threshold` or `R ≥ recall_threshold`, each on at least `min_items` | to the challenger |
| `UNSUPPORTED` | the sworn score does not reproduce on its own sealed items, or the set was already spent | to the challenger |
| `CLEAN` | both under threshold on at least `min_items` admitted pairs | stays posted |
| `INCONCLUSIVE` | too few admitted pairs, or the endpoint did not answer | stays posted |
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

The scripted native certificate is finalized `CONTAMINATED / RECALL`:
24/24 pinned answers were correct and 24/24 held-out continuations matched.
Thirteen rewrite pairs were admitted by both referee framings, with four stale
answers. The court-adjusted rewrite score is 833‰, Δ is 166‰ and R is 1000‰.
The recall detector reaches its 20-item minimum; the paired detector does not.
Missing or unadmitted rewrites are presumed correct for the publisher, so
833‰ is not measured accuracy on admitted pairs alone. The
[finality handoff](runs/c0-finality-20261011-resume/handoff.json) proves the
[rule](https://explorer-bradbury.genlayer.com/transactions/0xd2970d5c785db84c92cfbf71924d8b719e29f8e48b29715b9da9c345e9c5ed77)
and an empty native court queue. This result describes the scripted subject.

The fresh real trial is in progress. Its preceding 72-call real-model rehearsal
answered both originals and rewrites at 1000‰, with Δ=0‰ and R=0‰; it used
scripted referee admission in the local contract harness. Separately, 112 real
Sonnet 4.6 calls, replayed through the corrected parser and exact prompt cache,
admitted all 24 intended rewrite pairs and rejected all four negative controls
in both framings. Raw transcripts are retained. Neither local result is a
native verdict or a guarantee of agreement among GenLayer validators.
See [V2-TRIAL.md](V2-TRIAL.md) for the frozen policies, source hashes and evidence.

The original real-model trial on the previous court ended
`INCONCLUSIVE / TOO_FEW_ADMISSIBLE` after its fixed window expired: 11 sealed
answers, four admitted pairs and 12 recall probes, below the 20-item minimum.
Nine sealed answers were correct; adjusted rewrite score 1000‰, Δ=−181‰, R=0‰.
Its failed transactions remain visible in [the historical snapshot](runs/v1-final-case.json).
The publisher retired that claim; withdrawals of 0.116 GEN and 0.008 GEN were
finalized and both wallet increases verified after fees. This partial result
establishes integration and limited evidence, without a contamination finding.

An earlier trial used a temporary tunnel which returned HTTP 502 after local
preflight. That separate court remains pending until 12 October 2026, 22:20:45
in Tashkent; 0.1 GEN bond and 0.023 GEN stake remain locked there. Its evidence
and spent registry are preserved in [runs/live-status.json](runs/live-status.json).
The $5 OpenRouter allowance is shared across every rehearsal and live run;
gateway restrictions and spending safeguards are in [OPENROUTER.md](OPENROUTER.md).

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
