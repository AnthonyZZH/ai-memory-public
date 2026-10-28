// Substitute only the DSH host boundary. Vendor bridge/transport code runs real.
import { registerHooks } from 'node:module';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('@deepseek-ai/')) return {url:new URL('./host-stub.mjs',import.meta.url).href,shortCircuit:true};
    if (specifier === 'ws') return {url:pathToFileURL(path.join(process.env.SOCIAL_WS,'wrapper.mjs')).href,shortCircuit:true};
    return next(specifier,context);
  },
});
