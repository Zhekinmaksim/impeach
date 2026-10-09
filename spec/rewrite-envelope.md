# Rewrite envelope, `impeach/1`

What a challenger files with `probe(challenge_id, item_index, "REWRITE", payload)`.

```json
{
  "version": "impeach/1",
  "class": "numeral_substitution",
  "prompt": "the rewritten item, in full",
  "answer": "the correct answer to the rewritten item"
}
```

Files in `examples/rewrites/` carry three more fields that stay off chain:
`item_index`, `derivation` (integer arithmetic that must evaluate to `answer`)
and `author_note`. `impeach envelope` checks them; `canonical_envelope` strips
them before sending.

## The deterministic gate

Checked by the contract before any referee runs. Failing it reverts the
transaction and costs nothing.

| rule | applies to |
| --- | --- |
| class is one the challenge declared | all |
| prompt is not identical to the sealed item | all |
| more than whitespace changed | all except `format_shift` |
| answer equals the sealed answer after normalisation | `paraphrase`, `format_shift` |
| at least one numeral differs | `numeral_substitution` |
| answer differs from the sealed answer | `numeral_substitution` |

## The referee

Two rounds use different framings. Each first solves both questions without
seeing either supplied answer, then separately judges the declared class.
The consensus result contains `original_result`, `rewrite_result`, and
`same_question`; validators must agree on all three. Both results must be
nonempty strings. For numeric answer keys the contract also compares the
normalized independently computed results with the supplied answers, so a
contradictory `same_question: true` cannot admit a wrong numeric key.

Both rounds must return `same_question: true` and pass these result checks.
Framing one runs inside `REWRITE`, before the model is asked. Framing two runs in
`ADMIT`. The referee is told the declared class and what must survive under it.
An unreadable or incomplete reply is a refusal. Each framing uses two LLM calls:
one blind calculation and one semantic judgment.

## Hashes

```text
item commitment  sha256("impeach/1/item\n"    + len:salt   + "\n" + len:answer + "\n" + len:prompt)
content hash     sha256("impeach/1/content\n" + flatten(prompt))
rewrite hash     sha256("impeach/1/rewrite\n" + len:class  + "\n" + len:answer + "\n" + len:prompt)
```

`len:x` is the UTF-8 byte length, a colon, then the text. `flatten` collapses
whitespace, lowercases ASCII letters and straightens typographic quotes; nothing
else, so that Python, the contract and a browser agree byte for byte.
