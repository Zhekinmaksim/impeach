# What to do with a local model

A model running on your own machine covers the two things this repository could
not do for itself: judging the rewrites with a real language model, and being
the subject that stands trial. Commands assume an OpenAI-shaped server on
`localhost:11434` (Ollama's default); any server with `/v1/chat/completions`
works the same way.

```bash
export LOCAL=http://localhost:11434/v1
export MODEL=<a model you have pulled>        # `ollama list`
```

## 1. Check the model answers in the right shape

```bash
curl -s $LOCAL/chat/completions -H 'content-type: application/json' -d '{
  "model": "'$MODEL'", "temperature": 0, "seed": 7, "max_tokens": 512,
  "messages": [{"role":"user","content":"Solve the problem. Finish with a line of the form ANSWER: <number>.\n\nWhat is 17 + 25?"}]
}'
```

You want `choices[0].message.content` ending in `ANSWER: 42`. A model that
thinks out loud for more than 512 tokens will be cut off before the answer;
raise `max_tokens` in `calibration/claim-gsm8k.json` if so.

## 2. Rehearse the whole trial locally

```bash
python3 scripts/rehearse.py --endpoint $LOCAL/chat/completions --model $MODEL
```

The rehearsal reads `calibration/claim-gsm8k.json`, including its prompt,
`max_tokens`, thresholds, bond and windows. Use `--claim path/to/claim.json` for
another claim. It exits nonzero if requests fail or scored replies omit the
`ANSWER:` line; inspect those failures before choosing the sworn score.

72 requests, a few minutes. The real contract runs on the local stub and sends
your model exactly what it would send from Bradbury. You get the sealed
accuracy, the rewritten accuracy, Δ, R and a forecast verdict.

Write down **answered as sealed**. That is the most you can honestly swear to.

To see it on the page:

```bash
python3 scripts/rehearse.py --endpoint $LOCAL/chat/completions --model $MODEL --score <that number> --out web/case.json
make serve
```

`make snapshot` puts the three scripted subjects back.

## 3. Run the referee over the corpus

```bash
export OPENAI_BASE_URL=$LOCAL  REFEREE_MODEL=$MODEL
python3 scripts/referee_dryrun.py
```

56 prompts: both framings over the 24 rewrites and the 4 controls. Expected: 24
admitted, 4 refused. Each `MISS` line is one of two things:

- an honest rewrite refused. Open the file, see whether the referee has a point.
  The three `unit_change` rewrites are the likeliest; refile them as `paraphrase`
  if the class is being read strictly.
- a control admitted. That framing is too weak for this model. Do not go live
  until at least one framing stops every control.

A small local model is a poor referee. If the results look random, use the
largest model you can run for this step only; the referee and the subject do not
have to be the same model. Either way this is one judge, not a validator set.

## 4. Put the model on trial for real

The contract only accepts a public `https://` endpoint with no key. Tunnel the
local server:

```bash
cloudflared tunnel --url http://localhost:11434
# prints https://<random>.trycloudflare.com
```

If the tunnel returns 403, the server is rejecting the forwarded host name; add
`--http-host-header localhost:11434`.

Then in `calibration/claim-gsm8k.json`:

```json
"subject": "local/<model>@2026-10",
"endpoint": "https://<random>.trycloudflare.com/v1/chat/completions",
"score_milli": <the number from step 2>,
"decode_params": {"model": "<model>", "temperature": 0, "top_p": 1, "max_tokens": 512, "seed": 7}
```

`model` inside `decode_params` is what the endpoint is asked for; without it the
contract sends the `subject` string, which your server will not recognise.

From here follow `DEPLOY.md` from step 3.

Three things that are different with a model on your desk:

- **The address is frozen at `open_claim`.** A quick tunnel gets a new address
  every time it restarts. Keep one tunnel process alive from `open` to `rule`,
  or use a named tunnel. If the address dies mid-trial the verdict is
  `INCONCLUSIVE`, reason `ENDPOINT_SILENT`, and the bond pays the challenger's
  costs.
- **Every validator calls it.** One probe is one request per validator, and they
  arrive together. Let the server handle a few requests in parallel
  (`OLLAMA_NUM_PARALLEL` for Ollama) and keep the machine awake.
- **Anyone with the address can use your model** while the tunnel is up. Close
  it after `rule`.

## 5. Optional: a subject with a known verdict first

```bash
python3 scripts/stub_endpoint.py --port 8787
cloudflared tunnel --url http://localhost:8787
# endpoint: https://<random>.trycloudflare.com/memoriser/v1/chat/completions
```

The scripted memoriser, convicted as `CONTAMINATED` on both detectors. It proves
that every path settles on Bradbury before a real model is involved. It is a
lookup table, and the submission has to say so.
