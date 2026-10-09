# Validation evidence

The public page is https://impeach.vercel.app and the source is
https://github.com/Zhekinmaksim/impeach.

- `deployment.json`: deployment history, active contract, transaction and artifact hash.
- `bradbury.jsonl`: submitted live-trial transactions, recorded before receipt polling.
  A row proves submission only; `collect.py` checks settled receipts and execution results.
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
- `budget-allocation.json`: the $5 total allocation. Local SQLite reserves every
  public call before dispatch and is deliberately excluded from version control.

One local referee model is not a validator set. Calibration cannot guarantee the
network verdict. API costs are reported in USD; wallet values are testnet GEN.
No credentials are included in these files.
