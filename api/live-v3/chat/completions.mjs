import { COURT24_V3_CLAIM, createProxy, trialRequests } from '../../../lib/proxy.mjs';

export function createLiveV3Proxy({ env = process.env, ...options } = {}) {
  return createProxy({ ...options,
    env: { ...env, TRIAL_ENABLED: env.TRIAL_V3_ENABLED, TRIAL_CREDIT_ONLY: 'true' },
    loadRequests: model => trialRequests(model, COURT24_V3_CLAIM),
  });
}

export default { fetch: createLiveV3Proxy() };
