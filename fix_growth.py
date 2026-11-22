from pathlib import Path
p = Path(r"D:\@Boda_Bot\Bots_Folder\growth_engine.py")
s = p.read_text(encoding="utf-8")
old = '"fixed_bot_ids": [],'
new = '"fixed_bot_ids": ["store"],'
if old in s:
    s = s.replace(old, new, 1)
    p.write_text(s, encoding="utf-8")
    print("done")
else:
    print("NOT FOUND")