import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync('static/public_analytics.js','utf8');
const local=new Map([['nhp_analytics_choice_v1','accepted']]),session=new Map();let handlers={},loaded=[];
function run(path,search='',referrer='') {
 handlers={};const banner={hidden:true,querySelector:s=>({addEventListener:(_,cb)=>handlers[s]=cb,focus(){}})};
 const location={pathname:path,search,origin:'https://example.invalid',hostname:'example.invalid',href:'https://example.invalid'+path+search,reload(){}};
 const context={window:{},document:{referrer,cookie:'',getElementById:id=>id==='public-analytics'?{dataset:{measurementId:'G-TEST',sendToGoogle:'true'}}:id==='analytics-consent'?banner:{addEventListener(){}},head:{appendChild:x=>loaded.push(x)},createElement:()=>({}),addEventListener(){},body:{contains:()=>true}},location,localStorage:{getItem:k=>local.get(k),setItem:(k,v)=>local.set(k,v)},sessionStorage:{getItem:k=>session.get(k),setItem:(k,v)=>session.set(k,v),removeItem:k=>session.delete(k)},URL,URLSearchParams,Date,encodeURIComponent};
 vm.createContext(context);vm.runInContext(source,context);return context;
}
let c=run('/plumber-guildford','?utm_source=google&utm_medium=organic&utm_campaign=repairs','https://google.com/search?q=private');
assert.equal(c.window.nhpAttribution.context().landing_page,'/plumber-guildford');
assert.equal(c.window.nhpAttribution.context().referrer,'https://google.com');
c=run('/bathroom-plumbing','?utm_source=bing');assert.equal(c.window.nhpAttribution.context().utm_source,'google');
c=run('/request-quote');assert.equal(c.window.nhpAttribution.context().landing_page,'/plumber-guildford');
handlers['[data-choice="rejected"]']();assert.equal(session.size,0);assert.equal(c.window.nhpAttribution.accepted(),false);
assert.deepEqual(JSON.parse(JSON.stringify(c.window.nhpAttribution.context())),{landing_page:'/request-quote'});
c=run('/plumber-woking','?utm_source=person@example.invalid');assert.equal(session.size,0);assert.equal(c.window.dataLayer,undefined);
local.set('nhp_analytics_choice_v1','accepted');session.set('nhp_attribution_session_v1',JSON.stringify({capturedAt:Date.now()-25*3600000,context:{landing_page:'/old'}}));
c=run('/','?utm_source=google&utm_term=07700900000&utm_campaign=private@example.invalid');assert.equal(c.window.nhpAttribution.context().landing_page,'/');assert.equal(c.window.nhpAttribution.context().utm_term,undefined);assert.equal(c.window.nhpAttribution.context().utm_campaign,undefined);
const config=c.window.dataLayer.find(x=>x[0]==='config')[2];assert.equal(config.page_location,'https://example.invalid/');assert.equal(config.page_referrer,'');assert.equal(config.campaign_source,'google');
console.log('Revenue attribution: first-entry, multi-hop, withdrawal, minimisation and expiry PASS');
