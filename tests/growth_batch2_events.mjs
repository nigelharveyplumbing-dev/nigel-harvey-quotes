import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

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
  }, URL, URLSearchParams, Date, encodeURIComponent,
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

{
  // Both page families must use the same privacy-aware, first-party attribution script.
  const shared = fs.readFileSync('business/website_contact.py', 'utf8');
  const sharedMatch = shared.match(/QUOTE_ATTRIBUTION_SCRIPT = """(<script>[\s\S]*?<\/script>)"""/);
  const homepage = fs.readFileSync('templates/homepage.html', 'utf8');
  const homepageMatch = homepage.match(/__PUBLIC_ANALYTICS__\s*(<script>[\s\S]*?<\/script>)/);
  assert.ok(sharedMatch && homepageMatch, 'attribution scripts exist');
  assert.equal(sharedMatch[1], homepageMatch[1], 'homepage and other public pages share identical logic');
  const source = sharedMatch[1].replace(/^<script>/, '').replace(/<\/script>$/, '');
  const site = 'https://www.nigelharveyplumbing.co.uk';
  function visit({path, referrer = '', choice = null, query = '', session = new Map()}) {
    const choices = new Map(choice ? [['nhp_analytics_choice_v1', choice]] : []);
    const quoteLink = {href: '/request-quote'};
    const otherLink = {href: '/plumber-woking'};
    const handlers = {};
    const location = {origin: site, pathname: path, search: query, href: site + path + query};
    const document = {
      referrer,
      querySelectorAll() { return [quoteLink]; },
      addEventListener(type, callback) { handlers[type] = callback; }
    };
    vm.runInNewContext(source, {
      document, location, URL, URLSearchParams, Date, Number, Object, JSON,
      localStorage: {getItem(key) { return choices.get(key) || null; }},
      sessionStorage: {
        getItem(key) { return session.get(key) || null; },
        setItem(key, value) { session.set(key, value); },
        removeItem(key) { session.delete(key); }
      }
    });
    return {
      quoteLink, otherLink,
      setChoice(value) { choices.set('nhp_analytics_choice_v1', value); },
      click(link) { handlers.click({target: {closest() { return link; }}}); }
    };
  }
  const consentedSession = new Map();
  const first = visit({
    path: '/plumber-guildford', referrer: 'https://www.google.co.uk/search?q=plumber',
    choice: 'accepted', query: '?utm_source=google&utm_medium=organic',
    session: consentedSession
  });
  const firstUrl = new URL(first.quoteLink.href, site);
  assert.equal(firstUrl.searchParams.get('landing_page'), '/plumber-guildford');
  assert.equal(firstUrl.searchParams.get('referrer'), 'https://www.google.co.uk');
  assert.equal(firstUrl.searchParams.get('utm_medium'), 'organic');
  assert.equal(consentedSession.size, 1);

  const second = visit({
    path: '/leak-repair-guildford', referrer: site + '/plumber-guildford',
    choice: 'accepted', session: consentedSession
  });
  const secondUrl = new URL(second.quoteLink.href, site);
  assert.equal(secondUrl.searchParams.get('landing_page'), '/plumber-guildford');
  assert.equal(secondUrl.searchParams.get('referrer'), 'https://www.google.co.uk');
  assert.equal(secondUrl.searchParams.get('utm_source'), 'google');

  const deniedSession = new Map();
  const denied = visit({
    path: '/plumber-guildford', referrer: 'https://www.google.com/search',
    choice: 'rejected', session: deniedSession
  });
  assert.equal(deniedSession.size, 0, 'declined analytics cannot create session attribution');
  assert.equal(new URL(denied.quoteLink.href, site).searchParams.get('landing_page'),
               '/plumber-guildford');

  const revoked = visit({
    path: '/plumber-woking', choice: 'rejected', session: consentedSession
  });
  assert.equal(consentedSession.size, 0, 'revoking consent discards stored attribution');
  assert.equal(new URL(revoked.quoteLink.href, site).searchParams.get('landing_page'),
               '/plumber-woking');

  const lateSession = new Map();
  const late = visit({
    path: '/plumber-guildford', referrer: 'https://www.google.com/search',
    session: lateSession
  });
  assert.equal(lateSession.size, 0);
  late.setChoice('accepted');
  late.click(late.otherLink);
  assert.equal(JSON.parse(lateSession.get('nhp_quote_origin_v1')).landing_page,
               '/plumber-guildford');

  const stale = new Map([['nhp_quote_origin_v1', JSON.stringify({
    landing_page: '/old', referrer: 'https://example.com', saved_at: Date.now() - 31 * 60 * 1000
  })]]);
  const refreshed = visit({path: '/plumber-woking', choice: 'accepted', session: stale});
  assert.equal(new URL(refreshed.quoteLink.href, site).searchParams.get('landing_page'),
               '/plumber-woking');

  const externalSession = new Map([['nhp_quote_origin_v1', JSON.stringify({
    landing_page: '/plumber-guildford', referrer: 'https://www.google.co.uk',
    saved_at: Date.now()
  })]]);
  const external = visit({
    path: '/plumber-guildford', referrer: 'https://www.bing.com/search',
    choice: 'accepted', session: externalSession
  });
  assert.equal(new URL(external.quoteLink.href, site).searchParams.get('referrer'),
               'https://www.bing.com');
}

console.log('Growth Batch 2 analytics and quote success workflows passed offline');
