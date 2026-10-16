# Steward corrections — 16 October 2026

The corrected `impeach/1.1` court has a **native FINALIZED / CLEAN real-model
verdict** with **24 admitted pairs and 24 measured recall results**. Δ=0‰ and
R=0‰. The retired certificate is final. The new scripted control is still running;
its result will be published separately after native finalization.

## Requested fixes

**Answer-key admission.** Previously, a nonempty wrong text answer could pass
when the semantic referee returned `same_question: true`, because the final key
comparison was conditional on numeric keys. Both blind results are now compared
with their respective committed keys for every answer type. Numeric pairs use
canonical decimal equality; other pairs use deterministic `norm_answer` equality.
Unlisted synonyms are conservatively rejected. Both independent referee
framings remain mandatory, and the blind solver cannot see the keys.

Tests cover wrong original and rewritten text answers, mixed numeric/text keys,
false-positive semantic Booleans, malformed outputs and both framings. The old
text bypass reproduced seven failing assertions before the fix. Public probe
paths also run through the pinned real SDK.

**CLEAN evidence.** A clean verdict now requires both
`admissible >= min_items` and `recall_probes >= min_items`, with neither detector
nor score shortfall tripping. Only recall `MATCH` and `MISS` count as measured
evidence. Missing, `NA` and `DEAD` results cannot support CLEAN; insufficient
recall yields `INCONCLUSIVE / TOO_FEW_RECALL`. Positive contamination evidence and
proven score shortfalls retain independent verdict paths.

Contract, Python CLI and browser recomputation share this rule. Tests include
zero recall, one below the minimum, exactly the minimum and ineligible short
tails. Solvency is checked after every public write.

## Corrected native evidence

Court: [0xCB67936d0b00b82Ea73611b3C8353a21EBdc7261](https://explorer-bradbury.genlayer.com/address/0xCB67936d0b00b82Ea73611b3C8353a21EBdc7261),
Bradbury chain 4221. The [source/protocol check](runs/review-protocol-and-source-preflight.json)
verifies deployed artifact SHA-256
`3d46770b50e2f59cadc621a40ff36da1f747c885fa9f9c45327a1199b2afa3b9`,
byte-for-byte source equality and the active protocol implementations.

| Real-model case 1/1 | Stored result |
| --- | --- |
| Subject | Llama 3.1 8B Instruct, DeepInfra FP8 |
| Original / rewritten answers | 24/24 correct in each group |
| Both referee framings | 24/24 pairs ADMISSIBLE |
| Measured recall | 24 MISS, no missing or dead probes |
| Verdict | CLEAN, Δ=0‰, R=0‰ |
| Lifecycle | RETIRED, final certificate, bond 0.1 test GEN credited internally |
| Native case transactions | 113 FINALIZED, including unsuccessful attempts |

- [Collected native record](runs/review-live-final-case.json) and
  [full hash journal](runs/review-live.jsonl).
- [Rule transaction](https://explorer-bradbury.genlayer.com/transactions/0x9e0a82eaee891864a753cdd9dab304368d649ab5d299de91c728fd437a106bec)
  and [actual native finality proof](runs/review-live-rule-final-native.json).
- [Retirement transaction](https://explorer-bradbury.genlayer.com/transactions/0x26eef7e5e96b14dbb415b6b990492b85532de94668bfda2592d61beb601211c5)
  and [native finality proof](runs/review-live-retire-final-native.json).
- [Frozen claim](calibration/claim-review-live.json) and
  [pre-rule stored-state checks](runs/review-live-pre-rule-state.json).
- Local recomputation: `python3 cli/impeach.py recompute web/case.json` agrees
  with the native certificate. The website displays this corrected record.

Native finality above checks actual TransactionManager status 7, successful
execution and the deployed source hash, separately from application certificate
fields. The final certificate does not itself prove wallet payout. Internal
credit withdrawal remains a separate settlement step.

The separate scripted control has 24 correct original answers and 24 exact recall
matches. Remaining rewrite/referee operations are still running. It is a lookup
table, not a real LLM; its expected contamination is a positive control.

These are regression runs on previously disclosed public synthetic corpora,
not secret benchmarks or evidence of absence from training. A new deployment has
its own spent registry. Previous contracts, burns and partial certificates remain
historical records, including [the previous site snapshot](runs/review-previous-site-case.json).

## Verification

- 203 local contract assertions, 187 Python regression tests, 169 pinned real-SDK
  assertions and 52 browser parity checks pass.
- `make check` also verifies the deployment artifact's AST, endpoint policy,
  gas guards, receipts and native finality safeguards. Node 22+ is required.
- [Core correction CI](https://github.com/Zhekinmaksim/impeach/actions/runs/38856453603)
  passed both jobs on `7f5b7fc`.
- [Runner CI](https://github.com/Zhekinmaksim/impeach/actions/runs/38888397455) and
  [ready-admission CI](https://github.com/Zhekinmaksim/impeach/actions/runs/38890898087)
  passed both jobs. These caller changes do not change the deployed court.
- [Fresh 72-response Llama rehearsal](runs/review-live-rehearsal-audit.json) and
  [112-response exact referee replay](runs/review-referee-replay.json) are
  calibration evidence. The replay admits all 24 intended pairs and rejects all
  four negative controls in both framings. Neither is a native verdict.

## Operations and limits

Failed consensus rounds remain in the journals and are never counted as saved
answers. Recovery requires finalized negative execution or a native proof that
no messages were applied, an unchanged frozen claim and an untouched slot. Each
new hash preserves its predecessor and original receipt. Two scripted REWRITE
calls sent by the wrong caller reverted; explicit caller correction binds the
new signer to the frozen challenger and retains both failed hashes.

Seven leader rotations are requested without reducing the five-validator
committee. Signed ABI and actual native committee fields are checked because
the SDK projection mislabels the committee count on rotated calls. Read-only
RPC retries are bounded; writes are not blindly retried. An explicit operator limit allows at
most six recoveries per slot, one by default. Raising an exhausted three-retry
limit preserves the same case identity and every original hash; tests cover
six failures, the absolute ceiling, safe resume and ineligible outcomes. The ready-admission
mode advances only C2 for saved pairs and reports partial completion explicitly.

The temporary API window was renewed once with explicit user authorization;
[the renewal record](runs/review-authorized-window-renewal.json) preserves both
scheduling identities. On-chain claim inputs and thresholds never changed.
The [canonical paid route was disabled](runs/review-gateway-shutdown-health.json)
after the last real subject result finalized. A
[valid POST now returns HTTP 503 / trial_disabled](runs/review-paid-route-disabled-post.json).
Prior immutable deployment URLs retain their fixed expiry, 14:27:02 UTC, without
extension. The free scripted route remains available. The
[budget snapshot](runs/review-budget-after-shutdown.json) records $2.02767348 spent
under the unchanged $5 lifetime cap, with no reset or BYOK usage.
