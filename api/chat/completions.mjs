import { createProxy } from '../../lib/proxy.mjs';

// Native Vercel Node.js Web handler. No framework, build step or client secret.
export default { fetch: createProxy() };
