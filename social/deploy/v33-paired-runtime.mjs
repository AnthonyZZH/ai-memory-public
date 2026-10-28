import fs from 'node:fs';
import { pathToFileURL } from 'node:url';
export const inject=['agents','tools','agentPresets'];
export function apply(ctx) {
  const timer=setTimeout(async()=>{
    const base='C:/xiaoqian/data/qq/dsh-home/profiles/qq-social/node_modules/';
    const rows=[];
    for (const [label,dir] of [['before','dsh-napcat'],['after','dsh-napcat-v33-candidate']]) {
      let handle;
      try {
        const mod=await import(pathToFileURL(base+dir+'/lib/social-policy.js').href);
        handle=await ctx.agents.create({sessionId:'v33-paired-'+label,meta:{cwd:'C:/xiaoqian/data/qq',agentPreset:'xiaoqian-social'},agentOptions:{provider:'deepseek-official',model:'deepseek-flash'},setup:async(agentCtx,agent)=>{
          mod.restrictSocialTools(agentCtx);
          await ctx.agentPresets.mount(agentCtx,'xiaoqian-social');
          const names=agentCtx.tools.schemas(agent).map(v=>v.name).sort();
          if(names.some(x=>!mod.PUBLIC_TOOLS.includes(x))) throw new Error('SOCIAL_UNEXPECTED_TOOL');
        }});
        const names=ctx.tools.schemas(handle.agent).map(v=>v.name).sort();
        rows.push({label,ok:true,tools:names});
      } catch(e) {
        const msg=String(e?.message??'');
        const code=msg.includes('unknown global tool')?'UNKNOWN_GLOBAL_TOOL':msg.includes('scoped context')?'NOT_SCOPED':msg.includes('SOCIAL_UNEXPECTED_TOOL')?'UNEXPECTED_TOOL':'OTHER';
        rows.push({label,ok:false,error:code});
      } finally {if(handle) await handle.dispose();}
    }
    fs.writeFileSync('C:/xiaoqian/data/qq/v33-audit/paired-runtime.json',JSON.stringify(rows),{flag:'wx'});
  },5000);
  ctx.on('dispose',()=>clearTimeout(timer));
}
