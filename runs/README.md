# Validation evidence

The public page is https://impeach.vercel.app and the source is
https://github.com/Zhekinmaksim/impeach.

- `deployment.json`: deployment history, active contract, transaction and artifact hash.
- `bradbury.jsonl`: submitted live-trial transactions, recorded before receipt polling.
  A row proves submission only; `collect.py` checks settled receipts and execution results.
- `live-status.json`: the original tunnel trial and its endpoint failure. Its claim
  is still pending until the immutable timeout permits settlement.
- `bradbury-vercel.jsonl`: the new trial using the permanent Vercel endpoint.
  `vercel-first-probe-appeal.log` records recovery of a leader timeout on the same
  transaction; the original failed-round receipt is retained separately.
- `vercel-live-status.json` and `web/case.json`: the ruled partial trial,
  `INCONCLUSIVE / TOO_FEW_ADMISSIBLE`, with 11 sealed answers and 4 admitted pairs.
  The registry contains all 24 revealed items. The fixed trial window expired.
- `vercel-rule.log`, `vercel-retire.log`, and `vercel-withdraw-*.json` / `.log`:
  rule, bond retirement, native payout messages and wallet verification. An
  accepted withdrawal waits for finalization before its EVM message pays out.
- `tunnel-withdraw-challenger.log`: withdrawal of the earlier trial's already
  available 0.001 GEN. The remaining 0.123 GEN stays locked until its old deadline.
- `vercel-api-health-after-expiry.json`: the free endpoint check confirms the
  four-hour gateway expired; production is also configured with `TRIAL_ENABLED=false`.
- `vercel-trial-config.json`: sanitized activation settings and the API expiry.
  The key is a Vercel server Secret, with a $5 lifetime credit cap and no reset.
- `consensus-failures.jsonl` and `consensus-appeals.jsonl`: inspected failures,
  explicit acknowledgements and bounded zero-bond leader recovery. Raw receipts
  are retained alongside them. A timeout or `NO_MAJORITY` is not a model answer.
- `vercel-item2-rewrite-diagnostics.json`: limits of the available debug replay;
  it does not identify the cause of the validators' execution-violation votes.
- `llama-requests.jsonl`: 72 real subject requests and unmodified OpenRouter responses.
- `llama-rehearsal.json`: local forecast with a scripted marker/referee, not chain evidence.
  Sealed 750‰, rewritten 708‰, gap 41‰, recall 0‰. Two truncated answers remain errors.
- `llama-token-check.json`: two diagnostic 1024-token retries; neither produced a final
  answer. These retries do not replace responses in the 512-token rehearsal.
- `referee-gpt41mini.json` and `referee-gpt41.json`: original-prompt failures, retained.
- `referee-gpt41-blind.json`: blind-solving revision; 20/24 honest rewrites admitted,
  all four controls rejected. Some provider responses were not captured in this run.
- `referee-sonnet46-blind-transcript.jsonl`: interrupted first Sonnet run, whose prose
  before fenced JSON exposed the parser defect. All 26 responses are retained.
- `referee-sonnet46-focused-v2.json`: after the parser repair, two honest unit rewrites
  pass both framings and all four controls fail both; raw transcript and cost summary
  are alongside it. The full corpus run is recorded separately.
- `referee-sonnet46-blind-v2.json`: full revised Sonnet run; 14/24 honest rewrites
  admitted and all four controls rejected. The replay file classifies failures;
  this run does not establish that 20 pairs will be admitted on-chain.
- `budget-allocation.json`: the historical local gateway's $5 allocation. That
  gateway reserved calls in SQLite and was stopped before the Vercel trial.
  `openrouter-budget-current.json` records safe usage metadata for the shared
  lifetime cap; neither file contains the key.

One local referee model is not a validator set. Calibration cannot guarantee the
network verdict. API costs are reported in USD; wallet values are testnet GEN.
No credentials are included in these files.
