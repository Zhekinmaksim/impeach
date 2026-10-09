# Decisions

The spec left three questions open on purpose. Building it turned up eight more
places where the spec as written either had a hole or did not say enough to
implement. Each is listed with what the contract does, why, and which test holds
it. All of them are reversible; none of them is hidden.

## The three open questions

### 1. Who pays for the model calls?

**No sampling inside a challenge. The subset is the sample.**

The challenger names the items blind, at least `min_items` of them, and every
named item is probed in full. A second layer of sampling inside that would
weaken a number that is already small.

Costs fall where they arise. The challenger sends the probe transactions and
pays their gas. The publisher serves the endpoint and pays the inference. An
honest challenger who finds nothing gets the whole stake back, as the spec asks.

"`INCONCLUSIVE` returns both, minus probe costs" is implemented as: when the
reason is `ENDPOINT_SILENT`, the publisher pays the challenger an amount equal
to the challenger's stake out of the bond. The silent party pays the other
side's costs.

*Test:* `silence` — "silence is not free".

### 2. Should `CLEAN` be purchasable?

**No, in two ways.**

By absence: a claim nobody challenged reads `UNCONTESTED`, before and after the
publisher retires it. It is never upgraded.

By a friendly challenger: `CLEAN` does not close the case. The bond stays posted
and the claim stays open (`STANDING`). Anyone can challenge again. Because the
items are now public, a later challenger must take the whole set — choosing
which questions to ask after reading them is how a gap gets manufactured. The
certificate carries `challenges_survived` and `bond_standing`, so a reader can
tell a score that has stood through three challenges from one whose publisher
took the bond and left after the first.

*Test:* `standing` — "a CLEAN certificate does not protect the next trial".

### 3. Does a burned set retire the score?

**Yes.** The certificate carries `score_status`: `SEALED` until reveal, `SPENT`
after, with `score_expired_at` set to the burn time. Once the items are public
the score can never again be measured on text the subject has not seen, so from
that moment the number is worth exactly what the certificate says and nothing
more.

## Departures from the spec

### 4. A fourth verdict: `UNSUPPORTED`

The build order asks the suite to separate three subjects: one that memorised,
one that can do the task, one that does neither. Under the spec's verdict table
the third one has no gap and no recall, so it is `CLEAN` and takes its bond
home — for a score it cannot reproduce.

The publisher *swears to a number*. If measured accuracy on the sealed items
falls short of the sworn score by `delta_threshold` or more, the verdict is
`UNSUPPORTED` and the bond goes to the challenger. One threshold now guards two
links of the same chain: sworn → sealed, sealed → rewritten.

The same verdict, reason `SET_ALREADY_SPENT`, is given at reveal when any item
was already in the registry before the claim was opened. Re-salting hides a
spent item from `open_claim`; it does not hide it from the reveal.

A bad model that swears to a bad score is `CLEAN`. The court tries the oath, not
the model.

*Tests:* `three_populations`, `registry`.

### 5. Default judgment

A publisher who expects to lose simply never reveals. Without a rule for that,
the sealed set is an exit. After `reveal_window_s` anyone may call
`claim_default`; the bond and the stake go to the challenger. Nothing is burned,
because nothing was shown.

This is the one place the contract depends on transaction time. `clock()`
exposes it for a smoke test after deploy.

### 6. Silence on a rewrite is an answer

An endpoint that holds a lookup table can answer the items it knows and return
an error on everything else, turning every losing probe into a dead one. If the
sealed item was answered and the admitted rewrite was not, the rewrite counts as
wrong. A fully dead endpoint is different and stays `INCONCLUSIVE`.

*Test:* `silence` — "going quiet on the rewrites is read as an answer".

### 7. The gap is counted over every probed item

The spec computes Δ over admissible pairs. A challenger can query the public
endpoint first, file rewrites only for items the model got right, and drop the
rest. That removes every pair that would have pulled the gap down. In the test
this turns an honest model with a 30% error rate into a conviction.

The contract counts over every item with a live sealed answer, and reads an item
with no admitted rewrite as if the rewrite had been answered correctly. The
`min_items` requirement still applies to admitted pairs.

*Test:* `omission` — "counted over those pairs alone, the gap would convict".

### 8. Forfeited stake goes to the publisher, not a pool

"Griefing funds the next case" worked in Suborn because a sponsor owned the pool
and wanted it paid out. Here there is no sponsor. Any shared pool that pays
winners can be drained by a publisher who opens a doomed claim and challenges it
from a second address. Money that only ever moves between the two parties cannot
be farmed, and the publisher is the one whose set was burned to hear a question
that should not have been asked.

### 9. The challenger writes the rewrites

The spec says rewrites are "generated at judgment time" and also that failed
admissibility costs the challenger. Both hold if the challenger authors them
after the reveal. So `probe` takes a fourth argument (the rewrite envelope) and
there is a fourth mode, `ADMIT`, for the second referee framing — the same split
as Suborn's `submit` and `confirm`, and the fourth box in the spec's own diagram.

One rewrite per item. The stake is divided per item: an admitted rewrite gets
its slice back win or lose, an inadmissible one forfeits it, an unfiled one
forfeits it at ruling.

### 10. `ruled_at` is a time, not a block

The pinned SDK does not expose a block number to contracts. The certificate
carries the transaction time in seconds.

### 11. HTTPS subjects only

The spec's v1 covers public endpoints and on-chain agents. `impeach/1` covers
public endpoints. Calling another contract as the subject needs an agreed
interface that does not exist yet.

## Found on the way: `withdraw` in Suborn and Jastrow

Impeach's `withdraw` was first copied from Suborn:

```python
_Recipient(Address(gl.message.sender_address)).emit_transfer(value=u256(amount))
```

On the pinned SDK `gl.message.sender_address` is already an `Address`, and
`Address(Address)` raises `TypeError`. The real-SDK run caught it; the stub
cannot, because its `Address` accepts itself.

If Suborn's `withdraw` has never been called on Bradbury, it probably reverts.
Jastrow wraps the same line in `try/except`, which would mean the balance is
zeroed and no transfer is emitted. This was observed in direct mode, not on
chain — check both before anyone relies on them. The fix is to pass the address
through unwrapped.
