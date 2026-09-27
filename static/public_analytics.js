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
    window.gtag('config', id, { allow_google_signals: false, allow_ad_personalization_signals: false });
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
    if (value === 'accepted') start();
    else if (started) {
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
