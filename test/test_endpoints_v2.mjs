import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import test from 'node:test';
import { canonical, COURT24_V2_CLAIM, COURT24_V2_SCRIPTED_CLAIM, trialRequests } from '../lib/proxy.mjs';
import { createScripted, SCRIPTED_MODEL } from '../lib/scripted.mjs';
import { createLiveV2Proxy } from '../api/live-v2/chat/completions.mjs';

const ROOT = new URL('../', import.meta.url);
const MODEL = 'meta-llama/llama-3.1-8b-instruct';
const SCRIPTED_CLAIM = COURT24_V2_SCRIPTED_CLAIM;
const NOW = Date.parse('2026-10-10T12:00:00Z');
const ENV = { OPENROUTER_API_KEY: 'offline-test-key', OPENROUTER_MODEL: MODEL,
  OPENROUTER_PROVIDER: 'deepinfra/fp8', TRIAL_ENABLED: 'true', TRIAL_V2_ENABLED: 'true',
  TRIAL_CREDIT_ONLY: 'true', TRIAL_BUDGET_USD: '5', TRIAL_EXPIRES_AT: '2026-10-10T13:00:00Z' };
const KEY = { limit: 5, limit_remaining: 3, limit_reset: null, byok_usage: 0,
  include_byok_in_limit: false, is_management_key: false };
const post = (body, headers = {}) => new Request('https://example.test/api/scripted-v2/chat/completions', {
  method: 'POST', headers: { 'Content-Type': 'application/json', ...headers },
  body: typeof body === 'string' ? body : JSON.stringify(body),
});
const readJson = path => JSON.parse(readFileSync(new URL(path, ROOT), 'utf8'));

test('default corpus stays byte-identical and only explicit committed selectors exist', () => {
  const old = trialRequests(MODEL);
  assert.equal(createHash('sha256').update(JSON.stringify(old)).digest('hex'),
    'd57fe54446ae2df137888f23fe1c5438325122728bb234e782a785fc6eac3cfa');
  for (const path of ['.env.local', '/tmp/claim.json', '../calibration/claim-gsm8k.json',
    'calibration/claim-court24-v2.json/../claim-gsm8k.json', null, {}]) {
    assert.throws(() => trialRequests(MODEL, path), /Unsupported corpus configuration/);
  }
  assert.equal(trialRequests(MODEL, COURT24_V2_CLAIM).length, 72);
  assert.equal(createHash('sha256').update(JSON.stringify(trialRequests(MODEL, COURT24_V2_CLAIM))).digest('hex'),
    '4795886ad63c3cab29436873bf5e531ee7c4b4097d91aa0b51564c76e2bbc74d');
  assert.equal(trialRequests(SCRIPTED_MODEL, SCRIPTED_CLAIM).length, 72);
});

test('new live and scripted allowlists match all actual contract request bodies', () => {
  for (const [model, claimPath] of [[MODEL, COURT24_V2_CLAIM], [SCRIPTED_MODEL, SCRIPTED_CLAIM]]) {
    const script = `import json, sys
sys.path.insert(0, 'scripts')
import rehearse
seen=[]
def http(url, body):
    seen.append(json.loads(body))
    return 200, json.dumps({'choices':[{'message':{'content':'ANSWER: 0'}}]}).encode()
rehearse.run_rehearsal(rehearse.load_claim('${claimPath}'), '${model}', 0, http)
print(json.dumps(seen))`;
    const actual = JSON.parse(execFileSync('python3', ['-c', script], { cwd: ROOT, encoding: 'utf8' }));
    assert.equal(actual.length, 72);
    assert.deepEqual(trialRequests(model, claimPath).map(canonical).sort(), actual.map(canonical).sort());
  }
});

test('live and scripted source content hashes cannot collide in the spent registry', () => {
  const script = `import json, sys
sys.path.insert(0, 'scripts')
from run_case import load_claim, tool
result={}
for label,path in [('live','${COURT24_V2_CLAIM}'),('scripted','${SCRIPTED_CLAIM}')]:
    result[label]=[tool.content_hash(item['prompt']) for item in load_claim(path)['_items']]
print(json.dumps(result))`;
  const hashes = JSON.parse(execFileSync('python3', ['-c', script], { cwd: ROOT, encoding: 'utf8' }));
  assert.equal(new Set(hashes.live).size, 24);
  assert.equal(new Set(hashes.scripted).size, 24);
  assert.deepEqual(hashes.live.filter(hash => hashes.scripted.includes(hash)), []);
  const live = new Set(trialRequests(SCRIPTED_MODEL, COURT24_V2_CLAIM).map(canonical));
  const scripted = trialRequests(SCRIPTED_MODEL, SCRIPTED_CLAIM).map(canonical);
  assert.deepEqual(scripted.filter(body => live.has(body)), [], 'all 72 request bodies belong to distinct corpora');
});

test('new live switch is independent and the old corpus cannot reach its provider', async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return url.endsWith('/key') ? Response.json({ data: KEY })
      : Response.json({ choices: [{ message: { content: 'ANSWER: 9' } }], usage: { is_byok: false } });
  };
  const body = trialRequests(MODEL, COURT24_V2_CLAIM)[0];
  const disabled = createLiveV2Proxy({ env: { ...ENV, TRIAL_V2_ENABLED: undefined }, fetchImpl, now: () => NOW });
  assert.equal((await disabled(post(body))).status, 503);
  assert.equal(calls.length, 0);
  const enabled = createLiveV2Proxy({ env: ENV, fetchImpl, now: () => NOW });
  assert.equal((await enabled(post(trialRequests(MODEL)[0]))).status, 403);
  assert.equal((await enabled(post(trialRequests(MODEL, SCRIPTED_CLAIM)[0]))).status, 403);
  assert.equal(calls.length, 0);
  assert.equal((await enabled(post(body))).status, 200);
  assert.equal(calls.length, 2);
  const forwarded = JSON.parse(calls[1].init.body);
  assert.deepEqual(forwarded.provider, { only: ['deepinfra/fp8'], allow_fallbacks: false, require_parameters: true,
    max_price: { prompt: 0.05, completion: 0.10, request: 0 } });
  delete forwarded.provider;
  assert.deepEqual(forwarded, body);
});

test('v2 keeps the same capped credit-only route and response guards', async () => {
  const body = trialRequests(MODEL, COURT24_V2_CLAIM)[0];
  for (const options of [
    { env: { TRIAL_BUDGET_USD: '5.01' } }, { env: { OPENROUTER_PROVIDER: 'other' } },
    { env: { OPENROUTER_MODEL: 'openai/gpt-4.1' } },
    { env: { TRIAL_CREDIT_ONLY: 'false', TRIAL_BUDGET_USD: '6' } },
    { env: { TRIAL_EXPIRES_AT: '2026-10-10T16:00:01Z' } },
    { key: { limit: 6 } }, { key: { byok_usage: 0.01 } }, { key: { limit_remaining: 0.09 } },
    { key: { limit_reset: 'daily' } }, { key: { is_management_key: true } },
    { completion: { choices: [{ message: { content: 'ANSWER: 9' } }] } },
  ]) {
    let calls = 0;
    const handle = createLiveV2Proxy({ env: { ...ENV, ...options.env }, now: () => NOW,
      fetchImpl: async url => {
        calls++;
        return url.endsWith('/key') ? Response.json({ data: { ...KEY, ...options.key } })
          : Response.json(options.completion);
      } });
    assert.equal((await handle(post(body))).status, options.completion ? 502 : 503);
    assert.equal(calls, options.env ? 0 : options.key ? 1 : 2);
  }
});

test('scripted lookup is labeled, repeats sealed answers and returns exact recall tails', async () => {
  const handle = createScripted();
  const health = await (await handle(new Request('https://example.test/'))).json();
  assert.equal(health.kind, 'scripted');
  assert.equal(health.llm, false);
  assert.equal(health.model, SCRIPTED_MODEL);
  assert.equal(health.allowed_requests, 72);
  const claim = readJson(SCRIPTED_CLAIM);
  const items = readJson(claim.items).items;
  const rewrites = readdirSync(new URL(claim.rewrites, ROOT)).filter(name => name.endsWith('.json')).sort()
    .map(name => readJson(claim.rewrites + '/' + name));
  const bodies = trialRequests(SCRIPTED_MODEL, SCRIPTED_CLAIM);
  const pairs = [];
  let stale = 0;
  for (const [index, body] of bodies.entries()) {
    const response = await handle(post(body));
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('x-impeach-mode'), 'scripted-no-llm');
    assert.equal(response.headers.get('cache-control'), 'no-store');
    const completion = await response.json();
    assert.equal(completion.model, SCRIPTED_MODEL);
    assert.equal(completion.impeach.llm, false);
    assert.equal(completion.impeach.kind, 'scripted');
    const content = completion.choices[0].message.content;
    if (index < 24) assert.equal(content, 'ANSWER: ' + items[index].answer);
    else if (index < 48) {
      const rewrite = rewrites[index - 24];
      assert.equal(content, 'ANSWER: ' + items[rewrite.item_index].answer);
      if (Number(rewrite.answer) !== Number(items[rewrite.item_index].answer)) {
        stale++;
        assert.notEqual(content, 'ANSWER: ' + rewrite.answer, 'changed-number rewrite must expose memorisation');
      }
    } else {
      const chars = Array.from(items[index - 48].prompt);
      assert.equal(content, chars.slice(Math.floor(chars.length * claim.extras.recall_prefix_milli / 1000)).join(''));
    }
    pairs.push({ request: body, response: completion });
  }
  assert.ok(stale >= 5, 'the corpus must contain multiple rewrites that change the sealed answer');
  const script = `import json,sys
sys.path.insert(0,'scripts')
import rehearse
pairs=json.load(sys.stdin)
key=lambda body:json.dumps(body,sort_keys=True,ensure_ascii=False)
lookup={key(pair['request']):pair['response'] for pair in pairs}
seen=[]
def http(url,body):
    parsed=json.loads(body)
    seen.append(parsed)
    return 200,json.dumps(lookup[key(parsed)]).encode()
_,_,verdict,cert=rehearse.run_rehearsal(rehearse.load_claim('${SCRIPTED_CLAIM}'),'${SCRIPTED_MODEL}',1000,http)
print(json.dumps({'calls':len(seen),'verdict':verdict,'certificate':cert}))`;
  const result = JSON.parse(execFileSync('python3', ['-c', script], {
    cwd: ROOT, encoding: 'utf8', input: JSON.stringify(pairs),
  }));
  assert.equal(result.calls, 72);
  assert.equal(result.certificate.pinned_milli, 1000);
  assert.equal(result.certificate.recall_milli, 1000);
  assert.equal(result.certificate.stale_answers, stale);
  assert.equal(result.certificate.rewrite_milli, Math.floor((24 - stale) * 1000 / 24));
  assert.equal(result.verdict, 'CONTAMINATED');
  assert.equal(result.certificate.reason, 'RECALL');
});

test('scripted accepts no arbitrary chat, model, params, extra fields or oversized input', async () => {
  const handle = createScripted();
  const body = trialRequests(SCRIPTED_MODEL, SCRIPTED_CLAIM)[0];
  for (const invalid of [null, [], {}, { ...body, model: MODEL }, trialRequests(SCRIPTED_MODEL)[0],
    trialRequests(SCRIPTED_MODEL, COURT24_V2_CLAIM)[0],
    { ...body, messages: [{ role: 'user', content: 'hello' }] }, { ...body, temperature: 1 },
    { ...body, seed: 8 }, { ...body, max_tokens: 513 }, { ...body, provider: {} },
    { ...body, stream: false }, { ...body, tools: [] }]) {
    assert.equal((await handle(post(invalid))).status, 403);
  }
  assert.equal((await handle(post('{'))).status, 400);
  assert.equal((await handle(post(body, { 'Content-Type': 'text/plain' }))).status, 415);
  assert.equal((await handle(post(' '.repeat(25 * 1024)))).status, 413);
  assert.equal((await handle(post(body, { 'Content-Length': '50000' }))).status, 413);
  assert.equal((await handle(new Request('https://example.test/', { method: 'DELETE' }))).status, 405);
  const missing = createScripted({ loadFixtures: () => { throw new Error('private failure'); } });
  assert.deepEqual(await (await missing(post(body))).json(), { error: { code: 'trial_corpus_unavailable' } });
});
