const fs=require('fs'); const {spawn}=require('child_process'); const path=require('path');
const cfg='C:\\xiaoqian\\app\\napcat\\config';
const names=fs.readdirSync(cfg).filter(n=>/^onebot11_\d+\.json$/.test(n));
if(names.length!==1) { process.stdout.write('debug_precheck_failed\n'); process.exit(1); }
const ob=JSON.parse(fs.readFileSync(path.join(cfg,names[0]),'utf8'));
const web=JSON.parse(fs.readFileSync(path.join(cfg,'webui.json'),'utf8'));
const secrets=[web.token,...(ob.network.websocketServers||[]).map(x=>x.token)].filter(x=>typeof x==='string'&&x.length>=16);
const log='C:\\xiaoqian\\logs\\dsh-qq-social-debug-scope-after-link.log'; if(fs.existsSync(log)) {process.stdout.write('debug_log_exists\n');process.exit(1);}
let text='', truncated=false, timed=false;
const child=spawn(process.execPath,['C:\\xiaoqian\\app\\dsh\\node_modules\\@deepseek-ai\\dsh\\lib\\bin.js','--profile','qq-social','--patch','C:\\\\xiaoqian\\\\setup\\\\v33-scope-probe.patch.yml','--no-open'],{cwd:'C:\\xiaoqian\\data\\qq',env:{...process.env,DSH_HOME:'C:\\xiaoqian\\data\\qq\\dsh-home',DSH_TELEMETRY_DISABLED:'1'},stdio:['ignore','pipe','pipe']});
function collect(c){if(text.length<2*1024*1024)text+=c.toString('utf8').slice(0,2*1024*1024-text.length);else truncated=true;}
child.stdout.on('data',collect);child.stderr.on('data',collect);
const timer=setTimeout(()=>{timed=true;child.kill();},18000);
child.on('error',()=>{text+='\nCHILD_SPAWN_ERROR\n'});
child.on('close',(code,signal)=>{clearTimeout(timer);for(const s of secrets) text=text.split(s).join('[REDACTED]');text=text.replace(/([?&]token=)[^\s&#]+/gi,'$1[REDACTED]').replace(/(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;"']+/gi,'$1[REDACTED]').replace(/\bsk-[A-Za-z0-9_-]{10,}\b/g,'[REDACTED]');if(secrets.some(s=>text.includes(s))) {process.stdout.write('redaction_failed\n');process.exitCode=1;return;}fs.writeFileSync(log,`foreground_exit=${code} signal=${signal} timeout=${timed} truncated=${truncated}\n`+text,{flag:'wx',encoding:'utf8'});process.stdout.write(`foreground_exit=${code} timeout=${timed} log_written\n`);});
