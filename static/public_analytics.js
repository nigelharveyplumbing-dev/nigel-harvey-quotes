/* Public pages only. Staging queues events locally and never loads Google's tag. */
(function () {
  'use strict';
  const script = document.getElementById('public-analytics');
  const banner = document.getElementById('analytics-consent');
  const settings = document.getElementById('analytics-settings');
  if (!script || !banner || !settings || location.pathname === '/app') return;

  const id = script.dataset.measurementId;
  const sendToGoogle = script.dataset.sendToGoogle === 'true';
  const storageKey = 'nhp_analytics_choice_v1';
  let choice = null;
  let started = false;
  try { choice = localStorage.getItem(storageKey); } catch (_) {}

  const entryKey = 'nhp_attribution_session_v1';
  const campaignKeys = ['utm_source','utm_medium','utm_campaign','utm_content','utm_term'];
  function currentContext() {
    const params = new URLSearchParams(location.search);
    const context = { landing_page: location.pathname };
    try { const ref = new URL(document.referrer); if (ref.origin !== location.origin) context.referrer = ref.origin; } catch (_) {}
    for (const key of campaignKeys) {
      const value = params.get(key) || '';
      if (/^[A-Za-z][A-Za-z0-9 _.-]{0,79}$/.test(value) && !/\d{7,}|@/.test(value)) context[key] = value;
    }
    return context;
  }
  function clearEntry() { try { sessionStorage.removeItem(entryKey); } catch (_) {} }
  function firstEntry() {
    if (choice !== 'accepted') { clearEntry(); return {landing_page:location.pathname}; }
    let entry;
    try { entry = JSON.parse(sessionStorage.getItem(entryKey)); } catch (_) {}
    if (!entry || !entry.context || Date.now() - entry.capturedAt > 24*60*60*1000 || entry.capturedAt > Date.now()) {
      entry = {capturedAt:Date.now(),context:currentContext()};
      try { sessionStorage.setItem(entryKey,JSON.stringify(entry)); } catch (_) {}
    }
    return entry.context;
  }
  window.nhpAttribution = { context:firstEntry, accepted:()=>choice === 'accepted' };
  firstEntry();

  function start() {
    if (started || choice !== 'accepted') return;
    started = true;
    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
    if (!sendToGoogle) return;
    window.gtag('consent', 'default', {
      analytics_storage: 'granted', ad_storage: 'denied',
      ad_user_data: 'denied', ad_personalization: 'denied'
    });
    window.gtag('js', new Date());
    const context = firstEntry();
    const campaign = {};
    for (const [utm,field] of Object.entries({utm_source:'campaign_source',utm_medium:'campaign_medium',utm_campaign:'campaign_name',utm_content:'campaign_content',utm_term:'campaign_term'})) if (context[utm]) campaign[field] = context[utm];
    window.gtag('config', id, { allow_google_signals: false, allow_ad_personalization_signals: false, page_location: location.origin + location.pathname, page_referrer:context.referrer || '', ...campaign });
    const loader = document.createElement('script');
    loader.async = true;
    loader.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(id);
    document.head.appendChild(loader);
  }

  function track(name) {
    if (choice !== 'accepted') return;
    start();
    window.gtag('event', name, { page_path: location.pathname, send_to: id });
  }
  window.nhpAnalytics = { track: track };

  function forgetCookies() {
    for (const part of document.cookie.split(';')) {
      const name = part.split('=')[0].trim();
      if (!/^_ga(?:_|$)/.test(name)) continue;
      document.cookie = name + '=; Max-Age=0; path=/; SameSite=Lax';
      document.cookie = name + '=; Max-Age=0; path=/; domain=' + location.hostname.replace(/^www\./, '') + '; SameSite=Lax';
    }
  }

  function choose(value) {
    choice = value;
    try { localStorage.setItem(storageKey, value); } catch (_) {}
    banner.hidden = true;
    if (value === 'accepted') { firstEntry(); start(); }
    else { clearEntry(); }
    if (value !== 'accepted' && started) {
      if (sendToGoogle) window.gtag('consent', 'update', { analytics_storage: 'denied' });
      forgetCookies();
      location.reload();
    }
  }

  banner.querySelector('[data-choice="accepted"]').addEventListener('click', function () { choose('accepted'); });
  banner.querySelector('[data-choice="rejected"]').addEventListener('click', function () { choose('rejected'); });
  settings.addEventListener('click', function () { banner.hidden = false; banner.querySelector('button').focus(); });
  if (choice === 'accepted') start();
  else if (choice !== 'rejected') banner.hidden = false;

  document.addEventListener('click', function (event) {
    const link = event.target.closest && event.target.closest('a[href]');
    if (!link || !document.body.contains(link)) return;
    const href = link.getAttribute('href') || '';
    if (/^tel:/i.test(href)) track('click_phone');
    else if (/^https:\/\/wa\.me\//i.test(href)) track('click_whatsapp');
    else if (new URL(link.href, location.href).pathname === '/request-quote') track('click_get_quote');
  });
}());
