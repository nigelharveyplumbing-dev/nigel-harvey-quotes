import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {randomUUID} from 'node:crypto';

const analytics = fs.readFileSync('static/public_analytics.js', 'utf8');
const quote = fs.readFileSync('templates/request_quote.html', 'utf8').split('<script>').at(-1).split('</script>')[0];

function setup(choice = null, send = false) {
  const handlers = {};
  const banner = {
    hidden: true,
    querySelector(selector) {
      return { addEventListener(_type, cb) { handlers[selector] = cb; }, focus() {} };
    }
  };
  const settings = { addEventListener(_type, cb) { handlers.settings = cb; } };
  const form = { addEventListener(_type, cb) { handlers.submit = cb; }, reset() {} };
  const button = { disabled: false };
  const ok = { style: {}, scrollIntoView() {} };
  const err = { style: {}, textContent: '' };
  const fields = {
    lead_name: 'Synthetic customer', lead_phone: '07000000000',
    lead_description: 'Synthetic test only', lead_email: '', lead_address: '',
    lead_postcode: 'GU1', lead_job_type: 'small', lead_urgency: '',
    lead_preferred_contact: ''
  };
  const links = {
    phone: { href: 'tel:07595725547' },
    whatsapp: { href: 'https://wa.me/447595725547?text=test' },
    quote: { href: '/request-quote' }
  };
  const injected = [];
  const storage = new Map(choice ? [['nhp_analytics_choice_v1', choice]] : []);
  const document = {
    referrer: '',
    cookie: '',
    head: { appendChild(node) { injected.push(node); } },
    body: { contains() { return true; } },
    createElement() { return {}; },
    getElementById(id) {
      return ({
        'public-analytics': { dataset: { measurementId: 'G-Q9Z2WWNF6F', sendToGoogle: String(send) } },
        'analytics-consent': banner, 'analytics-settings': settings,
        leadForm: form, submitButton: button, lead_ok: ok, lead_err: err
      })[id] || { value: fields[id] ?? '' };
    },
    addEventListener(_type, cb) { handlers.click = cb; }
  };
  const location = {
    pathname: '/request-quote', origin: 'https://example.invalid',
    href: 'https://example.invalid/request-quote', hostname: 'example.invalid',
    search: '', reload() { handlers.reloaded = true; }
  };
  const window = { location };
  const context = { document, window, location, localStorage: {
    getItem(key) { return storage.get(key) || null; },
    setItem(key, value) { storage.set(key, value); }
  }, sessionStorage: {getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)}, crypto:{randomUUID}, URL, URLSearchParams, Date, encodeURIComponent,
  fetch: async () => ({ ok: true, json: async () => ({ id: 1 }) }) };
  vm.createContext(context);
  vm.runInContext(analytics, context);
  vm.runInContext(quote, context);
  function click(name) {
    const link = {
      ...links[name], getAttribute() { return this.href; },
      closest() { return this; }
    };
    handlers.click({ target: { closest() { return link; } } });
  }
  async function submit() {
    await handlers.submit({ preventDefault() {} });
  }
  return { context, handlers, banner, button, err, ok, injected, click, submit };
}

{
  const h = setup();
  assert.equal(h.banner.hidden, false);
  h.click('phone');
  assert.equal(h.context.window.dataLayer, undefined);
  h.handlers['[data-choice="rejected"]']();
  h.click('whatsapp');
  assert.equal(h.context.window.dataLayer, undefined);
}
{
  const h = setup(null, false);
  h.handlers['[data-choice="accepted"]']();
  h.click('phone'); h.click('whatsapp'); h.click('quote');
  assert.deepEqual(Array.from(h.context.window.dataLayer, args => args[1]),
                   ['click_phone', 'click_whatsapp', 'click_get_quote']);
  assert.equal(h.injected.length, 0); // staging sends no hits to the live property
  h.context.fetch = async () => ({ ok: false, json: async () => ({ detail: 'Rejected' }) });
  await h.submit();
  assert.equal(h.button.disabled, false);
  assert.equal(h.context.window.dataLayer.length, 3);
  h.context.fetch = async () => ({ ok: true, json: async () => ({ id: 42 }) });
  await h.submit();
  await h.submit();
  assert.equal(h.button.disabled, true);
  assert.equal(h.ok.style.display, 'block');
  assert.deepEqual(Array.from(h.context.window.dataLayer, args => args[1]),
                   ['click_phone', 'click_whatsapp', 'click_get_quote', 'generate_lead']);
}
{
  const h = setup('accepted', true);
  assert.equal(h.injected.length, 1);
  assert.match(h.injected[0].src, /gtag\/js\?id=G-Q9Z2WWNF6F/);
  assert.deepEqual(Array.from(h.context.window.dataLayer, args => args[0]),
                   ['consent', 'js', 'config']);
  h.handlers.settings();
  h.handlers['[data-choice="rejected"]']();
  assert.equal(h.handlers.reloaded, true);
}
console.log('Growth Batch 2 analytics and quote success workflows passed offline');
