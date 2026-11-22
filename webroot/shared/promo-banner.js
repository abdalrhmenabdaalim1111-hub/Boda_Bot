/**
 * Internal Promotion Banner System
 * 
 * شريط إعلاني داخلي يعرض إعلانًا لبوت آخر من بوتات بودة
 * يُحمّل في كل تطبيق مصغّر عبر build_mini_apps.py
 * 
 * الميزات:
 * - اختيار ذكي للإعلان بناءً على الفئة والتاريخ
 * - تتبع كامل للإحالات (impression, click, start)
 * - تصميم يتبع ثيم تيليجرام
 * - قابل للإغلاق من المستخدم
 */

(async function () {
    // ── إعدادات البوت من وسم السكريبت ─────────────────────────────────────
    const script = document.currentScript;
    const BOT_ID = script.dataset.botId || "";
    const USER_ID = script.dataset.userId || "0";
    const SESSION_ID = script.dataset.sessionId || "";
    
    // ── التحقق من البيانات المطلوبة ───────────────────────────────────────
    if (!USER_ID || USER_ID === "0") {
        // محاولة جلبها من Telegram WebApp إذا لم تكن موجودة
        const tg = window.Telegram?.WebApp;
        const tgUser = tg?.initDataUnsafe?.user?.id;
        if (!tgUser) {
            console.log("⚠️ Promo banner: No user ID available");
            return;
        }
    }
    
    const finalUserId = USER_ID !== "0" ? USER_ID : (window.Telegram?.WebApp?.initDataUnsafe?.user?.id || "0");
    
    try {
        // ── جلب الإعلان المناسب ─────────────────────────────────────────────
        const response = await fetch(`/api/promo?bot=${encodeURIComponent(BOT_ID)}&uid=${finalUserId}`);
        
        if (!response.ok) {
            console.log("⚠️ Promo banner: API error", response.status);
            return;
        }
        
        const data = await response.json();
        
        if (!data || !data.campaign) {
            console.log("⚠️ Promo banner: No campaign available");
            return;
        }
        
        const campaign = data.campaign;
        
        // ── إنشاء شريط الإعلان ───────────────────────────────────────────────
        const bar = document.createElement('div');
        bar.id = 'promo-bar';
        bar.innerHTML = `
            <span class="promo-icon">${campaign.icon || '✨'}</span>
            <span class="promo-text">${campaign.text_ar}</span>
            <span class="promo-arrow">›</span>
            <button class="promo-close" aria-label="إغلاق الإعلان">✕</button>
        `;
        
        // ── تنسيقات CSS ─────────────────────────────────────────────────────
        bar.style.cssText = `
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            height: 52px;
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 0 14px;
            padding-bottom: env(safe-area-inset-bottom);
            cursor: pointer;
            z-index: 50;
            background: var(--tg-theme-secondary-bg-color, #1e1e1e);
            color: var(--tg-theme-text-color, #fff);
            border-top: 1px solid rgba(255, 255, 255, 0.08);
            direction: rtl;
            animation: promoIn 0.4s ease;
            box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.3);
        `;
        
        // ── تنسيقات العناصر الداخلية ───────────────────────────────────────
        const icon = bar.querySelector('.promo-icon');
        icon.style.cssText = `
            font-size: 18px;
            flex-shrink: 0;
        `;
        
        const text = bar.querySelector('.promo-text');
        text.style.cssText = `
            flex: 1;
            font-size: 14px;
            font-weight: 500;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        `;
        
        const arrow = bar.querySelector('.promo-arrow');
        arrow.style.cssText = `
            font-size: 16px;
            opacity: 0.7;
            flex-shrink: 0;
        `;
        
        const closeBtn = bar.querySelector('.promo-close');
        closeBtn.style.cssText = `
            width: 24px;
            height: 24px;
            border: none;
            background: rgba(255, 255, 255, 0.1);
            color: inherit;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            flex-shrink: 0;
            transition: background 0.2s;
        `;
        closeBtn.onmouseover = () => closeBtn.style.background = 'rgba(255, 255, 255, 0.2)';
        closeBtn.onmouseout = () => closeBtn.style.background = 'rgba(255, 255, 255, 0.1)';
        
        // ── إضافة البار للصفحة ───────────────────────────────────────────────
        document.body.appendChild(bar);
        document.body.style.paddingBottom = '64px';
        
        // ── تسجيل حدث الظهور ────────────────────────────────────────────────
        logEvent('impression', campaign.id);
        
        // ── التعامل مع النقرات ───────────────────────────────────────────────
        bar.onclick = (e) => {
            // منع النقر على زر الإغلاق
            if (e.target === closeBtn) {
                bar.style.transition = 'transform 0.3s ease, opacity 0.3s ease';
                bar.style.transform = 'translateY(100%)';
                bar.style.opacity = '0';
                setTimeout(() => bar.remove(), 300);
                return;
            }
            
            // فتح رابط البوت
            logEvent('click', campaign.id);
            
            try {
                const tg = window.Telegram?.WebApp;
                if (tg && tg.openTelegramLink) {
                    tg.openTelegramLink(campaign.link);
                } else {
                    window.open(campaign.link, '_blank');
                }
            } catch (err) {
                console.error('⚠️ Promo banner: Failed to open link', err);
            }
        };
        
        // ── إغلاق تلقائي بعد 30 ثانية (اختياري) ────────────────────────────
        setTimeout(() => {
            if (document.getElementById('promo-bar')) {
                bar.style.transition = 'transform 0.3s ease, opacity 0.3s ease';
                bar.style.transform = 'translateY(100%)';
                bar.style.opacity = '0';
                setTimeout(() => bar.remove(), 300);
            }
        }, 30000);
        
    } catch (e) {
        // الفشل صامت: لا يكسر التطبيق
        console.log("⚠️ Promo banner: Initialization error", e);
    }
    
    // ── تسجيل الأحداث ──────────────────────────────────────────────────────
    function logEvent(kind, campaignId) {
        try {
            const payload = JSON.stringify({
                bot: BOT_ID,
                campaign: campaignId,
                kind: kind,
                user_id: finalUserId,
                session_id: SESSION_ID
            });
            
            if (navigator.sendBeacon) {
                navigator.sendBeacon('/api/promo/event', payload);
            } else {
                fetch('/api/promo/event', {
                    method: 'POST',
                    body: payload,
                    headers: { 'Content-Type': 'application/json' }
                });
            }
        } catch (e) {
            console.log("⚠️ Promo banner: Failed to log event", e);
        }
    }
    
    // ── إضافة أنيميشن CSS ─────────────────────────────────────────────────
    const style = document.createElement('style');
    style.textContent = `
        @keyframes promoIn {
            from {
                transform: translateY(100%);
                opacity: 0;
            }
            to {
                transform: translateY(0);
                opacity: 1;
            }
        }
    `;
    document.head.appendChild(style);
    
})();
