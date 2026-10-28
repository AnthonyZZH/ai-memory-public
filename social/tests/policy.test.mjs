import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {root,temp} from './fixtures.mjs';
for(const [project,cooldown,cap] of [['dsh-napcat',10,4],['dsh-wechat-ai-bridge',3,12]]){
  const {SendBudget,restrictSocialTools,minuteAt}=await import(pathToFileURL(path.join(root,project,'lib/social-policy.js')));
  function setup(time='2026-10-28T04:00:00Z',timezone='Asia/Shanghai'){
    const file=path.join(temp('budget'),'state.json');let now=Date.parse(time);
    const options={cooldownMinutes:cooldown,maxPerHour:cap,timezone,now:()=>now};
    return {file,options,b:new SendBudget(file,options),advance:ms=>{now+=ms;}};
  }
  test(project+' cooldown boundary and hourly cap; mandatory ignores proactive budget',async()=>{
    const x=setup();let sends=0;
    for(let i=0;i<cap;i++){
      assert.equal(await x.b.send('g',true,async()=>{sends++;}),true);
      assert.equal(x.b.eligible('g',true),false);
      x.advance(cooldown*60000-1);assert.equal(x.b.eligible('g',true),false);x.advance(1);
    }
    assert.equal(sends,cap);assert.equal(await x.b.send('g',true,async()=>{sends++;}),false);
    assert.equal(await x.b.send('g',false,async()=>{sends++;}),true);
    x.advance(3600000);assert.equal(x.b.eligible('g',true),true);
  });
  test(project+' silent hours use configured timezone and exact 01/08 boundaries',()=>{
    for(const [time,allowed] of [['2026-10-27T16:59:00Z',true],['2026-10-27T17:00:00Z',false],['2026-10-27T23:59:00Z',false],['2026-10-28T00:00:00Z',true]]){
      const x=setup(time);assert.equal(x.b.eligible('g',true),allowed);assert.equal(x.b.eligible('g',false),true);
    }
    assert.equal(minuteAt(Date.parse('2026-10-28T02:00Z'),'UTC'),120);
    assert.equal(setup('2026-10-28T02:00Z','UTC').b.eligible('g',true),false);
    assert.throws(()=>setup('2026-10-28T02:00Z','invalid-timezone'));
  });
  test(project+' global six logical replies/minute; restart and multi-instance serialize',async()=>{
    const x=setup();let count=0;
    const other=new SendBudget(x.file,x.options);
    const result=await Promise.all(Array.from({length:10},(_,i)=>(i%2?x.b:other).send('g',false,async()=>{count++;})));
    // Competing instances may fail closed at the file lock; they cannot exceed cap.
    assert.ok(count<=6);assert.ok(result.filter(Boolean).length<=6);
    const restarted=new SendBudget(x.file,x.options);assert.equal(restarted.rows('g').length,count);
  });
  test(project+' failed/ambiguous transport keeps reservation; corrupted state fails closed',async()=>{
    const x=setup();await assert.rejects(x.b.send('g',true,async()=>{throw new Error('uncertain');}));
    assert.equal(new SendBudget(x.file,x.options).eligible('g',true),false);
    fs.writeFileSync(x.file,'broken');assert.throws(()=>new SendBudget(x.file,x.options),/SOCIAL_BUDGET_INVALID/);
  });
  test(project+' budget is stored before transport, same-chat concurrent proactive never double-sends',async()=>{
    const x=setup();let calls=0;
    const send=()=>x.b.send('g',true,async()=>{assert.equal(new SendBudget(x.file,x.options).rows('g').length,1);calls++;});
    const results=await Promise.all([send(),send(),send()]);assert.equal(calls,1);assert.equal(results.filter(Boolean).length,1);
    assert.ok(!fs.readFileSync(x.file,'utf8').includes('message body'));
  });
  test(project+' tool guard rejects inherited command and cross-chat tools',()=>{
    let guard,allowed;
    restrictSocialTools({tools:{schemas:()=>[{name:'mcp__public__search_notes'},{name:'mcp__public__read_note'}],restrict:value=>{allowed=value.allow;},guard:fn=>{guard=fn;}}});
    assert.deepEqual(allowed,['mcp__public__search_notes','mcp__public__read_note']);
    for(const name of ['napcat_send_message','napcat_api','napcat_send_file','workspace_run','mcp__memory__read_note'])assert.equal(guard({name}),'SOCIAL_TOOL_DENIED');
    assert.throws(()=>restrictSocialTools({}),/SOCIAL_GUARD_UNAVAILABLE/);
  });
}
