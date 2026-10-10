import { createHash } from 'node:crypto';
import { canonical, COURT24_V2_SCRIPTED_CLAIM, parseTrialBody, Rejected, response, trialFixtures } from './proxy.mjs';

export const SCRIPTED_MODEL = 'scripted/memoriser-court24-v2';

// An explicit demonstration lookup, not a model or a proxy. It uses no secrets,
// network calls or environment variables and only recognizes this sealed corpus.
export function createScripted({ loadFixtures = () => trialFixtures(SCRIPTED_MODEL, COURT24_V2_SCRIPTED_CLAIM) } = {}) {
  return async function handle(request) {
    const headers = { 'X-Impeach-Mode': 'scripted-no-llm' };
    if (request.method !== 'GET' && request.method !== 'POST') {
      return response({ error: { code: 'method_not_allowed' } }, 405, { ...headers, Allow: 'GET, POST' });
    }
    let fixtures;
    try {
      fixtures = new Map(loadFixtures().map(fixture => [canonical(fixture.request), fixture]));
      if (fixtures.size !== 72) throw new Error('Incomplete scripted corpus');
    } catch {
      return response({ error: { code: 'trial_corpus_unavailable' } }, 503, headers);
    }
    if (request.method === 'GET') {
      return response({ service: 'impeach-scripted-memoriser', enabled: true, model: SCRIPTED_MODEL,
        kind: 'scripted', llm: false, allowed_requests: fixtures.size,
        description: 'Sealed-answer and verbatim-tail lookup. No LLM or external API is called.',
        policy_sha256: createHash('sha256').update([...fixtures.keys()].sort().join('\n')).digest('hex') }, 200, headers);
    }
    try {
      const body = await parseTrialBody(request, fixtures);
      const fixture = fixtures.get(canonical(body));
      return response({
        id: 'scripted-' + createHash('sha256').update(canonical(body)).digest('hex').slice(0, 24),
        object: 'chat.completion', model: SCRIPTED_MODEL,
        choices: [{ index: 0, message: { role: 'assistant', content: fixture.content }, finish_reason: 'stop' }],
        impeach: { kind: 'scripted', llm: false, mode: fixture.mode, item_index: fixture.itemIndex },
      }, 200, headers);
    } catch (error) {
      if (error instanceof Rejected) return response({ error: { code: error.code } }, error.status, headers);
      return response({ error: { code: 'scripted_request_failed' } }, 400, headers);
    }
  };
}
