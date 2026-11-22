from pathlib import Path
p = Path(r"D:\@Boda_Bot\Bots_Folder\growth_engine.py")
s = p.read_text(encoding="utf-8")
old = '    "required_network_bots": [],'
new = '''    "required_network_bots": [
        {
            "id": "store",
            "name": "🏪 متجر تطبيقات بودا",
            "username": "@BodaStoreeBot",
            "url": "https://t.me/BodaStoreeBot"
        },
        {
            "id": "vidload",
            "name": "📥 تحميل الفيديوهات (VidLoad)",
            "username": "@VidLoadXBot",
            "url": "https://t.me/VidLoadXBot"
        },
        {
            "id": "stickerx",
            "name": "🎨 صانع الملصقات (StickerX)",
            "username": "@StickerXMakerBot",
            "url": "https://t.me/StickerXMakerBot"
        },
        {
            "id": "cleantok",
            "name": "🎵 تيك توك بلا علامة (CleanTok)",
            "username": "@CleanTokVidBot",
            "url": "https://t.me/CleanTokVidBot"
        },
        {
            "id": "transbot",
            "name": "🌐 المترجم الفوري (TransBot)",
            "username": "@TransXNowBot",
            "url": "https://t.me/TransXNowBot"
        }
    ],'''
if old in s:
    s = s.replace(old, new, 1)
    p.write_text(s, encoding="utf-8")
    print("done")
else:
    print("NOT FOUND")