import fs from 'node:fs';
import { pathToFileURL } from 'node:url';
export const inject = ['agents','tools','agentPresets'];
export function apply(ctx) {
  const timer=setTimeout(async()=>{
    const out='C:/xiaoqian/data/qq/v33-audit/scope-probe-after-link.json';
    let h, result={};
    try {
      const host=await import(pathToFileURL('C:/xiaoqian/app/dsh/node_modules/@deepseek-ai/dsh-scope/lib/index.js').href);
      const profile=await import(pathToFileURL('C:/xiaoqian/data/qq/dsh-home/profiles/qq-social/node_modules/@deepseek-ai/dsh-scope/lib/index.js').href);
      h=await ctx.agents.create({sessionId:'v33-scope-probe',meta:{cwd:'C:/xiaoqian/data/qq'},agentOptions:{provider:'deepseek-official',model:'deepseek-flash'},setup:async(agentCtx)=>{
        result.hostScope=host.scopeOf(agentCtx)!==undefined;
        result.profileScope=profile.scopeOf(agentCtx)!==undefined;
        try {agentCtx.tools.restrict({allow:[]});result.emptyRestrict=true;} catch(e) {result.emptyRestrict=false;result.reason=String(e?.message??'').replace(/\b[A-Za-z0-9_+-]{32,}\b/g,'[REDACTED]').slice(0,250);}
        throw new Error('PROBE_ABORT_BEFORE_PUBLICATION');
      }});
    } catch(e) {result.createError=String(e?.message??'').replace(/\b[A-Za-z0-9_+-]{32,}\b/g,'[REDACTED]').slice(0,250);}
    finally {if(h) await h.dispose(); fs.writeFileSync(out,JSON.stringify(result),{flag:'wx'});}
  },5000);
  ctx.on('dispose',()=>clearTimeout(timer));
}
