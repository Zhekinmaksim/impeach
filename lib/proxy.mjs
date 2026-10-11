import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';

const ROOT = new URL('../', import.meta.url);
const CHAT_URL = 'https://openrouter.ai/api/v1/chat/completions';
const KEY_URL = 'https://openrouter.ai/api/v1/key';
const RECALL_INSTRUCTION = 'Continue the text below exactly from where it stops. '
  + 'Output only the continuation, with no preamble.\n\n';
const RECALL_MAX_TOKENS = 512;
const MAX_REQUEST_BYTES = 24 * 1024;
const MAX_RESPONSE_BYTES = 256 * 1024;
const MAX_TOKENS = 4096;
const MAX_WINDOW_MS = 96 * 60 * 60 * 1000;
const CREDIT_ONLY_MAX_WINDOW_MS = 4 * 60 * 60 * 1000;
const CREDIT_ONLY_MODEL = 'meta-llama/llama-3.1-8b-instruct';
const CREDIT_ONLY_PROVIDER = 'deepinfra/fp8';
const CREDIT_ONLY_RESERVE_USD = 0.10;
const PARAMS = ['temperature', 'top_p', 'max_tokens', 'seed'];
const FIELDS = new Set(['model', 'messages', ...PARAMS]);
export const COURT24_V2_CLAIM = 'calibration/claim-court24-v2.json';
export const COURT24_V2_SCRIPTED_CLAIM = 'calibration/claim-court24-v2-scripted.json';
export const COURT24_V3_CLAIM = 'calibration/claim-court24-v3.json';
const CORPORA = new Map([
  ['calibration/claim-gsm8k.json', { items: 'calibration/gsm8k-24.items.json', rewrites: 'examples/rewrites' }],
  [COURT24_V2_CLAIM, { items: 'calibration/court24-v2.items.json', rewrites: 'examples/court24-v2/rewrites' }],
  [COURT24_V2_SCRIPTED_CLAIM, { items: 'calibration/court24-v2-scripted.items.json', rewrites: 'examples/court24-v2-scripted/rewrites' }],
  [COURT24_V3_CLAIM, { items: 'calibration/court24-v3.items.json', rewrites: 'examples/court24-v3/rewrites' }],
]);

// Object ordering is immaterial; every value, array position and field is frozen.
export function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') {
    return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
  }
  return JSON.stringify(value);
}

function readJson(path) {
  return JSON.parse(readFileSync(new URL(path, ROOT), 'utf8'));
}

export function trialFixtures(model, claimPath = 'calibration/claim-gsm8k.json') {
  // Callers choose a committed corpus explicitly; request bodies and environment
  // variables can never select arbitrary filesystem paths or add corpora.
  const paths = CORPORA.get(claimPath);
  if (!paths) throw new Error('Unsupported corpus configuration');
  const claim = readJson(claimPath);
  if (claim.items !== paths.items || claim.rewrites !== paths.rewrites) {
    throw new Error('Unsupported corpus configuration');
  }
  const items = readJson(claim.items).items;
  const rewrites = readdirSync(new URL(paths.rewrites + '/', ROOT)).filter(name => name.endsWith('.json'))
    .sort().map(name => readJson(paths.rewrites + '/' + name));
  if (items.length !== 24 || rewrites.length !== 24 || new Set(rewrites.map(item => item.item_index)).size !== 24) {
    throw new Error('Incomplete demonstration corpus');
  }
  const params = Object.fromEntries(PARAMS.filter(key => key in claim.decode_params).map(key => [key, claim.decode_params[key]]));
  if (!Number.isInteger(params.max_tokens) || params.max_tokens < 1 || params.max_tokens > MAX_TOKENS) {
    throw new Error('Unsafe token limit');
  }
  const answer = prompt => ({
    model,
    messages: [
      ...(claim.prompt_template.system ? [{ role: 'system', content: claim.prompt_template.system }] : []),
      { role: 'user', content: claim.prompt_template.user.replaceAll('{{item}}', prompt) },
    ],
    ...params,
  });
  const fixtures = items.map((item, itemIndex) => ({
    request: answer(item.prompt), mode: 'PINNED', itemIndex, content: 'ANSWER: ' + item.answer,
  }));
  for (const rewrite of rewrites) {
    if (!Number.isInteger(rewrite.item_index) || !items[rewrite.item_index]) throw new Error('Invalid rewrite index');
    fixtures.push({ request: answer(rewrite.prompt), mode: 'REWRITE', itemIndex: rewrite.item_index,
      // The scripted memoriser deliberately repeats the sealed answer even when
      // a numeral rewrite changes it. The live proxy never uses fixture content.
      content: 'ANSWER: ' + items[rewrite.item_index].answer });
  }
  for (const [itemIndex, item] of items.entries()) {
    // Python splits Unicode code points, not JavaScript UTF-16 code units.
    const chars = Array.from(item.prompt);
    const cut = Math.floor(chars.length * claim.extras.recall_prefix_milli / 1000);
    fixtures.push({ request: { model, messages: [{ role: 'user', content: RECALL_INSTRUCTION + chars.slice(0, cut).join('') }], ...params, max_tokens: RECALL_MAX_TOKENS },
      mode: 'RECALL', itemIndex, content: chars.slice(cut).join('') });
  }
  if (new Set(fixtures.map(fixture => canonical(fixture.request))).size !== 72) {
    throw new Error('Ambiguous demonstration corpus');
  }
  return fixtures;
}

export function trialRequests(model, claimPath = 'calibration/claim-gsm8k.json') {
  return trialFixtures(model, claimPath).map(fixture => fixture.request);
}

export class Rejected extends Error {
  constructor(status, code) { super(code); this.status = status; this.code = code; }
}

export function response(body, status = 200, extra = {}) {
  return new Response(typeof body === 'string' ? body : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store',
      'CDN-Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', ...extra },
  });
}

async function readBounded(source, limit, tooLargeStatus = 413) {
  const length = source.headers.get('content-length');
  if (length !== null && (!/^\d+$/.test(length) || Number(length) > limit)) {
    throw new Rejected(tooLargeStatus, 'body_too_large');
  }
  if (!source.body) return '';
  const reader = source.body.getReader();
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) throw new Rejected(tooLargeStatus, 'body_too_large');
      chunks.push(value);
    }
  } catch (error) {
    await reader.cancel().catch(() => {});
    throw error;
  } finally {
    reader.releaseLock();
  }
  return Buffer.concat(chunks, size).toString('utf8');
}

function configuration(env, now) {
  if (env.TRIAL_ENABLED !== 'true') throw new Rejected(503, 'trial_disabled');
  const key = env.OPENROUTER_API_KEY;
  const model = env.OPENROUTER_MODEL;
  const provider = env.OPENROUTER_PROVIDER;
  const budget = Number(env.TRIAL_BUDGET_USD);
  const creditOnly = env.TRIAL_CREDIT_ONLY === 'true';
  if (!key || typeof model !== 'string' || !/^[\w.-]+\/[\w.:-]+$/.test(model)
    || typeof provider !== 'string' || !/^[\w./-]+$/.test(provider)
    || !Number.isFinite(budget) || budget <= 0) {
    throw new Rejected(503, 'trial_not_configured');
  }
  if (creditOnly && (model !== CREDIT_ONLY_MODEL || provider !== CREDIT_ONLY_PROVIDER || budget > 5)) {
    throw new Rejected(503, 'credit_only_configuration_required');
  }
  const expires = Date.parse(env.TRIAL_EXPIRES_AT || '');
  if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/.test(env.TRIAL_EXPIRES_AT || '')
    || !Number.isFinite(expires) || expires > now + (creditOnly ? CREDIT_ONLY_MAX_WINDOW_MS : MAX_WINDOW_MS)) {
    throw new Rejected(503, 'trial_window_invalid');
  }
  if (expires <= now) throw new Rejected(503, 'trial_expired');
  return { key, model, provider, budget, expires, creditOnly };
}

function validShape(body) {
  return body && typeof body === 'object' && !Array.isArray(body)
    && Object.keys(body).every(key => FIELDS.has(key))
    && typeof body.model === 'string'
    && Array.isArray(body.messages) && body.messages.length >= 1 && body.messages.length <= 2
    && body.messages.every(message => message && typeof message === 'object' && !Array.isArray(message)
      && Object.keys(message).length === 2 && typeof message.role === 'string' && typeof message.content === 'string'
      && Object.keys(message).every(key => key === 'role' || key === 'content'))
    && PARAMS.every(key => !(key in body) || (typeof body[key] === 'number' && Number.isFinite(body[key])));
}

export async function parseTrialBody(request, allowed) {
  if (request.headers.get('content-type')?.split(';')[0].trim().toLowerCase() !== 'application/json') {
    throw new Rejected(415, 'json_required');
  }
  let body;
  const text = await readBounded(request, MAX_REQUEST_BYTES);
  try { body = JSON.parse(text); } catch { throw new Rejected(400, 'invalid_json'); }
  if (!validShape(body) || !allowed.has(canonical(body))) throw new Rejected(403, 'request_not_in_trial');
  return body;
}

// Dependencies are injectable for offline tests; no alternate upstream URL exists.
export function createProxy({ env = process.env, fetchImpl = globalThis.fetch, now = Date.now,
  timeoutMs = 45_000, loadRequests = trialRequests } = {}) {
  return async function handle(request) {
    if (request.method !== 'GET' && request.method !== 'POST') {
      return response({ error: { code: 'method_not_allowed' } }, 405, { Allow: 'GET, POST' });
    }
    let config;
    try {
      config = configuration(env, now());
    } catch (error) {
      if (request.method === 'GET') return response({ service: 'impeach-openrouter', enabled: false, status: error.code });
      return response({ error: { code: error.code || 'trial_not_configured' } }, 503);
    }
    let allowed;
    try {
      allowed = new Set(loadRequests(config.model).map(canonical));
    } catch {
      return response({ error: { code: 'trial_corpus_unavailable' } }, 503);
    }
    if (request.method === 'GET') {
      return response({ service: 'impeach-openrouter', enabled: true, status: 'configured',
        model: config.model, provider: config.provider, expires_at: new Date(config.expires).toISOString(),
        credit_only: config.creditOnly,
        allowed_requests: allowed.size,
        policy_sha256: createHash('sha256').update([...allowed].sort().join('\n')).digest('hex') });
    }
    try {
      const body = await parseTrialBody(request, allowed);

      const signal = AbortSignal.any([AbortSignal.timeout(timeoutMs), request.signal]);
      const headers = { Authorization: 'Bearer ' + config.key, 'Content-Type': 'application/json' };
      const options = { headers, signal, redirect: 'error', cache: 'no-store' };
      // The provider enforces the cap across serverless instances and validators.
      // Check afresh; neither successful responses nor budget metadata are cached.
      const keyResponse = await fetchImpl(KEY_URL, { ...options, method: 'GET' });
      if (!keyResponse.ok) throw new Rejected(503, 'budget_check_unavailable');
      let keyData;
      try { keyData = JSON.parse(await readBounded(keyResponse, MAX_REQUEST_BYTES, 502)).data; }
      catch { throw new Rejected(503, 'budget_check_unavailable'); }
      if (!keyData || !Number.isFinite(keyData.limit) || keyData.limit <= 0 || keyData.limit > config.budget
        || keyData.limit_reset !== null
        || (config.creditOnly
          ? !Number.isFinite(keyData.byok_usage) || keyData.byok_usage !== 0
          : keyData.include_byok_in_limit !== true)
        || keyData.is_management_key !== false || keyData.is_provisioning_key === true) {
        throw new Rejected(503, 'capped_inference_key_required');
      }
      if (!Number.isFinite(keyData.limit_remaining) || keyData.limit_remaining <= 0
        || (config.creditOnly && keyData.limit_remaining < CREDIT_ONLY_RESERVE_USD)) {
        throw new Rejected(503, 'trial_budget_exhausted');
      }
      // Recheck expiry after the budget call. Forward the frozen model input unchanged.
      if (now() >= config.expires) throw new Rejected(503, 'trial_expired');
      const upstream = await fetchImpl(CHAT_URL, { ...options, method: 'POST', body: JSON.stringify({ ...body,
        provider: { only: [config.provider], allow_fallbacks: false, require_parameters: true,
          max_price: { prompt: 0.05, completion: 0.10, request: 0 } } }) });
      if (!upstream.ok) throw new Rejected(upstream.status === 429 ? 429 : 502, 'upstream_unavailable');
      const raw = await readBounded(upstream, MAX_RESPONSE_BYTES, 502);
      let completion;
      try { completion = JSON.parse(raw); } catch { throw new Rejected(502, 'invalid_upstream_response'); }
      if (completion.error || !Array.isArray(completion.choices)
        || typeof completion.choices[0]?.message?.content !== 'string' || completion.choices[0]?.error) {
        throw new Rejected(502, 'invalid_upstream_response');
      }
      // This checks the completed route; it cannot undo a charge already made.
      if (config.creditOnly && completion.usage?.is_byok !== false) {
        throw new Rejected(502, 'credit_only_response_required');
      }
      // Preserve the actual response byte-for-byte, including truncation/refusal.
      return response(raw);
    } catch (error) {
      if (error instanceof Rejected) return response({ error: { code: error.code } }, error.status);
      if (error.name === 'TimeoutError' || error.name === 'AbortError') {
        return response({ error: { code: 'upstream_timeout' } }, 504);
      }
      // Never return exception text, request headers, keys or provider error bodies.
      return response({ error: { code: 'upstream_unavailable' } }, 502);
    }
  };
}
