import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import {syncBuiltinESMExports} from 'node:module';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {root,temp,logger,fakeHost,oneBot,wechatMcp,settle} from './fixtures.mjs';
const load=(project,file)=>import(pathToFileURL(path.join(root,project,file)));
const N='dsh-napcat',W='dsh-wechat-ai-bridge';

async function qq(t,reply=()=> 'hello',overrides={}) {
  const server=await oneBot();t.after(()=>server.close());
  const host=fakeHost(reply), logs=[];
  const {OneBotConnection}=await load(N,'lib/onebot.js');
  const {Bridge}=await load(N,'lib/bridge.js');
  const {resolveConfig}=await load(N,'lib/config.js');
  const dir=overrides.workspacePath || temp('qq');
  let ready;
  const connected=new Promise(resolve=>{ready=resolve;});
  const conn=new OneBotConnection({mode:'forward',url:server.url,host:'127.0.0.1',port:0,accessToken:'fixture-only',reconnectMaxAttempts:1,
    log:(_level,code)=>logs.push(code),onStatus:yes=>{if(yes)ready();},onEvent:()=>{}});
  conn.start();await connected;t.after(()=>conn.stop());
  const config=resolveConfig({workspacePath:dir,groupAllowFrom:['11','22'],allowFrom:['101','102'],...overrides});
  const bridge=new Bridge({ctx:host.ctx,config,conn,log:(_level,code)=>logs.push(code)});
  host.listen((session,event)=>bridge.onSessionEvent(session,event));
  return {server,host,bridge,conn,config,dir,logs};
}
function event(kind,id,text='小千 hello',user='101') {
  return {post_type:'message',message_type:kind,user_id:kind==='private'?id:user,
    ...(kind==='group'?{group_id:id}:{}),self_id:999,time:Math.floor(Date.now()/1000),message:[{type:'text',data:{text}}]};
}
async function wx(t,reply=()=> 'hello',overrides={}) {
  const server=await wechatMcp();t.after(()=>server.close());
  const host=fakeHost(reply),dir=overrides.workspacePath || temp('wechat');
  const {normalizeConfig,createLogger}=await load(W,'lib/util.js');
  const {emptyState}=await load(W,'lib/state.js');
  const {McpClient}=await load(W,'lib/mcp-client.js');
  const {WechatApi}=await load(W,'lib/wechat-api.js');
  const {Bridge}=await load(W,'lib/bridge.js');
  const config=normalizeConfig({workspacePath:dir,statePath:path.join(dir,'state.json'),logPath:path.join(dir,'event.log'),...overrides});
  const log=createLogger({logger:host.ctx.logger},config);
  const client=new McpClient({url:server.url,token:'fixture-only',logger:log});t.after(()=>client.close());
  const store={data:emptyState(),save:()=>{}};
  const bridge=new Bridge(host.ctx,config,store,new WechatApi(client),log);
  bridge.identityResolved=true;
  host.listen((session,e)=>bridge.onSessionEvent(session,e));
  bridge.resolveSenderNicknames=async()=>{};
  bridge.ensureAgent=async contact=>{
    let entry=bridge.agents.get(contact.username);if(entry)return entry;
    const handle=await host.ctx.agents.create({sessionId:'wx-'+contact.username,meta:{cwd:dir}});
    entry={handle,sessionId:handle.agent.session.id,busy:false};
    bridge.agents.set(contact.username,entry);bridge.knownSessions.add(entry.sessionId);
    bridge.chatState(contact);return entry;
  };
  return {server,host,bridge,client,config,dir};
}
const contact=(username,group=true)=>({username,display_name:username,is_chatroom:group});
const batch=(mentioned=true,text='hello')=>[{mentioned,message:{text,create_time:1,time:'synthetic',sender_username:'fixture',sender_display:'fixture'}}];

test('QQ multiple groups and private chats reply only to their triggering chat',async t=>{
  const q=await qq(t,(message,id)=>'reply:'+id);
  await Promise.all([q.bridge.handleEvent(event('group','11')),q.bridge.handleEvent(event('group','22')),
    q.bridge.handleEvent(event('private','101')),q.bridge.handleEvent(event('private','102'))]);
  await settle(q.bridge);
  assert.equal(q.host.inputs.length,4);assert.equal(q.server.sent.length,4);
  for(const item of q.server.sent){const id=String(item.group_id??item.user_id);assert.ok(item.message[0].data.text.includes(item.message_type+'-'+id));}
  assert.ok(q.host.scopes.length>=4);
  for(const guard of q.host.scopes){assert.equal(guard({name:'mcp__public__read_note'}),undefined);assert.equal(guard({name:'napcat_send_message'}),'SOCIAL_TOOL_DENIED');assert.equal(guard({name:'workspace_run'}),'SOCIAL_TOOL_DENIED');}
});
test('QQ private allowlist outsider never enters model, any number of IDs accepted',async t=>{
  const q=await qq(t,()=> 'ok',{allowFrom:Array.from({length:120},(_,i)=>String(1000+i)),groupAllowFrom:Array.from({length:120},(_,i)=>String(2000+i))});
  await q.bridge.handleEvent(event('private','9999'));await settle(q.bridge);assert.equal(q.host.inputs.length,0);
  await q.bridge.handleEvent(event('private','1119'));await q.bridge.handleEvent(event('group','2119'));await settle(q.bridge);
  assert.equal(q.host.inputs.length,2);assert.equal(q.config.allowFrom.length,120);assert.equal(q.config.groupAllowFrom.length,120);
});
test('QQ final image/file paths and memes cannot read files or send media',async t=>{
  const q=await qq(t,()=>String.raw`[图片:C:\Windows\win.ini] ![x](C:\Windows\win.ini) [表情:hi]`);
  const original=fsp.readFile;let reads=0;
  fsp.readFile=async function(file,...args){if(String(file).includes('win.ini')){reads++;throw new Error('forbidden fixture read');}return original.call(this,file,...args);};syncBuiltinESMExports();
  try{await q.bridge.handleEvent(event('group','11'));await settle(q.bridge);}finally{fsp.readFile=original;syncBuiltinESMExports();}
  assert.equal(reads,0);assert.equal(q.server.sent.length,0);
});
test('QQ SKIP on a mandatory turn suppresses output and budget use',async t=>{
  const q=await qq(t,()=> '__SKIP__');await q.bridge.handleEvent(event('group','11'));await settle(q.bridge);
  assert.equal(q.server.sent.length,0);assert.equal(q.bridge.social.rows('group:11').length,0);
});
test('QQ raw model error and diagnostic text never reach group or event logs',async t=>{
  const q=await qq(t,()=>new Error('FIXTURE_SECRET_BODY'));await q.bridge.handleEvent(event('group','11'));await settle(q.bridge);
  assert.equal(q.server.sent.length,0);assert.ok(!q.logs.some(x=>x.includes('FIXTURE_SECRET_BODY')));
  assert.ok(q.logs.filter(x=>x.startsWith('SOCIAL_')).length>0);
});
test('QQ multi-segment response is one logical send; budget persists after restart',async t=>{
  const q=await qq(t,()=> 'abcdefghij',{splitMaxChars:3});await q.bridge.handleEvent(event('group','11'));await settle(q.bridge);
  assert.ok(q.server.sent.length>1);assert.equal(q.bridge.social.rows('group:11').length,1);
  const other=await qq(t,()=> 'again',{workspacePath:q.dir});assert.equal(other.bridge.social.rows('group:11').length,1);
});
test('QQ native proactive decision observes persistent cooldown and does not limit named replies',async t=>{
  const q=await qq(t,()=> 'unsolicited',{proactiveRatePerHour:0,proactiveChance:1});
  const original=Date.now;let now=Date.parse('2026-10-28T04:00:00Z');Date.now=()=>now;
  q.bridge.social.now=()=>now;
  try{
    q.bridge.chatter.set('group:11',[now,now]);
    await q.bridge.maybeInterject({kind:'group',id:'11',key:'group:11'});await settle(q.bridge);
    assert.equal(q.server.sent.length,1);assert.equal(q.bridge.social.rows('group:11')[0].proactive,true);
    q.bridge.chatter.set('group:11',[now,now]);await q.bridge.maybeInterject({kind:'group',id:'11',key:'group:11'});await settle(q.bridge);
    assert.equal(q.server.sent.length,1);
    await q.bridge.handleEvent(event('group','11','小千 说句话'));await settle(q.bridge);assert.equal(q.server.sent.length,2);
  }finally{Date.now=original;}
});
test('Wechat multiple groups and private friends never cross-route',async t=>{
  const w=await wx(t,(_m,id)=>'reply:'+id);
  const contacts=[contact('a@chatroom'),contact('b@chatroom'),contact('friend1',false),contact('friend2',false)];
  await Promise.all(contacts.map(c=>w.bridge.runBatch(c,batch(),0)));
  assert.equal(w.server.sent.length,4);
  for(const item of w.server.sent)assert.equal(item.message,'reply:wx-'+item.recipient_name);
});
test('Wechat current-chat read has no recipient parameter and rejects cross-chat attempt',async t=>{
  const w=await wx(t);const {registerTools}=await load(W,'lib/tools.js');registerTools(w.host.ctx,w.bridge,w.bridge.api);
  assert.deepEqual([...w.host.tools.keys()],['wechat_recent_messages']);
  await w.bridge.runBatch(contact('a@chatroom'),batch(),0);w.host.current('wx-a@chatroom');
  const tool=w.host.tools.get('wechat_recent_messages');
  await assert.rejects(tool.execute({contact_name:'other@chatroom'}),/SOCIAL_ARGUMENT_DENIED/);
  await tool.execute({limit:1});assert.equal(w.server.calls.at(-1).args.contact_name,'a@chatroom');
  w.host.current(undefined);await assert.rejects(tool.execute({}),/SOCIAL_CHAT_DENIED/);
});
test('Wechat SKIP and path markers suppress sends without an error',async t=>{
  for(const output of ['__SKIP__',String.raw`[图片:C:\Windows\win.ini]`]){
    const w=await wx(t,()=>output);await w.bridge.runBatch(contact('a@chatroom'),batch(false),0);
    assert.equal(w.server.sent.length,0);assert.equal(w.bridge.social.rows('a@chatroom').length,0);
    assert.ok(!w.host.ctx.logger.lines.includes('WECHAT_WARN'));
  }
});
test('Wechat errors are neither sent nor recorded verbatim',async t=>{
  const w=await wx(t,()=>new Error('FIXTURE_SECRET_BODY'));await w.bridge.runBatch(contact('a@chatroom'),batch(),0);
  w.bridge.logger.rate('secret','FIXTURE_SECRET_BODY');
  assert.equal(w.server.sent.length,0);assert.ok(!fs.readFileSync(w.config.logPath,'utf8').includes('FIXTURE_SECRET_BODY'));
});
test('Wechat proactive cooldown persists; name/private mandatory bypasses proactive cap',async t=>{
  const w=await wx(t);let now=Date.parse('2026-10-28T04:00:00Z');w.bridge.social.now=()=>now;
  const c=contact('a@chatroom');await w.bridge.runBatch(c,batch(false),0);assert.equal(w.server.sent.length,1);
  await w.bridge.runBatch(c,batch(false),0);assert.equal(w.server.sent.length,1);
  await w.bridge.runBatch(c,batch(false,'小千 hello'),0);assert.equal(w.server.sent.length,2);
  const fresh=await wx(t,()=> 'next',{workspacePath:w.dir});fresh.bridge.social.now=()=>now;
  await fresh.bridge.runBatch(c,batch(false),0);assert.equal(fresh.server.sent.length,0);
  await fresh.bridge.runBatch(contact('a-friend',false),batch(false),0);assert.equal(fresh.server.sent.length,1);
});
const MARKERS=[String.raw`[图片:C:\Windows\win.ini]`,String.raw`看这个 ![x](C:\Windows\win.ini)`,'[表情:hi]','[图片：/etc/passwd]','[CQ:image,file=file:///C:/Windows/win.ini]'];
test('QQ each path/meme marker alone drops the whole reply with only an event code; plain text still sends',async t=>{
  for(const output of MARKERS){
    const q=await qq(t,()=>'前缀文字 '+output);
    await q.bridge.handleEvent(event('group','11'));await q.bridge.handleEvent(event('private','101'));await settle(q.bridge);
    assert.equal(q.host.inputs.length,2);assert.equal(q.server.sent.length,0);
    assert.equal(q.bridge.social.rows('group:11').length,0);assert.equal(q.bridge.social.rows('private:101').length,0);
    assert.ok(q.logs.includes('SOCIAL_PATH_MARKER_DROPPED'));
    assert.ok(!q.logs.some(x=>/win\.ini|passwd|前缀/.test(x)));
  }
  const ok=await qq(t,()=> '[图片] 只是普通文字');await ok.bridge.handleEvent(event('group','11'));await settle(ok.bridge);
  assert.equal(ok.server.sent.length,1);
});
test('Wechat path/meme markers drop the reply in daytime, mandatory and proactive, without budget or body in logs',async t=>{
  for(const output of MARKERS)for(const mentioned of [true,false]){
    const w=await wx(t,()=>output);w.bridge.social.now=()=>Date.parse('2026-10-28T04:00:00Z');
    await w.bridge.runBatch(contact('a@chatroom'),batch(mentioned),0);await w.bridge.runBatch(contact('friend1',false),batch(mentioned),0);
    assert.equal(w.server.sent.length,0);assert.equal(w.bridge.social.rows('a@chatroom').length,0);assert.equal(w.bridge.social.rows('friend1').length,0);
    assert.ok(w.host.ctx.logger.lines.includes('SOCIAL_PATH_MARKER_DROPPED'));assert.ok(!w.host.ctx.logger.lines.includes('WECHAT_WARN'));
    assert.ok(!fs.readFileSync(w.config.logPath,'utf8').match(/win\.ini|passwd/));
  }
  const ok=await wx(t,()=> 'plain');ok.bridge.social.now=()=>Date.parse('2026-10-28T04:00:00Z');
  await ok.bridge.runBatch(contact('a@chatroom'),batch(false),0);assert.equal(ok.server.sent.length,1);
});
test('Wechat friend default stays open with many group allowlist entries',async t=>{
  const ids=Array.from({length:120},(_,i)=>'g'+i+'@chatroom');
  const w=await wx(t,()=> 'yes',{reply:{allowContacts:ids}});
  assert.ok(w.bridge.allowedChat(contact('friend',false)));assert.ok(w.bridge.allowedChat(contact(ids.at(-1))));
  assert.equal(w.bridge.allowedChat(contact('outside@chatroom')),false);
});
