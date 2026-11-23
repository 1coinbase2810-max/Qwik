"""Generate logo.png (96x96) from the user's 1logo.svg mark:
red disc (#E8442E), white inner ring, white magnifier on top. No SVG renderer
on this box, so the center badge is redrawn 1:1 with Pillow."""
import math
import os
from PIL import Image, ImageDraw

S = 96
BASE = os.path.dirname(os.path.abspath(__file__))
RED = (232, 68, 46, 255)
WHITE = (255, 255, 255, 255)

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
cx = cy = S / 2

d.ellipse([cx - 44, cy - 44, cx + 44, cy + 44], fill=RED)
d.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], outline=WHITE, width=4)

# magnifier: ring radius 21, stroke 7, handle at 45 deg
r, w, hr, hw = 21, 7, 12, 6
d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=RED, width=w)
d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=WHITE, width=w)
ux, uy = math.cos(math.radians(45)), math.sin(math.radians(45))
x0, y0 = cx + ux * (r - 2), cy + uy * (r - 2)
x1, y1 = cx + ux * (r + hr), cy + uy * (r + hr)
d.line([x0, y0, x1, y1], fill=RED, width=w + 3, joint="curve")
d.line([x0, y0, x1, y1], fill=WHITE, width=hw, joint="curve")

out = os.path.join(BASE, "logo.png")
img.save(out)
print("wrote", out)
