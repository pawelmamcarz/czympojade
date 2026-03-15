"""Generuje OG image (1200x630) dla CzymPojade.pl"""
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1200, 630
img = Image.new("RGB", (W, H), "#0f172a")  # dark navy
draw = ImageDraw.Draw(img)

# Gradient overlay
for y in range(H - 120, H):
    alpha = int((y - (H - 120)) / 120 * 40)
    draw.line([(0, y), (W, y)], fill=(15, 23, 42 + alpha))

def get_font(size, bold=False):
    paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

font_huge = get_font(72, bold=True)
font_big = get_font(42)
font_med = get_font(28)
font_small = get_font(22)

# Blue accent line
draw.rectangle([(60, 60), (65, 200)], fill="#3b82f6")

# Main title
draw.text((90, 70), "CzymPojade.pl", fill="#ffffff", font=font_huge)

# Subtitle
draw.text((90, 160), "Kalkulator TCO", fill="#94a3b8", font=font_big)

# Divider
draw.line([(90, 230), (1110, 230)], fill="#334155", width=2)

# Feature bullets — colored dots instead of emoji
features = [
    ("#22c55e", "Porownaj BEV vs ICE vs Hybryda"),
    ("#3b82f6", "Sankey diagram kosztow miesiecznych"),
    ("#f59e0b", "Baza 150+ modeli aut"),
    ("#ef4444", "Strefy Czystego Transportu (SCT)"),
]
y = 260
for color, text in features:
    draw.ellipse([(90, y + 8), (106, y + 24)], fill=color)
    draw.text((120, y), text, fill="#e2e8f0", font=font_med)
    y += 48

# Right side — 3 colored bars (BEV/HYB/ICE comparison visual)
bar_x = 850
draw.rectangle([(bar_x, 270), (bar_x + 250, 300)], fill="#22c55e")
draw.text((bar_x + 10, 273), "BEV  1 850 zl/mies.", fill="#fff", font=font_small)

draw.rectangle([(bar_x, 315), (bar_x + 220, 345)], fill="#3b82f6")
draw.text((bar_x + 10, 318), "HYB  2 100 zl/mies.", fill="#fff", font=font_small)

draw.rectangle([(bar_x, 360), (bar_x + 200, 390)], fill="#f59e0b")
draw.text((bar_x + 10, 363), "ICE   2 650 zl/mies.", fill="#fff", font=font_small)

draw.text((bar_x, 400), "Przykladowe TCO", fill="#64748b", font=font_small)

# Bottom bar
draw.rectangle([(0, H - 70), (W, H)], fill="#1e293b")
draw.text((90, H - 50), "Darmowy kalkulator kosztow posiadania samochodu 2026", fill="#64748b", font=font_small)
draw.text((880, H - 50), "czympojade.pl", fill="#3b82f6", font=get_font(26))

out = "static/og-image.png"
img.save(out, "PNG", quality=95)
print(f"OG image saved: {out} ({os.path.getsize(out):,} bytes)")
