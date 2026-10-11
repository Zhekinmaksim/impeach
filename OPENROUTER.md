# OpenRouter subject endpoint

OpenRouter can supply the real subject and the local referee. The contract cannot
send an API key. A gateway adds the server-side key and exposes only the committed
demonstration trial.

For the prepared fresh trial, use [V3-TRIAL.md](V3-TRIAL.md); the previous run is
preserved in [V2-TRIAL.md](V2-TRIAL.md). As of 11 October 2026,
the scripted native control has a finalized `CONTAMINATED / RECALL` certificate;
the real Llama native case is in progress and no real native verdict is asserted
here. The [control finality handoff](runs/c0-finality-20261011-resume/handoff.json)
records 24 pinned answers, 24 recall matches, 13 admitted pairs, court-adjusted
rewrite score 833‰, Δ=166‰, four stale answers and R=1000‰. This is the disclosed
scripted lookup, not an LLM finding. Its unadmitted rewrites receive the contract's
presumption of correctness; the paired sample is below the 20-item minimum.

For real claim 1, the [10:14 UTC handoff](runs/v2-live-final-native-handoff.json)
and [native audit](runs/v2-live-final-native-audit/audit.json) confirm all 107
recorded hashes are `FINALIZED` and the native queues are empty. Getters still
show 24 pinned `RIGHT`, 24 recall `MISS`, 24 rewrite `RIGHT`, 24 first-framing
`ADMISSIBLE` and only 23 second-framing `ADMISSIBLE` results. Item 14's C2 is
`PENDING` despite its positive finalized receipt. Item 14's and item 23's
final transactions have Phase events with `previousStatus=5` and
`shouldProcessMessages=true`; the
no-messages retry proof does not apply. The 24-pair goal has not been repaired.

No C1 rule, retirement or withdrawal was sent. Automatic approval review
rejected partial 23-pair closure before broadcast; explicit user authorization
has been requested. The saved `CLEAN` calculation is only an offline forecast,
not a ruled native certificate.

## Routes and frozen corpora

| Public path | Fixed claim and corpus | Enablement |
| --- | --- | --- |
| `/api/chat/completions` | `calibration/claim-gsm8k.json`; original GSM8K files | Legacy `TRIAL_ENABLED`; keep false for the v2 run |
| `/api/live-v2/chat/completions` | `calibration/claim-court24-v2.json`; `calibration/court24-v2.items.json`, `examples/court24-v2/rewrites` | Separate `TRIAL_V2_ENABLED=true`; disabled otherwise |
| `/api/scripted-v2/chat/completions` | `calibration/claim-court24-v2-scripted.json`; `calibration/court24-v2-scripted.items.json`, `examples/court24-v2-scripted/rewrites` | Public fixed lookup; no secret, provider or inference cost |
| `/api/live-v3/chat/completions` | `calibration/claim-court24-v3.json`; `calibration/court24-v3.items.json`, `examples/court24-v3/rewrites` | Independent `TRIAL_V3_ENABLED`; currently false |

Each endpoint admits only its own 72 exact JSON request bodies: 24 originals,
24 committed rewrites and 24 recall prefixes. Object key order is immaterial;
models, message text, roles, decoding and extra fields are checked. Only these
four explicit claim/path combinations exist in the loader. Neither a request
nor an environment variable can select an arbitrary file or corpus. The old
allowlist is unchanged. Vercel includes each route's own files through
[vercel.json](vercel.json).

Live v2 and v3 force the narrow credits-only policy described below, regardless of
`TRIAL_CREDIT_ONLY`: Llama 3.1 8B through `deepinfra/fp8`, budget at most $5,
expiry at most four hours, verified lifetime key cap and zero BYOK usage. Their
switches are independent of each other and `TRIAL_ENABLED`. The same lifetime
key allowance covers earlier calibration, rehearsal
and native inference. A deployment, new route, second claim or new time window
does not reset that allowance. The scripted route consumes no OpenRouter credit.

The scripted model ID is `scripted/memoriser-court24-v2`. It returns the original
sealed answer for both the original and corresponding rewrite, including the
five changed-number rewrites, and the exact saved-source tail for recall. Its
health and completions explicitly say `kind: scripted`, `llm: false`; responses
also carry `X-Impeach-Mode: scripted-no-llm`. This is a public control, not a real
LLM response. Both v2 corpora are disclosed synthetic material and share their
mathematics; see the limitations and audits in [V2-TRIAL.md](V2-TRIAL.md).

The prepared [v3 claim](calibration/claim-court24-v3.json) uses seed 240526 and
the exact prefix `An independent arithmetic exercise states: ` on every
original, rewrite and control. It copies v2 arithmetic and answers; the prefix
does not make this an independent benchmark. Fresh salts and disjoint text
hashes are documented in the [offline audit](calibration/court24-v3-audit.json).
The model, provider, decoding, numeric rule, thresholds and 1000‰ oath stay the
same. The trial window is six hours, with a one-hour reveal window; the API
still expires within four hours. The larger trial window does not extend that
API limit or the shared $5 lifetime budget.

V3's earlier replay of 72 old v2 responses remains a cross-prompt local regression
check, with scripted referee decisions, not a new model measurement. The separate
[Sonnet calibration](runs/v3-referee-verified.json) is now complete: 112 actual new
calls with `max_tokens=512` admitted all 24 intended rewrites in both framings and
rejected all four controls in both. Its recorded cost is $0.375864, within the
$1.80 run cap and $4.80 total-key stop below the hard $5 cap. The
[raw transcript](runs/v3-referee-sonnet-transcript.jsonl) is preserved.

The [initial Llama run](runs/v3-llama-initial-coverage-audit.json) made 74 attempts,
with three no-reply outcomes and 71 unique successful requests. One actual
[supplement](runs/v3-llama-supplement.jsonl) supplied missing PINNED item index 21.
The [verified replay audit](runs/v3-llama-verified-audit.json) then matched all 72
recorded responses to the exact new prompts, without additional network calls:
24 correct originals, 24 correct rewrites, 24 recall misses, n=24, Δ=0‰ and R=0‰.
The [local snapshot](runs/v3-llama-verified.json) forecasts `CLEAN` using scripted
admission; it is not native consensus or a certificate. Recorded successful
responses cost $0.00035026; the initial raw errors remain in the record.

The v3 public switch is still false, and no v3 native claim has been opened.
The route targets the existing Vercel project and server-side key; preparation
did not upload that key again. The C1 partial-closure request remains pending;
the fresh 10:46 UTC read still showed item 14's C2 `PENDING`.
The [10:47 UTC budget snapshot](runs/v3-budget-before-activation.json) records
$2.02391728 used and $2.97608272 remaining under the same $5 lifetime key cap,
with zero BYOK usage and no limit reset.

The v2 and v3 claims freeze the exact `NUMERIC_LINE_RULE`: the last nonempty line must
contain literal `ANSWER:` followed by one ASCII decimal and nothing else. The
contract compares canonical numeric results with `strict_eq` and uses no LLM
answer marker for this rule. Both LLM referee framings are still required;
legacy scoring rules retain their semantic marker. The live proxy forwards
model responses unchanged and does not repair a malformed final answer.

`scripts/openrouter_server.py` provides a local gateway with a persistent SQLite
budget and an HTTPS tunnel. The Vercel gateway supports either a key cap that
includes BYOK or a narrow, four-hour credits-only mode described below. Both
Vercel modes remain disabled by default and require a capped key because Vercel
instances do not share a durable local ledger. A lost tunnel URL cannot be
replaced in an already opened claim.

## Native completion and the inference window

Run `complete_case.py` in bounded sessions with a single court/account writer.
For V3, explicitly use `--subject-first --subject-deadline <UTC-epoch-seconds>`
as detailed in [V3-TRIAL.md](V3-TRIAL.md). The deadline must be a positive integer.
All 72 PINNED/RECALL/REWRITE states and their permitted recoveries must apply
before any ADMIT. A subject awaiting finality pauses completion and releases the
lock for queue service/resume. `DEAD`, C1 `INADMISSIBLE` and an unapplied slot with
a positive receipt block this stage; they are not automatically resubmitted.
Without the opt-in, the existing per-item scheduling remains unchanged.

The completion identity freezes the mode and deadline. Standalone recovery
inherits that deadline when its CLI flag is omitted and rejects a different
value or mismatched identity. Immediately before a subject dispatch marker,
the helpers compare UTC wall time and a fresh chain clock with API expiry minus
120 seconds; recovery repeats this check after proof lookup and final reads.
Once all subjects are applied, ADMIT and eligible ADMIT recoveries may continue
inside the court window after API expiry. Already queued calls cannot be
canceled and may execute after expiry; this is a dispatch guard, not a guarantee
of execution latency.

Recovery defaults to one new transaction per failed slot; the explicit
`--max-recoveries 3` setting caps the real-case plan at three recoveries per slot
in addition to the original. Receipt-only recovery keeps the exact payload and
needs a newly verified finalized negative consensus result, or finalized
`IDLE / NOT_VOTED`, with the slot still unapplied and the trial still open.
`DEAD`, semantic referee rejection and a pending/replaying call do not qualify.
Ambiguous `RETURN / IDLE` remains blocked without the explicit proof path below.
The baseline plan makes no automatic appeals, which can rewind descendant
calls. One separately reviewed exception authorized a single zero-bond appeal
for the latest item 14 ADMIT recovery after `LEADER_TIMEOUT`, preserving its
native hash and payload. The [dispatch](runs/v2-live-item14-appeal01/dispatch.json)
and [EVM receipt](runs/v2-live-item14-appeal01/evm-receipt.json) record that bounded
action (`0xd6e15fa9…`). Its native result is now finalized, while the C2 getter
remains pending. Keep all hashes, receipts and durable dispatch
markers; this exception permits no further calls or appeals.

Both completion/recovery helpers accept `--allow-proven-no-messages` and
`--source build/impeach.py`. This opt-in adds only `FINALIZED / RETURN / IDLE`
and `FINALIZED / NOT_VOTED / MAJORITY_AGREE` (status/execution/result order).
Ordinary receipt guards remain unchanged. A unique canonical EVM receipt must
contain the exact native hash's FinalizationPhase event with previous status
6, 12 or 13 and `shouldProcessMessages=false`; the same-named Main event is
insufficient. Current and historical protocol pins, frozen source/claim,
calldata/value, fresh native finality and unchanged empty slot/deadline checks
must all pass. Missing proof or unavailable bounded RPC lookup pauses recovery.

Proof origin `chain_observation` describes evidence read from the chain without
a matching local dispatch journal; it does not claim automatic finalization.
`service_queue` requires the linked service before/dispatch/receipt/after/done
evidence. Every recovery row and prebroadcast marker retains the failure basis,
proof path and SHA256, checked again across the whole history. The
[full proof policy](DECISIONS.md#16-recover-an-ambiguous-finalized-failure-only-with-a-bound-event-proof)
does not increase the recovery limit or change the inference budget.

Between completer sessions, after `<manifest>.complete.lock` is released,
`service_queue.py` may use the same lock to inspect or service native heads.
It is read-only unless `--execute` is supplied. Its only writes are simulated,
zero-value Main finalization/idleness calls for known manifest transactions;
it creates no new probe transactions or rules. It may finalize an already recorded
zero-value rule after exact calldata and identity checks. Never run it alongside
the completer or another signer. An unresolved dispatch requires reconciliation,
not a second send.

Native finalization may occur automatically or through a recorded Main call.
A projected `READY_TO_FINALIZE` status or successful EVM receipt is not itself
native success. The [verified active enums and queue policy](DECISIONS.md#14-preserve-unknown-transactions-instead-of-guessing-a-result)
distinguish native `FINALIZED` from application success. Known stored failure
phases 6/12/13 may be finalized at the actual queue head despite stale outcome
fields, after exact Main simulation and fresh source/calldata checks. Evidence
records `beforeStoredFailurePhase` and `native_success=false`. These annotations
alone do not authorize recovery. Resume the completer only after that helper
releases the lock; it rechecks the frozen deadline and
recovery eligibility.

These native delays do not extend the frozen trial window or the gateway's
four-hour expiry. Validators and recoveries can make repeated paid requests;
the $5 lifetime allowance does not reset between them. Stop inference when the
case is done. Finalization of completed calls may finish after the inference
route has been disabled; unresolved or replaying probes still need the endpoint.
This separation does not promise that the real case will obtain a complete
sample before its deadline.

## Local gateway with a durable budget

The user approved $5 total. Deduct earlier rehearsal/referee spend before choosing
the gateway's `--budget`. For example, allocate at most $1.50 to preliminary calls
and $3.50 to the gateway, using the same key. Do not continue separate direct API
calls beyond that preliminary allocation while the gateway is running.

```bash
python3 scripts/openrouter_server.py --budget 3.5 --ledger runs/openrouter-budget.sqlite
```

The server loads `.env.local`, binds only `127.0.0.1:8787`, and serves
`/v1/chat/completions` plus `/health`. This legacy server accepts the original
GSM8K gateway's 72 frozen request bodies; it is not the v2 corpus selector. It
uses the subject model and provider in `.env.local`.
It never exposes the key, account metadata, arbitrary chat or the referee.

Before **every** upstream call, a SQLite `BEGIN IMMEDIATE` transaction reserves a
conservative cost and commits it to disk. The reservation uses UTF-8 request bytes
plus 1024 framing tokens as an input upper bound, the frozen output token limit,
and a 10% margin, with a minimum of $0.001 per request. The request itself pins
`provider.max_price` to $0.05 per million input tokens and $0.10 per million output
tokens, with a zero per-request fee, one provider and no fallback. If that price/provider is unavailable,
the call fails instead of moving to a more expensive route.

Reservations are never refunded, including on timeout, provider error or process
interruption. Repeated calls each spend another reservation. Concurrent workers
and restarts share the same ledger. Exhaustion returns `503 trial_budget_exhausted`
without making an upstream call. The ledger's budget and trial identity cannot be
changed on restart. This is intentionally conservative and may stop with real
credit remaining.

**Keep the SQLite file.** Deleting it, using another path, or starting another
gateway with a fresh ledger would discard the shared spending history. Keep the
ledger outside Git and deployment output. Its health check reports remaining
reserved budget, not actual provider spend:

```bash
curl --fail-with-body http://127.0.0.1:8787/health
cloudflared tunnel --url http://127.0.0.1:8787
```

Run the server and tunnel as persistent processes for the whole case, keep the
machine awake, and preserve the tunnel URL from `open` to `rule`. Use that URL plus
`/v1/chat/completions` in the live claim. Close the tunnel after `rule`. Public
replays can consume the reserved allowance, but cannot exceed it through this
gateway. Local reservations do not cover unrelated calls using the same key.

For the local rehearsal, use the same gateway without the tunnel:

```bash
python3 scripts/rehearse.py --endpoint http://127.0.0.1:8787/v1/chat/completions \
  --model meta-llama/llama-3.1-8b-instruct
python3 -m unittest discover -s test -p test_openrouter_server.py -v
```

The earlier local-gateway session started a $4 ledger, then permanently reserved an extra
$0.50 for direct referee work. It therefore has at most $3.50 for public calls
without resetting the existing ledger. See `runs/budget-allocation.json`.

The seven offline tests cover real-contract request parity, price/provider caps,
concurrent reservations, restarts, rejected requests and failure accounting.

## Legacy Vercel gateway reference

The commands in this section describe `/api/chat/completions` and its original
GSM8K claim. They do not enable or rehearse v2/v3. Use the route/claim pairing above
and [V3-TRIAL.md](V3-TRIAL.md) for the prepared run.

The function is **disabled by default**. Deploying the site does not enable model
calls. `GET /api/chat/completions` is a free health/configuration check and does not
contact OpenRouter; `status: configured` does not mean a live inference has passed.

### Configuration

Copy `.env.example` to the ignored `.env.local` and put the key there. The selected
starting models are `meta-llama/llama-3.1-8b-instruct` for the subject and
`openai/gpt-4.1-mini` for the local referee. The approved total budget is $5.
`deepinfra/fp8` is the subject provider; verify it remains available before starting.

| Variable | Purpose |
| --- | --- |
| `OPENROUTER_API_KEY` | Dedicated inference key; store as a Vercel Secret |
| `OPENROUTER_MODEL` | Exact subject model ID sent by the claim |
| `OPENROUTER_PROVIDER` | Exact provider slug, currently `deepinfra/fp8` |
| `REFEREE_MODEL` | Local referee only; not exposed through the public endpoint |
| `TRIAL_ENABLED` | Must equal `true` to permit inference; otherwise disabled |
| `TRIAL_V2_ENABLED` | Separate switch for live v2; does not change the legacy endpoint |
| `TRIAL_V3_ENABLED` | Separate switch for live v3; currently false |
| `TRIAL_CREDIT_ONLY` | Optional `true` for the verified DeepInfra credits-only route; defaults to false |
| `TRIAL_BUDGET_USD` | Approved total key limit; currently `5` |
| `TRIAL_EXPIRES_AT` | UTC deadline in `YYYY-MM-DDTHH:MM:SSZ` format; at most 4 hours in credits-only mode, otherwise 96 hours |

For this optional Vercel setup, use an OpenRouter inference key with a credit limit no higher than $5, no limit
reset, and **include BYOK usage in the limit** enabled. The function checks
`GET https://openrouter.ai/api/v1/key` before every permitted completion. An
unlimited key, a recurring limit, a management key, an exhausted key, or a failed
lookup prevents inference. The same dedicated capped key should cover rehearsal
and referee calls so they share the total allowance.

### Narrow credits-only mode

`TRIAL_CREDIT_ONLY=true` is an explicit alternative to the include-BYOK setting,
only for `meta-llama/llama-3.1-8b-instruct` through `deepinfra/fp8`. Before enabling
it, verify in the authenticated OpenRouter provider settings that DeepInfra BYOK
is **Not configured**. That verification was completed for the current session;
do not add a DeepInfra provider key while this mode is active. This mode does not
claim that a request parameter can disable OpenRouter BYOK.

The gateway requires an approved budget of at most $5 and a deadline no more
than four hours ahead. Before every completion it verifies a finite lifetime key
limit no higher than that budget, no limit reset, a non-management inference key,
finite `byok_usage` equal to zero, and at least $0.10 of `limit_remaining`.
Unknown BYOK usage closes the gate. `include_byok_in_limit` may be false only
because this mode depends on the verified absence of a DeepInfra BYOK key.

Both Vercel modes send a fixed provider, disable fallbacks, require support for
the frozen parameters, and set `provider.max_price` to $0.05 per million input
tokens, $0.10 per million output tokens and zero per-request fee. Each route's
model, prompts, decoding and 72-request allowlist remain fixed.

In credits-only mode, the completed upstream response must also explicitly
report `usage.is_byok: false`. A missing or true value returns
`502 credit_only_response_required`. **This is a check after inference: rejecting
the response cannot reverse a charge already incurred.** Account configuration
verification and the OpenRouter credit cap remain necessary. The ten-cent
reserve is an early stop margin, not an atomic reservation across concurrent
serverless instances. Disable the trial when the case ends or if the account's
provider configuration changes. Ordinary mode retains its include-BYOK gate.

The corpus is public, and anyone can repeat an allowed request during the active
window. The allowlist prevents general chat or a more expensive model; it cannot
authenticate validators or prevent replay. OpenRouter enforces the key credit
limit across instances. This application has no local spend counter and makes no
claim about metering lag or Vercel platform charges. Disable the trial after `rule`.

On Vercel, set the key as a server-only Secret for the intended environment and
the other variables as Config values. Changing environment variables requires a
new deployment. Keep `TRIAL_ENABLED=false` until the key, model, cap and live
window are ready. Do not set any `VITE_` or `NEXT_PUBLIC_` key variable.

### Deployment

The static page remains in `web/`. The functions use native Node.js Web handlers
and need no framework or build dependencies. Use Node.js 22 or later. The
committed [vercel.json](vercel.json) includes all four routes and their fixed
corpus files. This minimal example and the commands below illustrate the legacy
GSM8K route; v2/v3 require their explicit claim and route from the table above:

```json
{
  "functions": {
    "api/chat/completions.mjs": {
      "maxDuration": 60,
      "includeFiles": "{calibration/claim-gsm8k.json,calibration/gsm8k-24.items.json,examples/rewrites/*.json}"
    }
  }
}
```

Merge this with the existing configuration. The included corpus is read by the
function, not copied into the static output. Test a deployment with:

```bash
curl --fail-with-body https://impeach.vercel.app/api/chat/completions
```

Do not place Vercel Authentication in front of the live subject URL: validators
must reach its public HTTPS address without cookies or a bearer token.

### First Vercel live call and rehearsal

Once the window is enabled, generate one exact allowed request and check the
answer format. This call spends from the approved key allowance:

```bash
node --input-type=module -e 'import { trialRequests } from "./lib/proxy.mjs"; process.stdout.write(JSON.stringify(trialRequests("meta-llama/llama-3.1-8b-instruct")[0]));' > /tmp/impeach-probe.json
curl --fail-with-body https://impeach.vercel.app/api/chat/completions \
  -H 'Content-Type: application/json' --data-binary @/tmp/impeach-probe.json
```

The completion should end with `ANSWER: <number>`. The proxy forwards the real
completion unchanged, including refusal, wrong answer or `finish_reason: length`.
It never repairs, fabricates, retries or caches model answers.

Run the 72-request rehearsal through the same deployment that will serve the
claim, so it uses the same model and provider routing:

```bash
python3 scripts/rehearse.py \
  --endpoint https://impeach.vercel.app/api/chat/completions \
  --model meta-llama/llama-3.1-8b-instruct
```

Record `answered as sealed` for the sworn score. The model's answer and recall
probes use the exact frozen parameters. If the 512-token answer budget truncates
replies, update `calibration/claim-gsm8k.json` and redeploy **before** opening the
claim. The proxy permits at most 4096 answer tokens; recall remains the contract's
512 tokens. Changing decoding after `open` would invalidate the experiment.

The referee uses different prompts and must call OpenRouter directly; it cannot
use this subject-only endpoint:

```bash
OPENAI_BASE_URL=https://openrouter.ai/api/v1 python3 scripts/referee_dryrun.py
```

The local scripts load `.env.local`. Check the referee report: all 24 intended
rewrites should pass both framings, and all four negative controls should fail.
Do not infer a referee pass from a successful subject rehearsal.

Then prepare the actual claim file with the public endpoint, measured score and
`"model": "meta-llama/llama-3.1-8b-instruct"` in `decode_params`. Follow `DEPLOY.md`.
Keep the deployment, model, provider, prompt template, decoding and allowlist
fixed from `open` through `rule`. The endpoint intentionally supports only the
committed 24 originals, 24 rewrites and 24 recall probes. A different corpus or
new challenger rewrite needs a deliberately updated endpoint before the claim.

### Offline verification and failures

```bash
node --test test/test_proxy.mjs
```

Tests compare the allowlist with all 72 requests emitted by the actual Python
contract. They also cover free health checks, disabled and expired windows,
request injection, token/body limits, provider pinning, key limits, timeouts,
secret-free errors, unchanged responses and repeated requests without caching.
Credits-only tests cover the fixed route, four-hour window, known zero BYOK usage,
ten-cent boundary, lifetime cap and missing or true response BYOK markers.
These checks use a fake provider and spend no credits.

The full offline `make check` baseline on Node 24 is 184 stub contract checks,
173 Python tests, 47 browser-arithmetic parity checks and 38 Node tests, plus
fixture consistency and published-snapshot recomputation. It covers recovery
limits and queue guards as well as endpoints, including 31 focused queue-service
tests. The separate pinned-SDK suite remains 150 checks. These are not a native
trial result.

| Response | Meaning |
| --- | --- |
| `403 request_not_in_trial` | Model, messages, decoding or fields differ from the committed trial |
| `503 trial_disabled` | Enablement is absent or false |
| `503 trial_not_configured` | Required server environment values are missing/invalid |
| `503 credit_only_configuration_required` | Credits-only mode has another model/provider or a budget above $5 |
| `503 trial_window_invalid` / `trial_expired` | Fix the deadline before opening, or close the completed trial |
| `503 capped_inference_key_required` | The key cap, reset/BYOK setting or key type does not satisfy the selected mode's gate |
| `503 trial_budget_exhausted` | No key allowance remains, or credits-only mode has less than $0.10 remaining |
| `503 budget_check_unavailable` | Key metadata could not be verified; no completion was attempted |
| `429 upstream_unavailable` | The provider rate limited the request |
| `502 credit_only_response_required` | The completed response did not explicitly report non-BYOK usage; an upstream charge may already exist |
| `502` / `504` | Provider failure, invalid response or 45-second upstream timeout |

Provider error messages and keys are never sent to the caller. There are no
automatic retries: the contract decides whether to retry a dead probe.

Implementation references: [Vercel Node.js functions](https://vercel.com/docs/functions/runtimes/node-js),
[function configuration](https://vercel.com/docs/project-configuration/vercel-json#functions),
[OpenRouter API](https://openrouter.ai/docs/api_reference/overview),
[provider routing](https://openrouter.ai/docs/guides/routing/provider-selection),
[key metadata](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-api-key).
