import {spawnSync} from 'node:child_process';
process.stdout.write('Ready for source credential JSON on stdin (input is hidden).\n');
let input='';
for await (const chunk of process.stdin) {
 input+=chunk;
 if(input.includes('\n'))break;
}
const credential=JSON.parse(input.trim());
const origin=new URL(credential.remote_url).origin;
const env={...process.env,GIT_CONFIG_COUNT:'2',GIT_CONFIG_KEY_0:'credential.helper',GIT_CONFIG_VALUE_0:'',GIT_CONFIG_KEY_1:`http.${origin}/.extraHeader`,GIT_CONFIG_VALUE_1:`Authorization: Bearer ${credential.token}`,GIT_TERMINAL_PROMPT:'0'};
const result=spawnSync('git',['push',credential.remote_url,`HEAD:${credential.branch}`],{env,stdio:['ignore','pipe','pipe'],encoding:'utf8'});
process.stdout.write(result.stdout);process.stderr.write(result.stderr);
if(result.status!==0)process.exit(result.status||1);
const head=spawnSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).stdout.trim();
process.stdout.write(JSON.stringify({commit_sha:head,pushed:true})+'\n');
