<img src="web/assets/logo.svg" alt="Impeach" width="320">

# Impeach — a court for benchmark scores

A published score says a model can do something. It might instead say the model
has seen the answers. Impeach is a GenLayer Intelligent Contract that
cross-examines the score: the publisher swears to a number and bonds it, a
challenger stakes that it came from memory, and the validator set asks the model
the sealed questions again in words it has not met.

```text
Jastrow  — is this specification decidable at all
Suborn   — does this specification survive a document written to break it
Impeach  — does this score survive items the model has not seen before
```

> **Status.** [Interactive demo](https://impeach.vercel.app) ·
> [Source](https://github.com/Zhekinmaksim/impeach).
> `web/case.json` contains local rehearsals against scripted subjects, visibly
> labelled on the page. It is not a live model finding. Contract scenarios pass
> on the local stub and the pinned real SDK. See [OPENROUTER.md](OPENROUTER.md)
> for a hosted model, [LOCAL-MODEL.md](LOCAL-MODEL.md) for Ollama, and
> [DEPLOY.md](DEPLOY.md) for the on-chain run. Submission evidence is still pending.

The court is deployed on Bradbury (chain 4221) at
`0x774f8ca813724B39775617487ADb4DfCf1eb72D6`.
The [deployment transaction](https://explorer-bradbury.genlayer.com/transactions/0xef103cfa95e7f8408712520076ce00c73454b3bcff01b2ab7eeabfcafb0918cf)
was accepted with `FINISHED_WITH_RETURN`. Source hashes and the failed first
attempt are recorded in `runs/deployment.json`. A deployed court is not a
completed trial; the published case data remains labelled by its actual origin.

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

The verified baseline is 177 contract assertions, 143 pinned-SDK assertions,
47 browser-arithmetic checks, and regression tests for the live runner and
rehearsal. The page has also been checked at desktop and mobile widths.

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
calibration/               24 GSM8K test items, the claim file for the live case
examples/rewrites/         24 rewrites across five classes, arithmetic machine-checked
examples/controls/         4 rewrites that change the answer; a referee must stop them
test/                      scenarios, scripted subjects, stub, real-SDK runner
scripts/                   simulate · rehearse · run_case · collect · referee_dryrun · stub_endpoint
web/                       the page; reads case.json only
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

## Live validation and remaining checks

- **A live trial.** The deployment transaction succeeded. Whether validators agree on
  a model's answer at temperature 0, and how long a probe round takes, is
  unknown until Bradbury.
- **The referee with a real model.** Initial GPT-4.1 and GPT-4.1-mini runs exposed
  false admissions in the supplied controls. The referee now solves both questions
  before seeing their supplied answers, then checks the rewrite in two framings.
  Real-model results and raw responses are recorded in `runs/`. The complete
  24-positive / 4-negative gate must pass before a live claim opens.
- **HTTP inside GenVM.** `gl.nondet.web.post` works in direct-mode tests; a live
  probe must verify public endpoint reachability from validators. The deployed
  contract's `clock()` was checked against current UTC after deployment.

The real subject rehearsal used `meta-llama/llama-3.1-8b-instruct`, fixed to
DeepInfra FP8: 72 requests, sealed accuracy 750‰, rewritten accuracy 708‰,
Δ 41‰ and recall 0‰. Its local forecast is `CLEAN`, with a scripted marker
and referee; it is not a network verdict. Two responses lacked a final answer
at 512 tokens and remained truncated at 1024. They remain errors in the
original 512-token measurement. See `runs/llama-rehearsal.json` and
`runs/llama-requests.jsonl`.

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
