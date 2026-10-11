// Observe response only; never record or modify signed request bytes.
import {openSync, writeSync, fsyncSync, closeSync} from 'node:fs';
const nativeFetch = globalThis.fetch;
globalThis.fetch = async (...args) => {
  let method;
  try { method = JSON.parse(args[1]?.body || '{}').method; } catch {}
  const response = await nativeFetch(...args);
  if (method === 'eth_sendRawTransaction') {
    const body = await response.clone().json();
    if (/^0x[0-9a-fA-F]{64}$/.test(body.result || '')) {
      const fd = openSync(process.env.IMPEACH_EVM_RECEIPT_FILE, 'wx');
      try {
        writeSync(fd, JSON.stringify({at: new Date().toISOString(), evm_hash: body.result}) + '\n');
        fsyncSync(fd);
      } finally { closeSync(fd); }
      console.error('Appeal EVM transaction:', body.result);
    }
  }
  return response;
};
