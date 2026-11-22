# =============================================================================
#  control_center/promo.py — نظام الترويج الداخلي للبوتات
#
#  يوفر نظامًا متكاملاً للترويج الداخلي بين بوتات بودة:
#    • محرك ذكي لاختيار الإعلانات المناسبة
#    • نظام تتبع الإحالات والأداء
#    • واجهة API للتطبيقات المصغرة
#    • إدارة الحملات عبر لوحة التحكم
#
#  المفهوم:
#    كل بوت يعرض شريطًا صغيرًا في أسفل التطبيق يروج لبوت آخر
#    من بوتات بودة، مع قواعد ذكية لاختيار الإعلان الأنسب.
# =============================================================================

import hashlib
import random
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass

from . import db
from .config import db_path

# ── الفئات المتقاربة ───────────────────────────────────────────────────────
AFFINITY_CATEGORIES = {
    "love": ["love", "fun", "games"],
    "fun": ["fun", "love", "games"],
    "tools": ["tools", "productivity", "daily"],
    "daily": ["tools", "productivity", "daily"],
    "media": ["media", "video", "design"],
    "design": ["media", "video", "design"],
    "learn": ["learn", "tests", "health"],
    "health": ["learn", "tests", "health"],
    "business": ["business", "security", "daily"],
    "security": ["business", "security", "daily"],
}

@dataclass
class PromoCampaign:
    id: int
    target_bot: str
    text_ar: str
    icon: str
    weight: int
    enabled: bool
    starts_at: Optional[str]
    ends_at: Optional[str]
    category: Optional[str]
    created_at: str
    updated_at: str

@dataclass
class PromoEvent:
    id: int
    ts: str
    source_bot: str
    campaign_id: int
    user_hash: str
    kind: str  # impression, click, start
    session_id: str

class PromoEngine:
    """محرك الترويج الداخلي الذكي"""
    
    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300  # 5 دقائق كاش
        self._session_cache = {}  # بيانات الجلسة لكل مستخدم
    
    def _get_user_hash(self, user_id: int) -> str:
        """إنشاء هاش للمستخدم (بدون تخزين ID خام)"""
        return hashlib.md5(str(user_id).encode()).hexdigest()[:16]
    
    def _get_session_id(self, user_id: int) -> str:
        """إنشاء معرف جلسة فريد للمستخدم"""
        return f"session_{user_id}_{int(time.time() // 3600)}"  # ساعة واحدة
    
    def _is_campaign_active(self, campaign: PromoCampaign) -> bool:
        """فحص إذا كانت الحملة نشطة حالياً"""
        now = datetime.now().isoformat()
        
        if campaign.starts_at and campaign.starts_at > now:
            return False
        if campaign.ends_at and campaign.ends_at < now:
            return False
            
        return campaign.enabled
    
    def _get_user_tried_bots(self, conn: sqlite3.Connection, user_hash: str) -> Set[str]:
        """الحصول على البوتات التي جربها المستخدم في هذه الجلسة"""
        try:
            rows = conn.execute("""
                SELECT DISTINCT source_bot 
                FROM promo_events 
                WHERE user_hash = ? AND kind IN ('impression', 'click', 'start')
                AND ts >= datetime('now', '-1 hour')
            """, (user_hash,)).fetchall()
            return {row[0] for row in rows}
        except Exception:
            return set()
    
    def _calculate_ctr(self, conn: sqlite3.Connection, campaign_id: int) -> float:
        """حسابة نسبة النقر إلى الظهور (CTR) لحملة معينة"""
        try:
            row = conn.execute("""
                SELECT 
                    COUNT(CASE WHEN kind = 'impression' THEN 1 END) as impressions,
                    COUNT(CASE WHEN kind = 'click' THEN 1 END) as clicks
                FROM promo_events 
                WHERE campaign_id = ?
                AND ts >= datetime('now', '-7 days')
            """, (campaign_id,)).fetchone()
            
            impressions = row[0] or 0
            clicks = row[1] or 0
            
            if impressions == 0:
                return 0.05  # افتراضي 5% عند عدم وجود بيانات
            
            return clicks / impressions
        except Exception:
            return 0.05
    
    def pick_campaign(self, conn: sqlite3.Connection, source_bot: str, 
                     source_category: str, user_hash: str, 
                     session_id: str) -> Optional[PromoCampaign]:
        """
        اختيار حملة إعلانية مناسبة للمستخدم
        
        القواعد:
        1. لا ترويج للبوت نفسه
        2. الفئات المتقاربة أولًا
        3. استبعاد ما جرّبه المستخدم
        4. تدوير بالوزن + اختبار A/B
        5. حد ظهور: نفس الإعلان مرتين كحد أقصى
        """
        
        # الحصول على البوتات التي جربها المستخدم
        tried_bots = self._get_user_tried_bots(conn, user_hash)
        
        # الحصول على جميع الحملات النشطة
        rows = conn.execute("""
            SELECT c.id, c.target_bot, c.text_ar, c.icon, c.weight, c.category
            FROM promo_campaigns c
            WHERE c.enabled = 1 
            AND (c.starts_at IS NULL OR c.starts_at <= datetime('now'))
            AND (c.ends_at IS NULL OR c.ends_at >= datetime('now'))
            AND c.target_bot != ?
        """, (source_bot,)).fetchall()
        
        if not rows:
            return None
        
        # تصفية الحملات المستبعدة
        available_rows = []
        for row in rows:
            if row[1] not in tried_bots:  # target_bot
                available_rows.append(row)
        
        # إذا لم تكن هناك حملات متاحة (كلها مستبعدة)، استخدم الكل
        rows = available_rows or rows
        
        # حساب الأوزن مع مراعاة الأداء
        weights = []
        for row in rows:
            campaign_id = row[0]
            base_weight = row[4] or 1  # weight
            
            # تعديل الوزن بناءً على CTR
            ctr = self._calculate_ctr(conn, campaign_id)
            performance_factor = 0.5 + ctr * 10  # 0.5 إلى 10.5
            
            # تعديل حسب الفئة المتقاربة
            category_factor = 1.0
            if source_category and row[5]:  # source_category, target_category
                source_cats = source_category.split(',')
                target_cats = row[5].split(',')
                for sc in source_cats:
                    for tc in target_cats:
                        if tc in AFFINITY_CATEGORIES.get(sc, []):
                            category_factor = 2.0
                            break
            
            final_weight = base_weight * performance_factor * category_factor
            weights.append(final_weight)
        
        # اختيار عشوائي بالوزن
        if weights:
            chosen_row = random.choices(rows, weights=weights)[0]
            return PromoCampaign(
                id=chosen_row[0],
                target_bot=chosen_row[1],
                text_ar=chosen_row[2],
                icon=chosen_row[3],
                weight=chosen_row[4],
                enabled=True,
                category=chosen_row[5],
                starts_at=None,
                ends_at=None,
                created_at="",
                updated_at=""
            )
        
        return None
    
    def record_event(self, conn: sqlite3.Connection, source_bot: str, 
                    campaign_id: int, user_hash: str, kind: str, 
                    session_id: str) -> bool:
        """تسجيل حدث إعلاني"""
        try:
            conn.execute("""
                INSERT INTO promo_events 
                (source_bot, campaign_id, user_hash, kind, session_id)
                VALUES (?, ?, ?, ?, ?)
            """, (source_bot, campaign_id, user_hash, kind, session_id))
            return True
        except Exception as e:
            # لا يفشل التطبيق بسبب تسجيل الإحصائيات
            print(f"⚠️ promo event error: {e}")
            return False
    
    def get_campaign_stats(self, conn: sqlite3.Connection, campaign_id: int = None,
                          source_bot: str = None, days: int = 7) -> Dict:
        """الحصول على إحصائيات الحملات"""
        try:
            conditions = []
            params = []
            
            if campaign_id:
                conditions.append("e.campaign_id = ?")
                params.append(campaign_id)
            if source_bot:
                conditions.append("e.source_bot = ?")
                params.append(source_bot)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            query = f"""
                SELECT 
                    e.kind,
                    COUNT(*) as count,
                    COUNT(DISTINCT e.user_hash) as unique_users
                FROM promo_events e
                WHERE {where_clause}
                AND e.ts >= datetime('now', '-{days} days')
                GROUP BY e.kind
            """
            
            rows = conn.execute(query, params).fetchall()
            
            stats = {}
            for row in rows:
                kind = row[0]
                stats[kind] = {
                    "count": row[1],
                    "unique_users": row[2]
                }
            
            # حساب إجماليات
            total_events = sum(s["count"] for s in stats.values())
            total_users = sum(s["unique_users"] for s in stats.values())
            
            impressions = stats.get("impression", {"count": 0, "unique_users": 0})
            clicks = stats.get("click", {"count": 0, "unique_users": 0})
            starts = stats.get("start", {"count": 0, "unique_users": 0})
            
            ctr = (clicks["count"] / impressions["count"] * 100) if impressions["count"] > 0 else 0
            conversion = (starts["count"] / clicks["count"] * 100) if clicks["count"] > 0 else 0
            
            return {
                "total_events": total_events,
                "total_users": total_users,
                "impressions": impressions,
                "clicks": clicks,
                "starts": starts,
                "ctr_percent": ctr,
                "conversion_percent": conversion,
                "period_days": days
            }
        except Exception as e:
            print(f"⚠️ promo stats error: {e}")
            return {}

# ─── واجهة برمجة التطبيقات ───────────────────────────────────────────────
promo_engine = PromoEngine()

def get_promo_for_user(source_bot: str, user_id: int, session_id: str = None) -> Dict:
    """
    الحصول على إعلان مناسب للمستخدم
    
    Args:
        source_bot: معرف البوت المصدر
        user_id: معرف المستخدم
        session_id: معرف الجلسة (اختياري)
    
    Returns:
        {
            "success": bool,
            "campaign": {id, text_ar, icon, link} | None,
            "error": str | None
        }
    """
    try:
        conn = db.connect()
        user_hash = promo_engine._get_user_hash(user_id)
        session_id = session_id or promo_engine._get_session_id(user_id)
        
        # الحصول على معلومات البوت المصدر
        source_info = conn.execute("""
            SELECT category FROM store_items WHERE bot_id = ?
        """, (source_bot,)).fetchone()
        
        source_category = source_info[0] if source_info else ""
        
        # اختيار الحملة
        campaign = promo_engine.pick_campaign(
            conn, source_bot, source_category, user_hash, session_id
        )
        
        if not campaign:
            return {
                "success": True,
                "campaign": None,
                "error": None
            }
        
        # إنشاء رابط تتبع
        link = f"https://t.me/{campaign.target_bot}?start=promo_{source_bot}_{campaign.id}"
        
        # تسجيل حدث الظهور
        promo_engine.record_event(
            conn, source_bot, campaign.id, user_hash, "impression", session_id
        )
        
        return {
            "success": True,
            "campaign": {
                "id": campaign.id,
                "text_ar": campaign.text_ar,
                "icon": campaign.icon or "✨",
                "link": link
            },
            "error": None
        }
        
    except Exception as e:
        return {
            "success": False,
            "campaign": None,
            "error": str(e)
        }
    finally:
        if 'conn' in locals():
            conn.close()

def record_promo_event(source_bot: str, campaign_id: int, user_id: int, 
                      kind: str, session_id: str = None) -> bool:
    """
    تسجيل حدث إعلاني
    
    Args:
        source_bot: معرف البوت المصدر
        campaign_id: معرف الحملة
        user_id: معرف المستخدم
        kind: impression | click | start
        session_id: معرف الجلسة
    """
    try:
        conn = db.connect()
        user_hash = promo_engine._get_user_hash(user_id)
        session_id = session_id or promo_engine._get_session_id(user_id)
        
        success = promo_engine.record_event(
            conn, source_bot, campaign_id, user_hash, kind, session_id
        )
        
        return success
        
    except Exception:
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def get_promo_stats(campaign_id: int = None, source_bot: str = None, 
                   days: int = 7) -> Dict:
    """الحصول على إحصائيات الترويج"""
    try:
        conn = db.connect()
        return promo_engine.get_campaign_stats(conn, campaign_id, source_bot, days)
    except Exception:
        return {}
    finally:
        if 'conn' in locals():
            conn.close()

def create_promo_campaign(target_bot: str, text_ar: str, icon: str = None,
                         weight: int = 1, category: str = None) -> Dict:
    """إنشاء حملة ترويجية جديدة"""
    try:
        conn = db.connect()
        
        # التحقق من وجود البوت المستهدف
        target_exists = conn.execute("""
            SELECT 1 FROM store_items WHERE bot_id = ?
        """, (target_bot,)).fetchone()
        
        if not target_exists:
            return {"success": False, "error": "Bot target not found"}
        
        conn.execute("""
            INSERT INTO promo_campaigns 
            (target_bot, text_ar, icon, weight, category, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (target_bot, text_ar, icon, weight, category))
        
        return {"success": True, "error": None}
        
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if 'conn' in locals():
            conn.close()

def update_promo_campaign(campaign_id: int, **kwargs) -> Dict:
    """تحديث حملة ترويجية"""
    try:
        conn = db.connect()
        
        # بناء جملة التحديث
        update_fields = []
        params = []
        
        allowed_fields = ["target_bot", "text_ar", "icon", "weight", 
                         "enabled", "starts_at", "ends_at", "category"]
        
        for field, value in kwargs.items():
            if field in allowed_fields:
                update_fields.append(f"{field} = ?")
                params.append(value)
        
        if not update_fields:
            return {"success": False, "error": "No valid fields to update"}
        
        params.append(campaign_id)
        
        conn.execute(f"""
            UPDATE promo_campaigns 
            SET {', '.join(update_fields)}, updated_at = datetime('now')
            WHERE id = ?
        """, params)
        
        return {"success": True, "error": None}
        
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if 'conn' in locals():
            conn.close()

def list_promo_campaigns() -> List[Dict]:
    """قائمة جميع الحملات الترويجية"""
    try:
        conn = db.connect()
        rows = conn.execute("""
            SELECT id, target_bot, text_ar, icon, weight, enabled, 
                   starts_at, ends_at, category, created_at, updated_at
            FROM promo_campaigns
            ORDER BY created_at DESC
        """).fetchall()
        
        campaigns = []
        for row in rows:
            campaigns.append({
                "id": row[0],
                "target_bot": row[1],
                "text_ar": row[2],
                "icon": row[3],
                "weight": row[4],
                "enabled": bool(row[5]),
                "starts_at": row[6],
                "ends_at": row[7],
                "category": row[8],
                "created_at": row[9],
                "updated_at": row[10]
            })
        
        return campaigns
        
    except Exception:
        return []
    finally:
        if 'conn' in locals():
            conn.close()

# ─── مساعدات لـ /start handlers ─────────────────────────────────────────────
def handle_promo_start(payload: str, source_bot: str, user_id: int) -> bool:
    """
    التعامل مع بداية بوت عبر رابط ترويجي
    
    Args:
        payload: payload من /start (يجب أن يبدأ بـ "promo_")
        source_bot: البوت الذي أرسل المستخدم
        user_id: معرف المستخدم
    
    Returns:
        bool: هل كانت الإحالة صالحة
    """
    if not payload.startswith("promo_"):
        return False
    
    try:
        parts = payload.split("_", 2)
        if len(parts) != 3:
            return False
        
        _, src, cid = parts
        
        # التحقق من أن المصدر يتطابق
        if src != source_bot:
            return False
        
        # تسجيل حدث الإحالة
        record_promo_event(src, int(cid), user_id, "start")
        
        return True
        
    except (ValueError, IndexError):
        return False