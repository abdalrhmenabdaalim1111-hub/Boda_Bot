"""
bot_integration.py — نظام التكامل الموحد بين البوتات
يوفر واجهة موحدة للتكامل بين البوتات والمتجر
"""
import logging
from typing import Dict, Optional, List, Callable
from dataclasses import dataclass
from datetime import datetime
import json
import os

logging.basicConfig(
    level=logging.INFO,
    format="[Integration] %(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("Integration")

@dataclass
class BotInfo:
    """معلومات البوت"""
    id: str
    name: str
    emoji: str
    description: str
    short_desc: str
    url: str
    username: str
    tag: str
    hidden: bool = False
    webapp_url: Optional[str] = None

class BotIntegration:
    """نظام التكامل الرئيسي"""

    def __init__(self, registry_path: str = "../bots_registry.json"):
        """
        تهيئة نظام التكامل

        Args:
            registry_path: مسار ملف السجل
        """
        self.registry_path = registry_path
        self.bots: Dict[str, BotInfo] = {}
        self.store_url = "https://t.me/BodaStoreeBot"
        self._load_registry()

    def _load_registry(self):
        """تحميل سجل البوتات"""
        try:
            abs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), self.registry_path))
            if os.path.exists(abs_path):
                with open(abs_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for bot_data in data:
                        bot = BotInfo(
                            id=bot_data['id'],
                            name=bot_data['name'],
                            emoji=bot_data['emoji'],
                            description=bot_data['description'],
                            short_desc=bot_data['short_desc'],
                            url=bot_data['url'],
                            username=bot_data['username'],
                            tag=bot_data['tag'],
                            hidden=bot_data.get('hidden', False)
                        )
                        self.bots[bot.id] = bot
                logger.info(f"تم تحميل {len(self.bots)} بوت من السجل")
        except Exception as e:
            logger.error(f"خطأ في تحميل السجل: {e}")

    def _save_registry(self):
        """حفظ سجل البوتات"""
        try:
            abs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), self.registry_path))
            data = []
            for bot in self.bots.values():
                bot_data = {
                    'id': bot.id,
                    'emoji': bot.emoji,
                    'name': bot.name,
                    'description': bot.description,
                    'short_desc': bot.short_desc,
                    'url': bot.url,
                    'username': bot.username,
                    'tag': bot.tag,
                    'hidden': bot.hidden
                }
                data.append(bot_data)

            with open(abs_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("تم حفظ السجل")
        except Exception as e:
            logger.error(f"خطأ في حفظ السجل: {e}")

    def register_bot(
        self,
        bot_id: str,
        name: str,
        emoji: str,
        description: str,
        short_desc: str,
        url: str,
        username: str,
        tag: str,
        hidden: bool = False,
        webapp_url: Optional[str] = None
    ) -> BotInfo:
        """
        تسجيل بوت جديد

        Args:
            bot_id: معرف البوت
            name: اسم البوت
            emoji: إيموجي البوت
            description: وصف البوت
            short_desc: وصف قصير
            url: رابط البوت
            username: اسم المستخدم
            tag: التصنيف
            hidden: مخفي في المتجر
            webapp_url: رابط التطبيق

        Returns:
            معلومات البوت المسجل
        """
        bot = BotInfo(
            id=bot_id,
            name=name,
            emoji=emoji,
            description=description,
            short_desc=short_desc,
            url=url,
            username=username,
            tag=tag,
            hidden=hidden,
            webapp_url=webapp_url
        )

        self.bots[bot_id] = bot
        self._save_registry()
        logger.info(f"تم تسجيل البوت: {name}")
        return bot

    def get_bot(self, bot_id: str) -> Optional[BotInfo]:
        """
        الحصول على معلومات البوت

        Args:
            bot_id: معرف البوت

        Returns:
            معلومات البوت أو None
        """
        return self.bots.get(bot_id)

    def get_all_bots(self, include_hidden: bool = False) -> List[BotInfo]:
        """
        الحصول على جميع البوتات

        Args:
            include_hidden: تضمين البوتات المخفية

        Returns:
            قائمة البوتات
        """
        bots = list(self.bots.values())
        if not include_hidden:
            bots = [b for b in bots if not b.hidden]
        return bots

    def update_bot(
        self,
        bot_id: str,
        name: Optional[str] = None,
        emoji: Optional[str] = None,
        description: Optional[str] = None,
        short_desc: Optional[str] = None,
        url: Optional[str] = None,
        username: Optional[str] = None,
        tag: Optional[str] = None,
        hidden: Optional[bool] = None,
        webapp_url: Optional[str] = None
    ) -> Optional[BotInfo]:
        """
        تحديث معلومات البوت

        Args:
            bot_id: معرف البوت
            name: اسم البوت الجديد
            emoji: إيموجي البوت الجديد
            description: وصف البوت الجديد
            short_desc: وصف قصير جديد
            url: رابط البوت الجديد
            username: اسم المستخدم الجديد
            tag: التصنيف الجديد
            hidden: مخفي في المتجر
            webapp_url: رابط التطبيق الجديد

        Returns:
            معلومات البوت المحدث أو None
        """
        bot = self.bots.get(bot_id)
        if not bot:
            return None

        if name is not None:
            bot.name = name
        if emoji is not None:
            bot.emoji = emoji
        if description is not None:
            bot.description = description
        if short_desc is not None:
            bot.short_desc = short_desc
        if url is not None:
            bot.url = url
        if username is not None:
            bot.username = username
        if tag is not None:
            bot.tag = tag
        if hidden is not None:
            bot.hidden = hidden
        if webapp_url is not None:
            bot.webapp_url = webapp_url

        self._save_registry()
        logger.info(f"تم تحديث البوت: {bot.name}")
        return bot

    def delete_bot(self, bot_id: str) -> bool:
        """
        حذف بوت من السجل

        Args:
            bot_id: معرف البوت

        Returns:
            True إذا تم الحذف بنجاح
        """
        if bot_id in self.bots:
            del self.bots[bot_id]
            self._save_registry()
            logger.info(f"تم حذف البوت: {bot_id}")
            return True
        return False

    def get_store_url(self) -> str:
        """
        الحصول على رابط المتجر

        Returns:
            رابط المتجر
        """
        return self.store_url

    def set_store_url(self, url: str):
        """
        تعيين رابط المتجر

        Args:
            url: رابط المتجر الجديد
        """
        self.store_url = url
        logger.info(f"تم تحديث رابط المتجر: {url}")

    def get_bots_by_tag(self, tag: str) -> List[BotInfo]:
        """
        الحصول على البوتات حسب التصنيف

        Args:
            tag: التصنيف

        Returns:
            قائمة البوتات
        """
        return [b for b in self.bots.values() if b.tag == tag and not b.hidden]

    def get_tags(self) -> List[str]:
        """
        الحصول على جميع التصنيفات

        Returns:
            قائمة التصنيفات
        """
        tags = set(b.tag for b in self.bots.values() if not b.hidden)
        return sorted(list(tags))

    def search_bots(self, query: str) -> List[BotInfo]:
        """
        البحث في البوتات

        Args:
            query: نص البحث

        Returns:
            قائمة البوتات المطابقة
        """
        query = query.lower()
        results = []
        for bot in self.bots.values():
            if bot.hidden:
                continue
            if (query in bot.name.lower() or
                query in bot.description.lower() or
                query in bot.short_desc.lower() or
                query in bot.tag.lower()):
                results.append(bot)
        return results

    def get_summary(self) -> Dict:
        """
        الحصول على ملخص البوتات

        Returns:
            قاموس يحتوي على ملخص البوتات
        """
        total = len(self.bots)
        visible = len([b for b in self.bots.values() if not b.hidden])
        hidden = total - visible

        tags = self.get_tags()
        by_tag = {tag: len(self.get_bots_by_tag(tag)) for tag in tags}

        return {
            "total": total,
            "visible": visible,
            "hidden": hidden,
            "tags": tags,
            "by_tag": by_tag
        }
