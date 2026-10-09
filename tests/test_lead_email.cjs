const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('static/app.js', 'utf8');
const start = source.indexOf('function leadEmailStatusHtml(');
const end = source.indexOf('function buildLeadWhatsappHref(', start);
assert(start > 0 && end > start);
const button = {disabled:false};
const alerts = [];
let loads = 0;
const requests = [];
let response = {ok:true, json:async()=>({status:'failed', error_code:'authentication_failed'})};
const context = vm.createContext({
  document:{getElementById:()=>button},
  fetch:async (...args)=>{requests.push(args); return response;},
  alert:text=>alerts.push(text), loadLeads:async()=>{loads++;},
});
vm.runInContext(source.slice(start, end), context);

async function main() {
  assert.match(context.leadEmailStatusHtml(3, {status:'failed'}), /Retry email alert/);
  assert.match(context.leadEmailStatusHtml(3, {status:'pending'}), /enquiry saved/);
  assert.match(context.leadEmailStatusHtml(3), /Send email alert/);
  for (const status of ['accepted', 'sending']) {
    assert.doesNotMatch(context.leadEmailStatusHtml(3, {status}), /<button/);
  }
  assert.doesNotMatch(context.leadEmailStatusHtml(3, {status:'<script>secret</script>'}), /<script>/);
  await context.retryLeadEmail(3);
  assert.equal(requests[0][0], '/api/leads/3/retry-email');
  assert.equal(requests[0][1].method, 'POST');
  assert.match(alerts.pop(), /rejected the saved login.*enquiry remains saved/);
  assert.equal(button.disabled, false);
  assert.equal(loads, 1);
  response = {ok:true, json:async()=>({status:'accepted'})};
  await context.retryLeadEmail(3);
  assert.match(alerts.pop(), /mail server accepted/);
  response = {ok:false, json:async()=>({detail:'Lead not found'})};
  await context.retryLeadEmail(3);
  assert.equal(alerts.pop(), 'Lead not found');
  assert.equal(button.disabled, false);
  console.log('Lead email controls: PASS');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
