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

> **Status.** [Live case](https://impeach.vercel.app) ·
> [Scripted examples](https://impeach.vercel.app/?demo=1) ·
> [Source](https://github.com/Zhekinmaksim/impeach).
> The live Bradbury certificate is `INCONCLUSIVE / TOO_FEW_ADMISSIBLE`:
> 11 answered sealed items, 4 admitted pairs, with a minimum of 20.
> `web/case.json` contains the contract reads and transaction outcomes;
> `web/demo.json` preserves the three clearly labelled scripted examples.
> See [OPENROUTER.md](OPENROUTER.md), [LOCAL-MODEL.md](LOCAL-MODEL.md), and
> [DEPLOY.md](DEPLOY.md) for reproducing the run. Submission is prepared separately.

The court is deployed on Bradbury (chain 4221) at
`0x47b0B5a11fC7F44F8f0d4ABa3A54b1A304AfDD3e`.
The [deployment transaction](https://explorer-bradbury.genlayer.com/transactions/0x28e52e602628b4dfbf5e0972aa10dfe9bda751c3b7284cd3921526dff4cd415e)
is finalized with `AGREE / FINISHED_WITH_RETURN`. Source hashes and the failed first
attempt are recorded in `runs/deployment.json`. The completed trial certificate is linked from the page, together with the failed
and recovered probe transactions.

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

The live subject is `meta-llama/llama-3.1-8b-instruct`, fixed to DeepInfra FP8,
with frozen decode parameters and a public Vercel gateway. The Bradbury trial
opened, challenged and revealed all 24 committed items. Its first item passed
both referee framings and all three native model probes.

The partial run stopped after a leader timeout; the fixed trial window then
expired. The court ruled `INCONCLUSIVE / TOO_FEW_ADMISSIBLE`: 11 sealed answers,
4 admitted pairs and 12 recall probes. Nine of the 11 sealed answers were correct.
The certificate's court-adjusted rewrite score is 1000‰ and its gap is −181‰;
missing or unadmitted rewrites are presumed correct for the publisher, so that
score is not the subject's measured rewrite accuracy. The recall result is 0‰.
None of the detectors reached the 20-item minimum.

The [rule transaction](https://explorer-bradbury.genlayer.com/transactions/0xdd4d149a02291d1901e80f277eca45ac48ec0284b3c57aa74ed8c5cb4bcc4d12)
was accepted with successful execution. `runs/bradbury-vercel.jsonl` preserves
submissions and recovery links; `web/case.json` includes their fetched outcomes.
Leader timeouts, disagreement and execution violations remain visible. They
are not subject answers. The result establishes the native integration and
partial evidence, not a contamination finding or a successful 24-item trial.

The publisher retired the ruled claim; the certificate is retained. Both parties'
credits are being verified through native `withdraw`. The four-hour model API
expired automatically and production is configured disabled. Total OpenRouter
usage, including calibration, is $1.28827328 of the approved $5.

An earlier trial used a temporary tunnel which returned HTTP 502, `no tunnel`,
after passing local preflight. Its immutable endpoint could not be repaired.
That separate court remains pending until 12 October 2026, 22:20:45 in Tashkent;
0.1 GEN bond and 0.023 GEN stake remain locked there. See `runs/live-status.json`.
Its spent registry and failed evidence remain intact.
Gateway restrictions and spending safeguards are documented in
[OPENROUTER.md](OPENROUTER.md).

The initial real-model referee runs exposed false admissions. The revised referee
solves both questions before seeing the proposed answer key, then checks the class
in two framings. GPT-4.1 admitted 20/24 honest rewrites and rejected all 4 controls;
Sonnet 4.6 admitted 14/24 and rejected all 4 controls in both framings. The full
Sonnet transcript and exact offline replay are in `runs/`. These false rejections
are a material limitation: at least 20 admitted pairs are needed for the gap
verdict. Calibration with one model does not guarantee validator agreement.

The deployed clock, native HTTP probes, referee rounds and rule operation have
been exercised on Bradbury. A complete 24-item live evaluation remains outstanding;
the published `INCONCLUSIVE` certificate records the partial trial honestly.

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
