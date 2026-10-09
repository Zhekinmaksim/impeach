# OpenRouter subject endpoint

OpenRouter can supply the real subject and the local referee. The contract cannot
send an API key. A gateway adds the server-side key and exposes only the committed
demonstration trial.

The selected setup uses `scripts/openrouter_server.py` with a persistent SQLite
budget and an HTTPS tunnel. This enforces the allocated budget independently of OpenRouter account settings.
The dedicated key also now has a $5 lifetime cap; BYOK is not included in that cap. The Vercel gateway stays disabled; its optional
configuration below requires a capped key because Vercel instances do not share
a durable local ledger.

## Active setup: local gateway with a durable budget

The user approved $5 total. Deduct earlier rehearsal/referee spend before choosing
the gateway's `--budget`. For example, allocate at most $1.50 to preliminary calls
and $3.50 to the gateway, using the same key. Do not continue separate direct API
calls beyond that preliminary allocation while the gateway is running.

```bash
python3 scripts/openrouter_server.py --budget 3.5 --ledger runs/openrouter-budget.sqlite
```

The server loads `.env.local`, binds only `127.0.0.1:8787`, and serves
`/v1/chat/completions` plus `/health`. It accepts exactly the same 72 frozen request
bodies as the Vercel gateway. It uses the subject model and provider in `.env.local`.
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

The current session started a $4 ledger, then permanently reserved an extra
$0.50 for direct referee work. It therefore has at most $3.50 for public calls
without resetting the existing ledger. See `runs/budget-allocation.json`.

The seven offline tests cover real-contract request parity, price/provider caps,
concurrent reservations, restarts, rejected requests and failure accounting.

## Optional Vercel gateway

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
| `TRIAL_BUDGET_USD` | Approved total key limit; currently `5` |
| `TRIAL_EXPIRES_AT` | UTC deadline in `YYYY-MM-DDTHH:MM:SSZ` format, at most 96 hours ahead |

For this optional Vercel setup, use an OpenRouter inference key with a credit limit no higher than $5, no limit
reset, and **include BYOK usage in the limit** enabled. The function checks
`GET https://openrouter.ai/api/v1/key` before every permitted completion. An
unlimited key, a recurring limit, a management key, an exhausted key, or a failed
lookup prevents inference. The same dedicated capped key should cover rehearsal
and referee calls so they share the total allowance.

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

The static page remains in `web/`. The function uses the native Node.js Web
handler in `api/chat/completions.mjs`; it needs no framework or build dependencies.
Use Node.js 22 or later and this function configuration in `vercel.json`:

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
These checks use a fake provider and spend no credits.

| Response | Meaning |
| --- | --- |
| `403 request_not_in_trial` | Model, messages, decoding or fields differ from the committed trial |
| `503 trial_disabled` | Enablement is absent or false |
| `503 trial_not_configured` | Required server environment values are missing/invalid |
| `503 trial_window_invalid` / `trial_expired` | Fix the deadline before opening, or close the completed trial |
| `503 capped_inference_key_required` | The key cap, reset/BYOK setting or key type does not satisfy the gate |
| `503 trial_budget_exhausted` | The provider reports no remaining key allowance |
| `503 budget_check_unavailable` | Key metadata could not be verified; no completion was attempted |
| `429 upstream_unavailable` | The provider rate limited the request |
| `502` / `504` | Provider failure, invalid response or 45-second upstream timeout |

Provider error messages and keys are never sent to the caller. There are no
automatic retries: the contract decides whether to retry a dead probe.

Implementation references: [Vercel Node.js functions](https://vercel.com/docs/functions/runtimes/node-js),
[function configuration](https://vercel.com/docs/project-configuration/vercel-json#functions),
[OpenRouter API](https://openrouter.ai/docs/api_reference/overview),
[provider routing](https://openrouter.ai/docs/guides/routing/provider-selection),
[key metadata](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-api-key).
