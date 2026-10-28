import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { WebSocketServer } from 'ws';

export const root = process.env.SOCIAL_VENDOR;
export function temp(label) { return fs.mkdtempSync(path.join(process.env.SOCIAL_TEST_TMP,label+'-')); }
export function logger() {
  const lines=[];
  return {lines, info:x=>lines.push(String(x)),warn:x=>lines.push(String(x)),error:x=>lines.push(String(x)),
    rate:(key,x)=>lines.push(String(key)+':'+String(x)),clean:x=>String(x),reset:()=>{},addSecret:()=>{}};
}
export function fakeHost(reply = () => 'fixture-reply') {
  const listeners=new Set(), live=new Map(), tools=new Map(), scopes=[], inputs=[];
  let currentId;
  const registry=()=>({register:tool=>{tools.set(tool.name,tool);return()=>tools.delete(tool.name);},
    schemas:()=>[{name:'mcp__public__search_notes'},{name:'mcp__public__read_note'}], restrict:()=>{}, guard:fn=>{scopes.push(fn);return()=>{};}});
  const ctx={
    tools:registry(), logger:logger(),
    get:name=>ctx[name], on:(_name,fn)=>{listeners.add(fn);return()=>listeners.delete(fn);},
    approval:{setPolicy:()=>{}},permissionPresets:{set:()=>{}},sessionTitle:{rename:()=>({})},
    workspaceRegistry:{archivedSessionIds:[],resolveByPath:async()=>undefined,create:async cwd=>({path:cwd,attachSession:async()=>{}})},
    sessionPersistence:{stat:async()=>undefined},
    agentDefaultModel:{currentSelection:()=>({provider:'fixture',model:'fixture'})},
    agentPresets:{mount:async()=>({id:'fixture'})},
  };
  ctx.agents={get:id=>live.get(id),currentInitiator:async()=>currentId,
    async create({sessionId,meta,setup}) {
      const session={id:sessionId,header:{...meta}}, agent={session};
      if(setup) await setup({tools:registry()},agent);
      let idle=Promise.resolve();
      const emit=(type,data)=>{for(const fn of listeners)fn(session,{type,data});};
      agent.followup = message => {
        inputs.push({sessionId,message});
        idle=(async()=>{
          emit('turn/start',{});
          const result=await reply(message,sessionId);
          if(result instanceof Error){emit('assistant/attempt',{stream:{secret:result.message}});emit('turn/end',{reason:{kind:'error',error:result}});return;}
          emit('assistant/message',{message:{content:[{type:'text',text:String(result)}]}});
          emit('turn/end',{reason:{kind:'completed'}});
        })();return idle;
      };
      agent.whenIdle=()=>idle;agent.cancel=()=>{};
      live.set(sessionId,agent);
      return {agent,dispose:async()=>{live.delete(sessionId);}};
    },
  };
  return {ctx,tools,scopes,inputs,listen:fn=>listeners.add(fn),current:id=>{currentId=id;}};
}
export async function oneBot() {
  const server=http.createServer();const ws=new WebSocketServer({server});const sent=[];
  ws.on('connection',(socket,req)=>{
    if(req.headers.authorization!=='Bearer fixture-only'){socket.close();return;}
    socket.on('message',data=>{
      const frame=JSON.parse(data.toString());
      if(frame.action==='send_msg')sent.push(frame.params);
      socket.send(JSON.stringify({status:'ok',retcode:0,echo:frame.echo,data:frame.action==='get_login_info'?{user_id:999}:{message_id:sent.length}}));
    });
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  return {sent,url:`ws://127.0.0.1:${server.address().port}`,close:async()=>{
    for(const socket of ws.clients)socket.terminate();await new Promise(resolve=>ws.close(resolve));await new Promise(resolve=>server.close(resolve));
  }};
}
export async function wechatMcp() {
  const sent=[],calls=[];let fail=false;
  const server=http.createServer(async(req,res)=>{
    if(req.headers.authorization!=='Bearer fixture-only'){res.writeHead(401);res.end();return;}
    const chunks=[];for await(const chunk of req)chunks.push(chunk);
    const message=JSON.parse(Buffer.concat(chunks));
    res.setHeader('content-type','application/json');res.setHeader('mcp-session-id','fixture-session');
    if(message.method==='notifications/initialized'){res.writeHead(202);res.end();return;}
    let result={protocolVersion:'2024-11-05',capabilities:{},serverInfo:{name:'fake-wechat',version:'1'}};
    if(message.method==='tools/call'){
      const {name,arguments:args}=message.params;calls.push({name,args});
      if(fail){res.end(JSON.stringify({jsonrpc:'2.0',id:message.id,error:{code:-32000,message:'FIXTURE_SECRET_BODY'}}));return;}
      let payload={status:'ok',messages:[]};
      if(name==='send_text_msg'){sent.push(args);payload={status:'executed',completed:true};}
      if(name==='get_recent_messages')payload={messages:[{text:'synthetic recent message'}]};
      result={content:[{type:'text',text:JSON.stringify(payload)}]};
    }
    res.end(JSON.stringify({jsonrpc:'2.0',id:message.id,result}));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  return {sent,calls,url:`http://127.0.0.1:${server.address().port}/mcp`,fail:()=>{fail=true;},close:async()=>{
    server.closeAllConnections();await new Promise(resolve=>server.close(resolve));
  }};
}
export async function settle(bridge) {
  for(let i=0;i<10;i++){
    await new Promise(resolve=>setImmediate(resolve));
    if(bridge.socialTurns?.size)await Promise.all([...bridge.socialTurns.values()]);
    if(bridge.social?.tail)await bridge.social.tail;
  }
}
