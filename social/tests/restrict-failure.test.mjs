import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import {root,temp,fakeHost,oneBot,settle} from './fixtures.mjs';
const load=file=>import(pathToFileURL(path.join(root,'dsh-napcat',file)));
async function fixture(t) {
  const server=await oneBot(); t.after(()=>server.close());
  const host=fakeHost(), logs=[];
  const {OneBotConnection}=await load('lib/onebot.js');
  const {Bridge}=await load('lib/bridge.js');
  const {resolveConfig}=await load('lib/config.js');
  let ready;const connected=new Promise(r=>{ready=r});
  const conn=new OneBotConnection({mode:'forward',url:server.url,host:'127.0.0.1',port:0,accessToken:'fixture-only',reconnectMaxAttempts:1,log:()=>{},onStatus:y=>{if(y)ready()},onEvent:()=>{}});
  conn.start();await connected;t.after(()=>conn.stop());
  const bridge=new Bridge({ctx:host.ctx,config:resolveConfig({workspacePath:temp('restrict'),groupAllowFrom:['11']}),conn,log:(_l,c)=>logs.push(c)});
  host.listen((session,e)=>bridge.onSessionEvent(session,e));
  const event={post_type:'message',message_type:'group',user_id:'101',group_id:'11',self_id:999,time:Math.floor(Date.now()/1000),message:[{type:'text',data:{text:'小千 synthetic'}}]};
  return {host,server,bridge,logs,event};
}
test('restriction failure rejects input and emits a single event code',async t=>{
  const q=await fixture(t);
  q.host.ctx.agents.create=async ({setup})=>{await setup({tools:{schemas:()=>[],restrict:()=>{throw Error('synthetic sensitive');},guard:()=>{}}},{});throw Error('unexpected');};
  await q.bridge.handleEvent(q.event).catch(()=>{});await settle(q.bridge);
  assert.equal(q.host.inputs.length,0);assert.equal(q.server.sent.length,0);
  assert.deepEqual(q.logs.filter(x=>x==='SOCIAL_TOOL_RESTRICT_FAILED'),['SOCIAL_TOOL_RESTRICT_FAILED']);
  assert.ok(!q.logs.some(x=>String(x).includes('synthetic sensitive')));
});
test('unverified live agent cannot be reused to bypass restriction',async t=>{
  const q=await fixture(t);let calls=0;
  q.host.ctx.agents.get=id=>({session:{id},whenIdle:async()=>{},followup:()=>{calls++}});
  await q.bridge.handleEvent(q.event).catch(()=>{});await settle(q.bridge);
  assert.equal(calls,0);assert.equal(q.server.sent.length,0);
  assert.ok(q.logs.includes('SOCIAL_TOOL_RESTRICT_FAILED'));
});
