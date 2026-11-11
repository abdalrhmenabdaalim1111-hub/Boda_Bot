# -*- coding: utf-8 -*-
"""
tools/ds_sdk.py — طبقة Telegram Mini App + الإعلانات + التتبع

تُدمج في كل تطبيق مصغّر عبر ``app_template.py``. المبادئ:
  • لا توكن ولا أسرار هنا — ``initData`` فقط ويُتحقق منه على السيرفر.
  • تجربة أصلية: MainButton / BackButton / Haptic / CloudStorage / expand.
  • الإعلانات: بانر ثابت أسفل الشاشة + بيني بعد اكتمال النتيجة فقط.
  • كل شيء best-effort: أي فشل في تيليجرام لا يعطّل التطبيق.
"""

SDK_JS = r"""
/* ═════════ Boda MiniApp SDK v2 ═════════
   Telegram-native + Design System + Ads placement
   لا يحتوي أي توكن — التكامل عبر Telegram.WebApp الرسمي فقط. */
(function () {
  'use strict';

  var API_BASE = window.__BODA_API__ || '';
  var BOT_ID   = window.__BODA_BOT_ID__ || 'unknown';
  var SHARE    = window.__BODA_SHARE__ || 'https://t.me/BodaStoreeBot';
  var tg       = (window.Telegram && window.Telegram.WebApp) || null;

  /* ── تهيئة تيليجرام والثيم ── */
  function applyTheme() {
    if (!tg || !tg.themeParams) return;
    var p = tg.themeParams, r = document.documentElement.style;
    if (p.bg_color)            r.setProperty('--tg-theme-bg-color', p.bg_color);
    if (p.secondary_bg_color)  r.setProperty('--tg-theme-secondary-bg-color', p.secondary_bg_color);
    if (p.text_color)          r.setProperty('--tg-theme-text-color', p.text_color);
    if (p.hint_color)          r.setProperty('--tg-theme-hint-color', p.hint_color);
    if (p.link_color)          r.setProperty('--tg-theme-link-color', p.link_color);
    if (p.button_color)        r.setProperty('--tg-theme-button-color', p.button_color);
    if (p.button_text_color)   r.setProperty('--tg-theme-button-text-color', p.button_text_color);
    var scheme = tg.colorScheme === 'light' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', scheme);
    document.documentElement.style.colorScheme = scheme;
  }

  function initTelegram() {
    if (!tg) return;
    try {
      tg.ready();
      tg.expand();
      if (tg.setHeaderColor) tg.setHeaderColor('secondary_bg_color');
      if (tg.setBackgroundColor) tg.setBackgroundColor('secondary_bg_color');
      if (tg.onEvent) tg.onEvent('themeChanged', applyTheme);
      applyTheme();
    } catch (e) {}
  }

  /* ── المستخدم (بيانات عرض فقط — لا تُستخدم للتحقق) ── */
  function getUser() {
    try {
      var u = tg && tg.initDataUnsafe && tg.initDataUnsafe.user;
      if (!u) return null;
      return { id: u.id, name: [u.first_name, u.last_name].filter(Boolean).join(' ') };
    } catch (e) { return null; }
  }

  function initData() { try { return (tg && tg.initData) || ''; } catch (e) { return ''; } }

  /* بيئة تيليجرام الحقيقية فقط — مكتبة telegram-web-app.js تُحمّل حتى خارج تيليجرام */
  function isTelegram() {
    try {
      if (!tg) return false;
      if (tg.initData) return true;
      if (tg.initDataUnsafe && tg.initDataUnsafe.user) return true;
      return !!(tg.platform && tg.platform !== 'unknown');
    } catch (e) { return false; }
  }

  /* ── التتبع (best-effort، لا يعطّل الواجهة) ── */
  function track(event, extra) {
    try {
      var u = getUser();
      var payload = Object.assign({
        bot: BOT_ID, event: event, user_id: u ? u.id : 0
      }, extra || {});
      var raw = initData();
      if (raw) payload.init_data = raw;
      if (API_BASE) {
        fetch(API_BASE + '/api/track', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        }).catch(function () {});
      }
      try {
        var k = 'boda_events';
        var arr = JSON.parse(localStorage.getItem(k) || '[]');
        arr.push(Object.assign({ t: Date.now() }, payload));
        localStorage.setItem(k, JSON.stringify(arr.slice(-50)));
      } catch (e) {}
    } catch (e) {}
  }

  /* ── نداء API مع initData (للعمليات الحساسة لاحقاً) ── */
  function api(path, body) {
    var payload = Object.assign({}, body || {});
    var raw = initData();
    if (raw) payload.init_data = raw;
    return fetch((API_BASE || '') + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (r) { return r.json(); });
  }

  /* ── اهتزاز ── */
  function haptic(kind) {
    try {
      if (!tg || !tg.HapticFeedback) return;
      if (kind === 'success' || kind === 'error' || kind === 'warning') {
        tg.HapticFeedback.notificationOccurred(kind);
      } else if (kind === 'select') {
        tg.HapticFeedback.selectionChanged();
      } else {
        tg.HapticFeedback.impactOccurred(kind || 'light');
      }
    } catch (e) {}
  }

  /* ── توست ── */
  function toast(msg) {
    var t = document.getElementById('toast');
    if (!t) { t = document.createElement('div'); t.id = 'toast'; document.body.appendChild(t); }
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(t._h);
    t._h = setTimeout(function () { t.classList.remove('show'); }, 2300);
  }

  /* ── نسخ ── */
  function copy(text, okMsg) {
    function done() { toast(okMsg || '✅ تم النسخ'); haptic('success'); }
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); } catch (e) {}
      ta.remove();
      done();
    }
    if (navigator.clipboard) navigator.clipboard.writeText(text).then(done).catch(fallback);
    else fallback();
  }

  /* ── مشاركة ── */
  function share(text, url) {
    var link = url || SHARE;
    var full = text + '\n\n' + link;
    try {
      if (tg && tg.openTelegramLink) {
        tg.openTelegramLink('https://t.me/share/url?url=' +
          encodeURIComponent(link) + '&text=' + encodeURIComponent(text));
      } else if (navigator.share) {
        navigator.share({ text: full });
      } else {
        copy(full, '📋 انسخه وشاركه');
        return;
      }
    } catch (e) { copy(full, '📋 انسخه وشاركه'); }
    track('share');
  }

  /* ── MainButton / BackButton أصليّان ── */
  var mainCb = null;
  var MainButton = {
    set: function (text, onClick) {
      if (!tg || !tg.MainButton || !isTelegram()) return false;
      try {
        tg.MainButton.setText(text || '');
        /* إزالة المستمع السابق حتى لا تتراكم الأفعال عند تغيير النص */
        if (mainCb && tg.MainButton.offClick) {
          try { tg.MainButton.offClick(mainCb); } catch (e) {}
        }
        mainCb = onClick || function () {};
        tg.MainButton.onClick(mainCb);
        tg.MainButton.show();
        return true;
      } catch (e) { return false; }
    },
    hide: function () { try { tg.MainButton.hide(); } catch (e) {} },
    progress: function (on) {
      if (!isTelegram()) return;
      try { on ? tg.MainButton.showProgress(true) : tg.MainButton.hideProgress(); }
      catch (e) {}
    },
    disable: function (on) {
      if (!isTelegram()) return;
      try { on ? tg.MainButton.disable() : tg.MainButton.enable(); } catch (e) {}
    }
  };

  var BackButton = {
    show: function (onClick) {
      if (!tg || !tg.BackButton || !isTelegram()) return false;
      try {
        tg.BackButton.onClick(onClick || function () { tg.close(); });
        tg.BackButton.show();
        return true;
      } catch (e) { return false; }
    },
    hide: function () { try { tg.BackButton.hide(); } catch (e) {} }
  };

  /* ── CloudStorage مع بديل محلي ── */
  var Cloud = {
    get: function (key) {
      return new Promise(function (resolve) {
        if (tg && tg.CloudStorage) {
          tg.CloudStorage.getItem(key, function (err, val) {
            if (!err && val) resolve(val);
            else resolve(localStorage.getItem('boda_cloud_' + key));
          });
        } else resolve(localStorage.getItem('boda_cloud_' + key));
      });
    },
    set: function (key, value) {
      return new Promise(function (resolve) {
        try { localStorage.setItem('boda_cloud_' + key, String(value)); } catch (e) {}
        if (tg && tg.CloudStorage) {
          tg.CloudStorage.setItem(key, String(value), function () { resolve(true); });
        } else resolve(true);
      });
    }
  };

  /* ═════════ الإعلانات ═════════ */
  var Ad = {
    cfg: window.__BODA_ADS__ || { banner: null, sponsor: null, every: 3 },
    _lastInterstitial: 0,

    /** بانر ثابت أسفل الشاشة — يُغلق مؤقتاً في هذه الجلسة */
    mountBanner: function () {
      var b = this.cfg.banner;
      if (!b || !b.html) return;
      try { if (sessionStorage.getItem('boda_banner_closed') === '1') return; } catch (e) {}

      var el = document.createElement('div');
      el.className = 'ad-banner';
      el.setAttribute('role', 'complementary');
      el.setAttribute('aria-label', 'محتوى برعاية');
      el.innerHTML =
        '<span class="ad-icon">' + (b.icon || '📢') + '</span>' +
        '<div class="ad-text">' + b.html +
        '<span class="ad-label">AD</span></div>' +
        '<button class="ad-close" type="button" aria-label="إغلاق الإعلان">✕</button>';

      document.body.appendChild(el);

      function show() {
        el.classList.add('show');
        var h = el.offsetHeight || 52;
        document.documentElement.style.setProperty('--bd-banner-h', h + 'px');
        track('ad_view', { placement: 'banner', format: 'fixed_bottom' });
      }
      setTimeout(show, 700);

      el.querySelectorAll('a').forEach(function (a) {
        a.addEventListener('click', function () {
          track('ad_click', { placement: 'banner' });
          haptic('light');
        });
      });
      el.querySelector('.ad-close').addEventListener('click', function () {
        el.remove();
        document.documentElement.style.setProperty('--bd-banner-h', '0px');
        try { sessionStorage.setItem('boda_banner_closed', '1'); } catch (e) {}
      });
    },

    /** يُستدعى بعد اكتمال النتيجة فقط — ليس أثناء العملية */
    afterResult: function () {
      var s = this.cfg.sponsor;
      if (!s) return;
      var every = Math.max(1, parseInt(this.cfg.every || 3, 10));
      var n = 0;
      try {
        n = (parseInt(localStorage.getItem('boda_results_' + BOT_ID) || '0', 10) || 0) + 1;
        localStorage.setItem('boda_results_' + BOT_ID, n);
      } catch (e) { n = 1; }
      if (n % every !== 0) return;
      if (Date.now() - this._lastInterstitial < 90000) return;
      this._lastInterstitial = Date.now();
      this.showInterstitial(s);
    },

    showInterstitial: function (s) {
      var old = document.getElementById('sponsor-overlay');
      if (old) old.remove();
      var ov = document.createElement('div');
      ov.id = 'sponsor-overlay';
      ov.setAttribute('role', 'dialog');
      ov.setAttribute('aria-modal', 'true');
      ov.innerHTML =
        '<div class="sponsor-card">' +
        '<span class="sp-badge">✦ SPONSORED</span>' +
        '<h3></h3><p></p>' +
        '<button class="btn" id="sp-go" type="button"></button>' +
        '<button class="skip" type="button" disabled></button>' +
        '</div>';
      ov.querySelector('h3').textContent = s.title || '';
      ov.querySelector('p').textContent = s.text || '';
      ov.querySelector('#sp-go').textContent = (s.button || 'زيارة الراعي') + ' ↗';
      document.body.appendChild(ov);
      requestAnimationFrame(function () { ov.classList.add('show'); });
      haptic('light');
      track('ad_view', { placement: 'interstitial', format: 'after_result' });

      function close() {
        ov.classList.remove('show');
        setTimeout(function () { ov.remove(); }, 240);
      }
      ov.querySelector('#sp-go').addEventListener('click', function () {
        track('ad_click', { placement: 'interstitial' });
        haptic('success');
        try {
          if (tg && tg.openLink) tg.openLink(s.url);
          else window.open(s.url, '_blank');
        } catch (e) {}
        close();
      });

      var skip = ov.querySelector('.skip');
      var left = 3;
      skip.textContent = 'يمكنك المتابعة بعد ' + left + '…';
      var timer = setInterval(function () {
        left -= 1;
        if (left <= 0) {
          clearInterval(timer);
          skip.disabled = false;
          skip.textContent = 'متابعة للتطبيق ←';
        } else {
          skip.textContent = 'يمكنك المتابعة بعد ' + left + '…';
        }
      }, 1000);
      skip.addEventListener('click', function () {
        if (!skip.disabled) { clearInterval(timer); close(); }
      });
    },

    /* توافق خلفي: لم يعد يظهر عند فتح التطبيق */
    maybeSponsor: function () { /* intentionally no-op */ }
  };

  /* ── رصد اكتمال النتائج تلقائياً في كل التطبيقات ── */
  function observeResults() {
    function onShown(el) {
      if (el._bodaCounted) return;
      el._bodaCounted = true;
      Ad.afterResult();
    }
    function scan(root) {
      var nodes = [];
      if (root.nodeType === 1 && root.classList && root.classList.contains('result')) {
        nodes.push(root);
      }
      if (root.querySelectorAll) {
        root.querySelectorAll('.result').forEach(function (el) { nodes.push(el); });
      }
      nodes.forEach(function (el) {
        if (el._bodaObserved) return;
        el._bodaObserved = true;
        if (el.classList.contains('show')) onShown(el);
        new MutationObserver(function (muts) {
          muts.forEach(function (m) {
            if (m.target.classList && m.target.classList.contains('show')) onShown(m.target);
          });
        }).observe(el, { attributes: true, attributeFilter: ['class'] });
      });
    }
    scan(document);
    new MutationObserver(function (muts) {
      muts.forEach(function (m) {
        m.addedNodes.forEach(function (n) {
          if (n.nodeType === 1) scan(n);
        });
      });
    }).observe(document.body, { childList: true, subtree: true });
  }

  /* ── تشغيل ── */
  function boot() {
    initTelegram();
    Ad.mountBanner();
    observeResults();
    track('app_open');
    document.documentElement.classList.add('boda-ready');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
    else fn();
  }

  window.Boda = {
    track: track, api: api, toast: toast, haptic: haptic, copy: copy, share: share,
    getUser: getUser, initData: initData, ready: ready, tg: tg,
    isTelegram: isTelegram,
    MainButton: MainButton, BackButton: BackButton, Cloud: Cloud, Ad: Ad
  };
})();
"""
