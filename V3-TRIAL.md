# Fresh full trial after the v2 storage discrepancy

Prepared on 11 October 2026. No v3 native result is claimed in this snapshot.
The court remains `0x45F610cefF1ed367d684A1839b1801Af12Cfb038` on Bradbury,
chain 4221; deployed source and artifact are unchanged. V2 finalized all 107
transactions but retained only 23 C2 admissions. Its pending item 14, reviewed
appeal and rejected partial-closure attempt remain in
[the handoff](runs/v2-live-final-native-handoff.json) and [V2-TRIAL.md](V2-TRIAL.md).
No partial ruling is sent without the user's separate authorization.

## What is frozen

The [claim](calibration/claim-court24-v3.json) uses 24 fresh commitments and
normalized text hashes, [24 rewrites](examples/court24-v3/rewrites) and
[four negative controls](examples/court24-v3/controls). This is a disclosed
prefixed copy of the earlier arithmetic, not an independent benchmark. The
[generator](scripts/generate_court24_v3.py) and [audit](calibration/court24-v3-audit.json)
preserve its construction, seed 240526 and exact arithmetic checks.

Llama 3.1 8B on DeepInfra FP8 remains fixed, with temperature 0, top_p 1,
max_tokens 512 and seed 7. The oath is 1000‰, bond 0.1 GEN, slice stake
0.001 GEN, min_items 20, delta threshold 250‰ and recall threshold 150‰.
The court window is six hours; the reveal window is one hour. These terms
do not lengthen the public gateway's maximum four-hour window or reset the
shared lifetime $5 OpenRouter budget.

## Actual calibration

[Sonnet calibration](runs/v3-referee-verified.json) made 112 new calls:
all 24 intended rewrites passed both framings, and all four negative controls
were rejected by both. It cost $0.375864. Old v2 referee prompts were not used
as substitutes for new calls.

The [initial Llama rehearsal](runs/v3-llama-rehearsal.log) made 74 attempts,
with three no-reply outcomes and 71 distinct successful responses. The missing
request was PINNED item index 21. [One actual supplement](runs/v3-llama-supplement.jsonl)
completed it. The initial errors and partial snapshot are preserved.
[Exact new-prompt replay](runs/v3-llama-verified-audit.json) then consumed all
72 recorded responses without network access: 24 correct originals, 24 correct
rewrites, 24 recall misses, no dead slots, Δ=0‰ and R=0‰. Recorded successful
responses cost $0.00035026. This establishes a local `CLEAN` forecast with
scripted admission, not native validator consensus.

## Native scheduling and limits

Use one account writer and one manifest,
`runs/bradbury-v3-live.jsonl`. Read the current counters instead of assuming
claim/challenge IDs; the [preflight](runs/v3-native-preflight.json) observed
2/2 as the next IDs and all 48 new commitment/text checks unspent.

Activate only `/api/live-v3/chat/completions` using `TRIAL_V3_ENABLED`.
The legacy and v2 paid routes stay off. Record the actual UTC expiry and
its epoch seconds before dispatch; keep that value unchanged on resume.
Then verify production's 72-request policy, a real inference, blocked other
corpora and the lifetime key cap before opening, challenging and revealing.

The opt-in `--subject-first` stage requires all PINNED, RECALL and REWRITE
states to apply before any ADMIT. It also handles their permitted recoveries
first. If a subject transaction awaits actual FINAL, release the completer's
lock, service its verified native queue and resume. `DEAD` answers and rejected
rewrites do not become automatically retryable.

```bash
python3 -u scripts/complete_case.py \
  --address 0x45F610cefF1ed367d684A1839b1801Af12Cfb038 \
  --claim calibration/claim-court24-v3.json \
  --manifest runs/bradbury-v3-live.jsonl \
  --challenge-id "$IMPEACH_V3_CHALLENGE_ID" --account impeach-challenger \
  --rpc https://rpc-bradbury.genlayer.com \
  --wait-timeout 100 --poll-interval 5 --max-runtime 3600 \
  --deadline-margin 120 --max-recoveries 3 \
  --subject-first --subject-deadline "$IMPEACH_SUBJECT_EXPIRY_EPOCH" \
  --allow-proven-no-messages --source build/impeach.py
```

The subject deadline is the public API expiry. Both wall time and a fresh
chain clock are checked before initial or recovery dispatch, including after
proof lookup; new subject dispatch stops 120 seconds early. Already submitted
calls cannot be canceled and may execute after that cutoff. Once all subjects
are applied, ADMIT uses the remaining court window even when the API has
expired. The deadline is a dispatch guard, not a promise of network latency.

Use no appeals in this run. Every recovery requires an unchanged empty slot,
an actually finalized failed transaction and the ordinary receipt or complete
native no-message proof. Preserve all original hashes, recovery ordinals and
immutable receipts. Queue servicing and the completer share their lock.
Do not rule a partial run as completion of the 24-item objective.

After all 24 pairs and final native history are verified, separately rule,
collect and recompute the real certificate, then retire and withdraw as
authorized. Disable the paid gateway and verify its public health. Publish
the real case and finalized scripted control with their distinct provenance;
submission is filled with the user after the work is complete.
