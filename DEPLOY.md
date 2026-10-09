# Going live

This is the reproducible deployment procedure. Current deployment receipts and
model runs are in `runs/`; the README distinguishes completed checks from the
remaining live trial. Credentials stay in ignored local files or the OS keychain.

## 0. Prove it runs

```bash
make check
make check-sdk
python3 test/test_runner.py
```

If either is red, stop.

## 1. Run the referee over the corpus

Before a stake rides on the admissibility referee, run the contract's two
framings against a real model. Each framing now has a blind solve call, without
the supplied answer key, followed by a separate semantic judgment:

```bash
export OPENAI_BASE_URL=…   OPENAI_API_KEY=…   REFEREE_MODEL=…
python3 scripts/referee_dryrun.py
```

Expected: all 24 rewrites in `examples/rewrites/` pass both framings, all 4
controls in `examples/controls/` are stopped by at least one. If an honest
rewrite is refused, fix the rewrite or the framing now — on chain it costs a
slice of the stake and a pair out of the sample. `--print-prompts` shows exactly
what is sent.

The rewrites most likely to be argued with are the three `unit_change` ones
(`examples/rewrites/01`, `12` and `17`): they restate a quantity in another unit rather than changing
what is asked. If a referee reads the class more strictly than that, refile them
as `paraphrase`.

## 2. Decide what stands trial

The subject must answer a public HTTPS endpoint, OpenAI chat-completions shape,
with no key. Two honest options:

**A subject with a known verdict.** `scripts/stub_endpoint.py` serves the
scripted memoriser. Put it behind a public HTTPS tunnel and the live case
demonstrates the `CONTAMINATED` path end to end. Say plainly in the submission
that the subject is a lookup table: this proves the court, not a finding.

**A real open model.** Stand up a small proxy in front of an open-weights model
you pay for, key on the server side, rate-limited. Fix temperature at 0. The
verdict is then unknown in advance, which is the point. GSM8K is old and widely
trained on, so either outcome is plausible and either is a result.

Doing A first and B second is the cheapest order: A shows that every code path
settles on Bradbury before B spends a model bill.

Check the endpoint by hand before opening a claim:

```bash
curl -s $ENDPOINT -H 'content-type: application/json' \
  -d '{"model":"…","messages":[{"role":"user","content":"What is 2+2? Finish with ANSWER: <number>."}],"temperature":0}'
```

The contract reads `choices[0].message.content` and treats anything else,
including any status other than 200, as a dead probe.

## 3. Deploy and smoke-test

```bash
python3 scripts/build_contract.py
node scripts/genlayer_write.mjs --deploy build/impeach.py --dry-run \
  --from 0xYOUR_PUBLIC_ACCOUNT --rpc https://rpc-bradbury.genlayer.com
node scripts/genlayer_write.mjs --deploy build/impeach.py \
  --account YOUR_ACCOUNT --rpc https://rpc-bradbury.genlayer.com
export CONTRACT=0x…

genlayer call $CONTRACT clock      # must be close to now, in unix seconds
genlayer call $CONTRACT defaults
genlayer call $CONTRACT counts
```

The readable 62 KB source exceeds Bradbury's per-transaction gas cap when
deployed directly. The generated artifact removes comments and docstrings,
checks that executable AST is unchanged, and compresses the remaining source
using `zlib` and `base64` from the pinned CPython runtime. It preserves every
method, storage field, prompt, and executable statement. Inspect
`build/impeach.readable.py` and `build/impeach.manifest.json` to verify the
unpacked code and hashes. Rebuild after any contract edit. The compact artifact
passes the same 143 pinned-SDK scenarios as the original source.

The bridge checks chain identity, estimates under the 16,777,216 transaction
gas cap, and simulates with the selected gas before signing. `--dry-run` uses
only the public address and never reads a private key, signs, or submits.
Oversized or reverting estimates stop the command; there is no gas fallback.
After deployment, wait for a successful accepted/finalized receipt and obtain
the contract address from its `recipient` field before the smoke tests.

`clock` is the one runtime assumption the reveal and trial windows rest on. If
it is wrong, do not open a claim.

## 4. Two accounts

The contract refuses a publisher challenging their own claim. Create and fund a
`publisher` and a `challenger` account in the GenLayer CLI.

## 5. Run the case

Set `subject` and `endpoint` in `calibration/claim-gsm8k.json`, then:

```bash
python3 scripts/run_case.py open      --address $CONTRACT --account publisher
python3 scripts/run_case.py challenge --address $CONTRACT --claim-id 0 --account challenger
python3 scripts/run_case.py reveal    --address $CONTRACT --claim-id 0 --account publisher
python3 scripts/run_case.py probes    --address $CONTRACT --challenge-id 0 --account challenger
# wait for the first pass to settle
python3 scripts/run_case.py admit     --address $CONTRACT --challenge-id 0 --account challenger
python3 scripts/run_case.py retry     --address $CONTRACT --challenge-id 0 --account challenger
python3 scripts/run_case.py rule      --address $CONTRACT --challenge-id 0 --account challenger
```

Each write waits for `ACCEPTED` or `FINALIZED` **and**
`FINISHED_WITH_RETURN`. Acceptance of an error receipt stops the runner.
Every step takes `--dry-run`. Every submitted hash is immediately appended to
`runs/bradbury.jsonl`. If interrupted or timed out, re-run the same command:
it resumes receipt tracking for recorded hashes before sending anything new.
Use `--wait-timeout 1800` when consensus needs more than the default 600 seconds.
An undetermined or failed transaction requires receipt inspection; it is never
blindly resubmitted.

Use a separate `--manifest runs/<case>.jsonl` for each case, including the
scripted subject and real model. The runner checks the contract address and
call inputs so a manifest cannot silently skip a new claim. Pass that same
file to `scripts/collect.py` when publishing a non-default case.

About 100 transactions for 24 items: 3 to set up, 72 in the first probe pass, up
to 24 admits, 1 to rule. Defaults in the claim file: bond 0.1 GEN, stake 0.001
GEN per item.

**Do the first three probes by hand and look at them** before running the pass:

```bash
python3 scripts/run_case.py probes --address $CONTRACT --challenge-id 0 --account challenger --subset 0
genlayer call $CONTRACT get_probe --args 0 0
```

The first `PINNED` is the first time `gl.nondet.web.post` runs inside GenVM for
this contract. The first `RECALL` is the first `strict_eq` over a live endpoint.
The first `REWRITE` is the first transaction with two nondeterministic blocks.
If any of the three comes back undetermined, find out why before sending 70
more.

The runner's subset, receipt, and restart behavior has offline regression
coverage. This does not establish that a Bradbury transaction has succeeded.

## 6. Collect and publish

```bash
make publish CONTRACT=$CONTRACT
```

This reads every receipt through the SDK and the same RPC used for contract
reads, records consensus status and execution result, reads settled state, writes
`web/case.json` with provenance `bradbury`, and recomputes the verdict from the
published probes. Transactions that ended undetermined are counted per probe
mode and kept in the snapshot. If nothing has settled it exits non-zero and the
rehearsal snapshot stays where it is.

When the snapshot is live the rehearsal banner disappears on its own.

## 7. Withdraw

```bash
genlayer write $CONTRACT withdraw     # from each account that is owed
genlayer call  $CONTRACT solvency
```

Do this before submitting. It is the first real exercise of native value leaving
the contract, and the same line is suspect in Suborn and Jastrow (see
DECISIONS.md).

## 8. Ship the page

```bash
python3 scripts/set_site.py https://your-domain    # share tags need absolute URLs
vercel --prod
```

`vercel.json` publishes `web/` only. Until `set_site.py` has run, `og:image` is
a relative path and most link previews will come up without the card.

The card and icons are committed. `make assets` re-renders them from
`design/og.html` and `web/favicon.svg` if either changes.

## 9. Fill in the submission

`SUBMISSION.md` is written except for the evidence block. Take every number in
it from receipts and from `web/case.json`.
