import { COURT24_V2_CLAIM, createProxy, trialRequests } from '../../../lib/proxy.mjs';

export function createLiveV2Proxy({ env = process.env, ...options } = {}) {
  return createProxy({ ...options,
    // The original endpoint's switch cannot silently enable this new trial.
    env: { ...env, TRIAL_ENABLED: env.TRIAL_V2_ENABLED, TRIAL_CREDIT_ONLY: 'true' },
    loadRequests: model => trialRequests(model, COURT24_V2_CLAIM),
  });
}

export default { fetch: createLiveV2Proxy() };
