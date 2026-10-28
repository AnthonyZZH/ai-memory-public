import test from 'node:test';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import path from 'node:path';
import {root,temp,fakeHost,logger} from './fixtures.mjs';
const load=(project,file)=>import(pathToFileURL(path.join(root,project,file)));

test('CONTRACT napcat registers no cross-chat, raw API or file tools',async()=>{
  const {registerTools}=await load('dsh-napcat','lib/tools.js');
  const host=fakeHost();registerTools(host.ctx,{call:async()=>({})},()=>{},{});
  assert.deepEqual([...host.tools.keys()],[]);
});
test('CONTRACT wechat forces safe settings despite unsafe caller input',async()=>{
  const {normalizeConfig}=await load('dsh-wechat-ai-bridge','lib/util.js');
  const dir=temp('contract');
  const c=normalizeConfig({workspacePath:dir,statePath:path.join(dir,'state.json'),logPath:path.join(dir,'log'),
    workspaceTools:true,codex:{enabled:true},tts:{enabled:true},reply:{files:true},toolAllowlist:['workspace_run']});
  assert.equal(c.workspaceTools,false);assert.equal(c.codex.enabled,false);assert.equal(c.tts.enabled,false);
  assert.equal(c.reply.files,false);assert.ok(!c.toolAllowlist.includes('workspace_run'));
});
