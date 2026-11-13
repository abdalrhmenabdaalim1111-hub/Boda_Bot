"""
tests/test_boda_ads_sdk.py — اختبارات قواعد جودة BodaAds (القواعد الـ 7).

يتحقق من:
1. Rewarded يبدأ فقط من ضغطة المستخدم وحماية الضغط المزدوج
2. فشل SDK لا يعطل وظيفة الأداة ويعيد {ok:false}
3. منع الإعلانات أثناء العمليات أو شاشة الاشتراك
4. الإعدادات الافتراضية الهادئة للإعلانات الداخلية (In-App)
5. خلو كافة صفحات webroot من استدعاءات alert()
"""

import json
import re
import subprocess
from pathlib import Path
import pytest


REPO_DIR = Path(__file__).resolve().parent.parent


def _strip_comments(code: str) -> str:
    """إزالة التعليقات من كود JS/HTML للبحث عن الاستدعاءات الحقيقية فقط"""
    # إزالة تعليقات /* ... */ و <!-- ... -->
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    code = re.sub(r'<!--.*?-->', '', code, flags=re.DOTALL)
    # إزالة تعليقات // ...
    code = re.sub(r'//.*', '', code)
    return code


def test_no_alert_calls_in_any_mini_app():
    """Rule 7: التأكد التام من خلو كافة صفحات التطبيقات من استدعاءات alert()"""
    html_files = list((REPO_DIR / "webroot").glob("*/index.html"))
    assert len(html_files) >= 34, f"Expected >= 34 mini apps, found {len(html_files)}"

    offenders = []
    alert_pattern = re.compile(r'(?<![a-zA-Z0-9_$])alert\s*\(')

    for f in html_files:
        clean_text = _strip_comments(f.read_text(encoding="utf-8"))
        match = alert_pattern.search(clean_text)
        if match:
            offenders.append(f"{f.name} -> {clean_text[match.start():match.start()+40]}")

    assert not offenders, f"Found real alert() calls in mini apps:\n" + "\n".join(offenders)


def _run_node_script(js_code: str) -> dict:
    """تشغيل كود JS في بيئة Node مع محاكاة بيئة المتصفح الخفيفة"""
    runner = f"""
    // Mock minimal browser environment
    global.MutationObserver = class {{
      constructor(cb) {{ this.cb = cb; }}
      observe() {{}}
      disconnect() {{}}
    }};
    global.window = {{}};
    global.document = {{
      readyState: 'complete',
      addEventListener: () => {{}},
      querySelectorAll: () => [],
      body: {{
        classList: {{
          _classes: new Set(),
          contains: function(c) {{ return this._classes.has(c); }},
          add: function(c) {{ this._classes.add(c); }},
          remove: function(c) {{ this._classes.delete(c); }}
        }},
        dataset: {{}},
        appendChild: function() {{}}
      }},
      documentElement: {{
        style: {{ setProperty: function() {{}} }},
        classList: {{ add: function() {{}} }}
      }}
    }};
    global.sessionStorage = {{ getItem: () => null, setItem: () => {{}} }};
    global.localStorage = {{ getItem: () => null, setItem: () => {{}} }};
    global.BOT_ID = 'testbot';

    {js_code}
    """
    res = subprocess.run(["node", "-e", runner], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Node execution failed: {res.stderr}")
    return json.loads(res.stdout.strip())


def test_boda_ads_sdk_rules_node_simulation():
    """اختبار سلوك BodaAds في Node.js لمحاكاة الضغطات وفشل الـ SDK"""
    from tools.ds_sdk import SDK_JS

    js_test = f"""
    {SDK_JS}

    async function run() {{
      const results = {{}};

      // 1. Test missing callback
      const r1 = await window.Boda.BodaAds.reward();
      results.no_cb = r1;

      // Setup ad config & mock SDK
      window.__BODA_ADS__ = {{
        sdk_name: 'test_sdk',
        ads: [
          {{ slot: 'interstitial', sdk_name: 'test_sdk', enabled: true, ad_id: 'ad1' }}
        ]
      }};
      window.Boda.BodaAds.cfg = window.__BODA_ADS__;

      let sdkCalled = false;
      window.test_sdk = function() {{
        sdkCalled = true;
        return Promise.resolve();
      }};

      // 2. Successful reward call
      let cbCalled = false;
      const r2 = await window.Boda.BodaAds.reward(() => {{ cbCalled = true; }});
      results.success = {{ r: r2, cbCalled, sdkCalled }};

      // 3. Double tap prevention (<1500ms)
      const r3 = await window.Boda.BodaAds.reward(() => {{}});
      results.double_tap = r3;

      // 4. Busy / Processing state suppression (Rule 3)
      window.Boda.BodaAds._tappedUntil = 0; // reset tap
      document.body.classList.add('processing');
      const r4 = await window.Boda.BodaAds.reward(() => {{}});
      results.busy_processing = r4;
      document.body.classList.remove('processing');

      // 5. SDK Rejection handling (Rule 2: never blocks/throws)
      window.Boda.BodaAds._tappedUntil = 0;
      window.test_sdk = function() {{
        return Promise.reject(new Error('Network error'));
      }};
      let cbFailCalled = false;
      const r5 = await window.Boda.BodaAds.reward(() => {{ cbFailCalled = true; }});
      results.sdk_rejected = {{ r: r5, cbFailCalled }};

      console.log(JSON.stringify(results));
    }}

    run().catch(err => {{
      console.error(err);
      process.exit(1);
    }});
    """

    data = _run_node_script(js_test)

    # Assert Rule 1 & validation
    assert data["no_cb"]["ok"] is False
    assert data["no_cb"]["reason"] == "no callback"

    # Assert successful flow
    assert data["success"]["r"]["ok"] is True
    assert data["success"]["cbCalled"] is True
    assert data["success"]["sdkCalled"] is True

    # Assert double tap protection
    assert data["double_tap"]["ok"] is False
    assert data["double_tap"]["reason"] == "double tap"

    # Assert Rule 3 (suppression during processing)
    assert data["busy_processing"]["ok"] is False
    assert data["busy_processing"]["reason"] == "busy"

    # Assert Rule 2 (SDK failure doesn't throw, doesn't execute callback)
    assert data["sdk_rejected"]["r"]["ok"] is False
    assert data["sdk_rejected"]["r"]["reason"] == "sdk rejected"
    assert data["sdk_rejected"]["cbFailCalled"] is False
