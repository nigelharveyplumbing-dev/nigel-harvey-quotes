import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { bounded, BrowserOperationTimeout, stopServer } from './batch8_browser_support.mjs';

const events=[];
const start=Date.now();
await assert.rejects(bounded('test/pending-evaluate',()=>new Promise(()=>{}),40,e=>events.push(e)),BrowserOperationTimeout);
assert(Date.now()-start<1000,'A never-settling browser operation must have a host deadline');
assert.deepEqual(events.map(e=>e.state),['start','failed']);

await assert.rejects(bounded('test/private-values',()=>{throw new Error('private body must never appear in diagnostics')},100,e=>events.push(e)));
assert(!JSON.stringify(events).includes('private body'));

const child=spawn(process.execPath,['-e',"process.on('SIGTERM',()=>{});console.log('ready');setInterval(()=>{},1000)"],{stdio:['ignore','pipe','pipe']});
child.stderr.resume();
try {
  await bounded('test/child-ready',()=>new Promise(resolve=>child.stdout.once('data',resolve)),1000);
  const result=await stopServer(child,100);
  assert.equal(result.terminated,true);assert.equal(result.forced,true);
  assert(child.signalCode!==null || child.exitCode!==null,'Child must be reaped after forced termination');
} finally { if(child.exitCode===null&&child.signalCode===null)child.kill('SIGKILL'); }
console.log('Batch 8 operation deadlines, diagnostic privacy and forced child cleanup: PASS');
