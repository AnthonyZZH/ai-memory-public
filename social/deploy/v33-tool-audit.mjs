import fs from 'node:fs';
import { pathToFileURL } from 'node:url';

export const inject = ['agents', 'tools', 'agentPresets'];
export function apply(ctx) {
  const timer = setTimeout(async () => {
    const target = 'C:/xiaoqian/data/qq/v33-audit/tool-audit-retry.json';
    let handle;
    try {
      const mod = await import(pathToFileURL('C:/xiaoqian/data/qq/dsh-home/profiles/qq-social/node_modules/dsh-napcat/lib/social-policy.js').href);
      handle = await ctx.agents.create({
        sessionId: 'v33-audit-synthetic',
        meta: { cwd: 'C:/xiaoqian/data/qq', agentPreset: 'xiaoqian-social' },
        agentOptions: { provider: 'deepseek-official', model: 'deepseek-flash' },
        setup: async agentCtx => {
          mod.restrictSocialTools(agentCtx);
          await ctx.agentPresets.mount(agentCtx, 'xiaoqian-social');
        },
      });
      const names = ctx.tools.schemas(handle.agent).map(item => item.name).sort();
      fs.writeFileSync(target, JSON.stringify({ ok: true, scope: 'synthetic-agent', tools: names }), { flag: 'wx' });
    } catch (error) {
      fs.writeFileSync(target, JSON.stringify({ ok: false, errorType: error?.name ?? 'Error', reason: String(error?.message ?? '').replace(/([?&]token=)[^\\s&#]+/gi, '$1[REDACTED]').replace(/\\b[A-Za-z0-9_+-]{32,}\\b/g, '[REDACTED]').slice(0,300) }), { flag: 'wx' });
    } finally {
      if (handle) await handle.dispose();
    }
  }, 5000);
  ctx.on('dispose', () => clearTimeout(timer));
}
