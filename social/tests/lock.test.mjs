import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {pathToFileURL} from 'node:url';
import {root,temp} from './fixtures.mjs';

// A pid that certainly belonged to a process which has already exited.
async function deadPid(){
  const child=spawn(process.execPath,['-e','0'],{stdio:'ignore'});
  await new Promise(resolve=>child.on('exit',resolve));return child.pid;
}
function runChild(policy,file,chats,rounds){
  const code=`const {SendBudget}=await import(process.env.P);
const b=new SendBudget(process.env.F,{cooldownMinutes:10,maxPerHour:4,timezone:'UTC'});
const chats=JSON.parse(process.env.C);let ok=0;
await Promise.all(Array.from({length:Number(process.env.R)},async()=>{for(const c of chats)if(await b.send(c,false,async()=>{await new Promise(r=>setTimeout(r,Math.random()*3));}))ok++;}));
process.stdout.write(JSON.stringify({ok}));`;
  return new Promise((resolve,reject)=>{
    const child=spawn(process.execPath,['--input-type=module','-e',code],{env:{...process.env,P:pathToFileURL(policy).href,F:file,C:JSON.stringify(chats),R:String(rounds)},stdio:['ignore','pipe','pipe']});
    let out='',err='';child.stdout.on('data',d=>out+=d);child.stderr.on('data',d=>err+=d);
    child.on('exit',code=>code===0?resolve(JSON.parse(out).ok):reject(new Error('child failed '+code+' '+err.slice(0,400))));
  });
}

for(const project of ['dsh-napcat','dsh-wechat-ai-bridge']){
  const policy=path.join(root,project,'lib/social-policy.js');
  const {SendBudget}=await import(pathToFileURL(policy));
  const make=(dir,extra={})=>new SendBudget(path.join(dir,'state.json'),{cooldownMinutes:10,maxPerHour:4,timezone:'UTC',...extra});
  const plant=(dir,record,ageMs)=>{
    const lock=path.join(dir,'state.json.lock');fs.writeFileSync(lock,typeof record==='string'?record:JSON.stringify(record));
    const when=new Date(Date.now()-ageMs);fs.utimesSync(lock,when,when);return lock;
  };

  test(project+' lock is released after each send and never left behind',async()=>{
    const dir=temp('lock');const b=make(dir);
    assert.equal(await b.send('g',false,async()=>{assert.ok(fs.existsSync(path.join(dir,'state.json.lock'))===false);}),true);
    await assert.rejects(b.send('g',false,async()=>{throw new Error('uncertain');}),/uncertain/);
    assert.deepEqual(fs.readdirSync(dir).sort(),['state.json']);assert.equal(b.rows('g').length,2);
  });

  test(project+' stale lock of a dead local pid is set aside (kept for inspection) and the send proceeds',async()=>{
    const dir=temp('lock');const pid=await deadPid();
    plant(dir,{pid,host:os.hostname(),at:Date.now()-120000,token:'old'},120000);
    let calls=0;assert.equal(await make(dir).send('g',false,async()=>{calls++;}),true);assert.equal(calls,1);
    const names=fs.readdirSync(dir);assert.ok(!names.includes('state.json.lock'));
    const kept=names.filter(n=>n.startsWith('state.json.lock.stale-'));assert.equal(kept.length,1);
    assert.equal(JSON.parse(fs.readFileSync(path.join(dir,kept[0]),'utf8')).token,'old');
  });

  test(project+' live, fresh, remote or unreadable locks are never overridden; bounded wait fails closed',async()=>{
    const pid=await deadPid();
    const cases=[
      ['live local pid, very old',{pid:process.pid,host:os.hostname(),at:Date.now()-3600000,token:'live'},3600000],
      ['dead pid but fresh',{pid,host:os.hostname(),at:Date.now(),token:'fresh'},0],
      ['dead pid but future timestamp',{pid,host:os.hostname(),at:Date.now()+3600000,token:'future'},120000],
      ['remote host, old',{pid,host:'some-other-host.invalid',at:Date.now()-3600000,token:'remote'},3600000],
      ['unreadable, old','{partial',3600000],
    ];
    for(const [label,record,age] of cases){
      const dir=temp('lock');const lock=plant(dir,record,age);const before=fs.readFileSync(lock,'utf8');
      let calls=0;const started=Date.now();
      await assert.rejects(make(dir,{lockWaitMs:150}).send('g',false,async()=>{calls++;}),/SOCIAL_BUDGET_LOCKED/,label);
      assert.ok(Date.now()-started<5000,label+' wait is bounded');
      assert.equal(calls,0,label);assert.equal(fs.readFileSync(lock,'utf8'),before,label);
      assert.ok(!fs.existsSync(path.join(dir,'state.json')),label+' nothing reserved');
      assert.deepEqual(fs.readdirSync(dir),['state.json.lock'],label+' nothing renamed');
    }
  });

  test(project+' waiting on a held lock succeeds once it is released',async()=>{
    const dir=temp('lock');const lock=plant(dir,{pid:process.pid,host:os.hostname(),at:Date.now(),token:'held'},0);
    setTimeout(()=>fs.renameSync(lock,lock+'.released'),120);
    let calls=0;assert.equal(await make(dir,{lockWaitMs:5000}).send('g',false,async()=>{calls++;}),true);assert.equal(calls,1);
  });

  test(project+' separate OS processes serialize on one state file: no lost updates, global cap holds',async()=>{
    const dir=temp('lock');const file=path.join(dir,'state.json');
    // Distinct chats per process: every send is eligible, so any lost update shows as missing rows.
    const own=await Promise.all([0,1,2,3].map(i=>runChild(policy,file,Array.from({length:5},(_,j)=>'p'+i+'-c'+j),1)));
    assert.deepEqual(own,[5,5,5,5]);
    const b=make(dir);for(let i=0;i<4;i++)for(let j=0;j<5;j++)assert.equal(b.rows('p'+i+'-c'+j).length,1);
    // One shared chat hammered by 4 processes x 4 concurrent sends: exactly the 6/minute cap succeeds.
    const shared=await Promise.all([0,1,2,3].map(()=>runChild(policy,file,['shared'],4)));
    assert.equal(shared.reduce((a,b)=>a+b,0),6);assert.equal(make(dir).rows('shared').length,6);
    assert.ok(!fs.readdirSync(dir).some(n=>n.endsWith('.lock')||n.includes('.break')||n.endsWith('.tmp')));
  });
}
