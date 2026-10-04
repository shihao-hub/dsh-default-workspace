# -*- coding: utf-8 -*-
"""把所有 SVG 图标排成一张对照表（放大 3 倍），用来逐个核对线条质量与辨识度。"""
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).parent
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
OUT = ROOT / "_sheet.png"

icons = []
for d in sorted((ROOT / "icons").glob("*")):
    for f in sorted(d.glob("*.svg")):
        src = re.sub(r"<!--.*?-->", "", f.read_text(encoding="utf-8"), flags=re.S).strip()
        src = re.sub(r"<\?xml.*?\?>", "", src, flags=re.S).strip()
        src = re.sub(r'\s+(width|height)="[^"]*"', "", src, count=4)
        icons.append((f"{d.name}/{f.stem}", src))

cells = "".join(
    f'<figure><div class="box">{s}</div><figcaption>{k}</figcaption></figure>'
    for k, s in icons)

html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><style>
body{{margin:0;background:#F5EFE1;font-family:"Noto Sans SC",sans-serif;padding:26px}}
h1{{font-size:15px;margin:0 0 16px;color:#5B5346;font-weight:400;letter-spacing:.06em}}
.grid{{display:grid;grid-template-columns:repeat(8,1fr);gap:14px}}
figure{{margin:0;text-align:center}}
.box{{background:#EDE4D0;border:1px solid #D6C9AC;aspect-ratio:1;display:flex;
align-items:center;justify-content:center;padding:9px}}
.box svg{{width:100%;height:100%;display:block}}
figcaption{{font-size:10.5px;color:#8A7E68;margin-top:5px;
font-family:"Cascadia Mono",Consolas,monospace;word-break:break-all}}
</style></head><body><h1>ICON SHEET · {len(icons)} icons</h1>
<div class="grid">{cells}</div></body></html>"""

p = ROOT / "_sheet.html"
p.write_text(html, encoding="utf-8")
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
                "--force-device-scale-factor=1.6", "--window-size=1300,2400",
                "--virtual-time-budget=1500", f"--screenshot={OUT}", p.as_uri()],
               capture_output=True, text=True)
print(f"{len(icons)} icons -> {OUT}")
