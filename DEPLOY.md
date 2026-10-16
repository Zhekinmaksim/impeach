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

The bundled Vercel proxy only accepts the frozen corpus requests; the generic
`2+2` request above intentionally gets `403 request_not_in_trial`. Test that proxy
with an allowed request instead (once its trial window has been enabled):

```bash
node --input-type=module -e 'import {trialRequests} from "./lib/proxy.mjs"; console.log(JSON.stringify(trialRequests("meta-llama/llama-3.1-8b-instruct")[0]))' > /tmp/impeach-preflight.json
curl -sS "$ENDPOINT" -H 'content-type: application/json' --data-binary @/tmp/impeach-preflight.json
```

## 3. Deploy and smoke-test

This run used GenLayer CLI 0.39.1 with its genlayer-js 1.1.8 SDK and legacy
Bradbury consensus VERSION 2.0.0. The receipt status table is specific to that
release family; check it before switching to Consensus v0.6 tooling.

The legacy-compatible SDK update also adds `14 = LEADER_REVEALING` while
keeping `11 = READY_TO_FINALIZE`, `12 = VALIDATORS_TIMEOUT`, and
`13 = LEADER_TIMEOUT`; see
[the official enum change](https://github.com/genlayerlabs/genlayer-js/commit/2af6928e2587091fb33f5f703160c8a160606048).
This phase only waits on the original hash. It is neither success nor a decided
failure and never authorizes a duplicate. The installed SDK 1.1.8 may return
the raw numeric value without a name.

```bash
export RPC=https://rpc-bradbury.genlayer.com
python3 scripts/build_contract.py
node scripts/genlayer_write.mjs --deploy build/impeach.py --dry-run \
  --from 0xYOUR_PUBLIC_ACCOUNT --rpc https://rpc-bradbury.genlayer.com
node scripts/genlayer_write.mjs --deploy build/impeach.py \
  --account YOUR_ACCOUNT --rpc https://rpc-bradbury.genlayer.com
export CONTRACT=0x…

genlayer call $CONTRACT clock --rpc $RPC      # must be close to now, in unix seconds
genlayer call $CONTRACT defaults --rpc $RPC
genlayer call $CONTRACT counts --rpc $RPC
```

The readable 71 KB source exceeds Bradbury's per-transaction gas cap when
deployed directly. The generated artifact removes comments and docstrings,
checks that executable AST is unchanged, and compresses the remaining source
using `zlib` and Base85 from the pinned CPython runtime. It preserves every
method, storage field, prompt, and executable statement. Inspect
`build/impeach.readable.py` and `build/impeach.manifest.json` to verify the
unpacked code and hashes. Rebuild after any contract edit. The compact artifact
passes the same 150 pinned-SDK scenarios as the original source.

The bridge checks chain identity, estimates under the 16,777,216 transaction
gas cap, and simulates with the selected gas before signing. `--dry-run` uses
only the public address and never reads a private key, signs, or submits.
Oversized or reverting estimates stop the command; there is no gas fallback.
After deployment, wait for a successful accepted/finalized receipt and obtain
the contract address from its `recipient` field before the smoke tests.

`clock` is the one runtime assumption the reveal and trial windows rest on. If
it is wrong, do not open a claim.

The bridge also accepts `--max-rotations 7`, or the per-process environment
variable `IMPEACH_CONSENSUS_MAX_ROTATIONS=7` when running the Python helpers.
This permits more leader rotations inside a new consensus transaction and can
lengthen its pending phase. It does not change the benchmark or the initial
committee size. The override is bounded to 1..7; omission keeps the SDK default.
Before signing, the bridge decodes the actual `addTransaction` calldata and
refuses an unexpected committee size or rotation budget. The review run's
[read-only simulation](runs/review-rotations7-dry-run.json) confirms five initial
validators and seven rotations on Bradbury. Use a longer receipt wait when
enabling the larger budget. An already applied result never becomes retryable.

## 4. Two accounts

The contract refuses a publisher challenging their own claim. Create and fund a
`publisher` and a `challenger` account in the GenLayer CLI.

## 5. Run the case

Set `subject` and `endpoint` in `calibration/claim-gsm8k.json`, then:

```bash
export MANIFEST=runs/my-case.jsonl  # choose a fresh file for a new case
python3 scripts/run_case.py open      --address $CONTRACT --account publisher --rpc $RPC --manifest $MANIFEST
python3 scripts/run_case.py challenge --address $CONTRACT --claim-id 0 --account challenger --rpc $RPC --manifest $MANIFEST
python3 scripts/run_case.py reveal    --address $CONTRACT --claim-id 0 --account publisher --rpc $RPC --manifest $MANIFEST
python3 scripts/run_case.py probes    --address $CONTRACT --challenge-id 0 --account challenger --rpc $RPC --manifest $MANIFEST
# wait for the first pass to settle
python3 scripts/run_case.py admit     --address $CONTRACT --challenge-id 0 --account challenger --rpc $RPC --manifest $MANIFEST
python3 scripts/run_case.py retry     --address $CONTRACT --challenge-id 0 --account challenger --rpc $RPC --manifest $MANIFEST
python3 scripts/run_case.py rule      --address $CONTRACT --challenge-id 0 --account challenger --rpc $RPC --manifest $MANIFEST
```

Each write waits for `ACCEPTED` or `FINALIZED` **and**
`FINISHED_WITH_RETURN` with `AGREE` or `MAJORITY_AGREE`. The sole compatibility
exception is an older compact `ACCEPTED` receipt that omits the consensus result;
an explicit unknown or contradictory result is never treated as success.
Acceptance of an error receipt stops the runner.
Every step takes `--dry-run`. Every submitted hash is immediately appended to
`runs/bradbury.jsonl`. If interrupted or timed out, re-run the same command:
it resumes receipt tracking for recorded hashes before sending anything new.
Use `--wait-timeout 1800` when consensus needs more than the default 600 seconds.
An undetermined or failed transaction requires receipt inspection; it is never
blindly resubmitted.

The v2 process uses [`complete_case.py`](scripts/complete_case.py), then
[`service_queue.py`](scripts/service_queue.py) after the completer has exited
and released its lock. Read [V2-TRIAL.md](V2-TRIAL.md) for the frozen v2 claim
files, bounded commands and source/implementation checks. Both helpers share
`<manifest>.complete.lock`; only one account writer runs at a time.

The active Bradbury v0.5 protocol permits zero-bond appeals of some decided
failures, but eligibility must be confirmed by exact simulation. An SDK
`canAppeal` field alone is insufficient. Late appeals can rewind subsequent
unfinalized transactions, including accepted probe results. The v2 real trial
uses finalized guarded recovery and queue servicing by default; its helpers
never appeal automatically. One separately reviewed zero-bond appeal was sent
for the latest timed-out C2 recovery on item 14, after checking the native queue,
unchanged source and exact Main simulation. The original hash, appeal receipt
and subsequent state observations are retained in
[the appeal journal](runs/v2-live-item14-appeal01). Acceptance of that replay
does not establish that the application state applied; check native finality
and both supported state versions before ruling. Historical control appeals
also remain in the evidence.

To continue other items after inspecting and saving a failed receipt, repeat
the runner command with `--acknowledge-failed <hash>`. This only skips a known
failed outcome; it does not count it as an answer or send it again. Pending
transactions and unknown or contradictory finalization fields still stop progress.
For `FINALIZED`, a known negative consensus result or known unsuccessful execution
can be acknowledged. This includes a leader timeout that finishes as
`FINALIZED / NOT_VOTED / IDLE`: finalization did not execute the contract.

A new probe attempt is allowed only after the old transaction actually reaches
`FINALIZED` with a negative consensus result, or exactly
`FINALIZED / NOT_VOTED / IDLE`, and its contract slot is still empty. All outcome
fields must be known and consistent. An agreed contract error can be acknowledged
to continue other work, but this recovery helper does not retry it.
Expiry of the appeal window alone is not finalization. The bridge can request
finalization; its simulation rejects an attempt before the network permits it:

```bash
node scripts/genlayer_write.mjs --finalize <original-tx-hash> --account challenger --rpc https://rpc-bradbury.genlayer.com
python3 scripts/retry_finalized_probe.py --address $CONTRACT --account challenger --rpc $RPC --manifest $MANIFEST --tx <original-tx-hash> --dry-run
# Inspect the dry run, then repeat without --dry-run for the permitted recovery.
```

Recovery checks the original input signature, zero value, untouched slot and
open trial window. It preserves the finalized receipt and appends a new manifest
row with `previous_tx`, its ordinal, the preceding row and immutable receipt.
Default recovery is one attempt; explicit `--max-recoveries 3` permits at most
three per slot, each after a new finalized failure. Do not run recovery
concurrently with the ordinary runner or queue service on the same account.
Before sending, it also saves a durable dispatch marker. If interrupted before
the new hash is recorded, it refuses another attempt until the on-chain outcome
and manifest have been reconciled; do not remove that marker and blindly resend.

Use a separate `--manifest runs/<case>.jsonl` for each case, including the
scripted subject and real model. The runner checks the contract address and
call inputs so a manifest cannot silently skip a new claim. Pass that same
file to `scripts/collect.py` when publishing a non-default case.

About 100 transactions for 24 items: 3 to set up, 72 in the first probe pass, up
to 24 admits, 1 to rule. Defaults in the claim file: bond 0.1 GEN, stake 0.001
GEN per item.

**Do the first three probes by hand and look at them** before running the pass:

```bash
python3 scripts/run_case.py probes --address $CONTRACT --challenge-id 0 --account challenger --subset 0 --rpc $RPC --manifest $MANIFEST
genlayer call $CONTRACT get_probe --args 0 0 --rpc $RPC
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
make publish CONTRACT=$CONTRACT MANIFEST=$MANIFEST RPC=$RPC
```

This reads every receipt through the SDK and the same RPC used for contract
reads, records consensus status, consensus decision and execution result, reads ruled state, writes
`web/case.json` with provenance `bradbury`, and recomputes the verdict from the
published probes. Transactions that ended undetermined are counted per probe
mode and kept in the snapshot, including an original failed attempt when a later
recovery succeeds. Offline `--from-json` reads are labelled `simulation`, never
verified chain evidence. If no certificate has been ruled it exits non-zero and the
rehearsal snapshot stays where it is.

When the snapshot is live the rehearsal banner disappears on its own.

## 7. Withdraw

After `CLEAN` or `INCONCLUSIVE`, the bond remains posted. If the publisher wants
to close that standing claim and recover the bond, first retire it:

```bash
node scripts/genlayer_write.mjs $CONTRACT retire_claim --account publisher --rpc $RPC --args-json '["0"]'
```

Then withdraw each account's available credit:

```bash
genlayer write $CONTRACT withdraw --rpc $RPC  # from each account that is owed
genlayer call  $CONTRACT solvency --rpc $RPC
```

On Bradbury, native transfer messages use `onAcceptance: false`. An accepted
`withdraw` clears the contract credit, while the wallet payment waits for network
finalization. Confirm a successful `FINALIZED` receipt and the recipient's wallet
balance increase after gas fees; a zero credit alone does not prove payment.
The bridge's `--receipt <hash>` preserves the recipient, value and transfer flag.

Do this before submitting. It is the first real exercise of native value leaving
the contract, and the same line is suspect in Suborn and Jastrow (see
DECISIONS.md).

### Earlier tunnel trial

The separate court at `0xD08Ee3B08b338539748b0D310b6709B4E77a627F` has a
frozen three-day trial window. Its 0.1 GEN bond and 0.023 GEN stake cannot be
settled before **12 October 2026, 17:20:45 UTC / 22:20:45 Tashkent**.
`runs/live-status.json` records that deadline and the failed tunnel. The available
0.001 GEN challenger credit was withdrawn separately; it does not close this claim.

After the deadline, read `clock` and `get_challenge(0)` on that court, call
`rule(0)`, and inspect the certificate and both credits. If the claim is standing,
the publisher can call `retire_claim(0)` before withdrawing. Use the SDK bridge
above with this old address and the matching publisher/challenger account. Record
each new hash in `runs/bradbury.jsonl`, retain its receipt, and confirm native
payments after finalization. Do not mix this court's manifest with
`runs/bradbury-vercel.jsonl`, or send these settlement calls before its deadline.

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
