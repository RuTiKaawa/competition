"""分析设计稿 SVG，提取关键设计参数"""
import re
from collections import Counter

with open('design.svg', 'r', encoding='utf-8') as f:
    svg = f.read()

# Extract colors
fills = re.findall(r'fill=\"(#[0-9A-Fa-f]{3,8})\"', svg)
strokes = re.findall(r'stroke=\"(#[0-9A-Fa-f]{3,8})\"', svg)
color_count = Counter(fills + strokes)
print('=== TOP 30 COLORS ===')
for color, cnt in color_count.most_common(30):
    print(f'  {color}: {cnt}')

# Extract border radius
rxs = re.findall(r'rx=\"(\d+)\"', svg)
rx_count = Counter(rxs)
print('\n=== TOP BORDER RADIUS ===')
for rx, cnt in rx_count.most_common(10):
    print(f'  rx={rx}: {cnt}')

# Extract font sizes
font_sizes = re.findall(r'font-size=\"?(\d+(?:\.\d+)?)', svg)
fs_count = Counter(font_sizes)
print('\n=== TOP FONT SIZES ===')
for fs, cnt in fs_count.most_common(15):
    print(f'  {fs}px: {cnt}')

# Extract text content
texts = re.findall(r'<text[^>]*>([^<]+)</text>', svg)
print('\n=== TEXT CONTENT (first 300 non-empty) ===')
count = 0
for t in texts:
    s = t.strip()
    if s and count < 300:
        print(f'  {s[:100]}')
        count += 1

# Extract rect dimensions for layout analysis
rects = re.findall(r'<rect[^>]*x=\"(\d+)\"[^>]*y=\"(\d+)\"[^>]*width=\"(\d+)\"[^>]*height=\"(\d+)\"[^>]*>', svg)
print('\n=== RECT DIMENSIONS (first 30) ===')
for r in rects[:30]:
    print(f'  x={r[0]} y={r[1]} w={r[2]} h={r[3]}')

# Find any inline SVG icons (small svg tags nested)
icons = re.findall(r'<svg[^>]*width=\"(\d+)\"[^>]*height=\"(\d+)\"[^>]*viewBox[^>]*>', svg[:100000])
print('\n=== ICON DIMENSIONS ===')
for w, h in icons[:20]:
    print(f'  {w}x{h}')
