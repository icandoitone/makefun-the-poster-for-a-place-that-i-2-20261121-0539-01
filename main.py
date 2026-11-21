#!/usr/bin/env python3
"""THALVARA — a travel poster for a place that isn't there.

Draws a 1024x1024 travel poster procedurally with only the Python
standard library and writes it to /output/entry.png (or $OUTPUT_PATH).

The invented place: THALVARA, a lagoon island crowned by the Skyglass
Spire — a tall crystal tower that catches the last light of the day
while paper lanterns drift on the water below. No real destination is
depicted; the name is set into the poster in large hand-drawn lettering.
"""

import math
import os
import struct
import zlib

W = H = 1024


# ---------------------------------------------------------------- canvas
class Canvas:
    def __init__(self):
        self.px = bytearray(W * H * 3)

    def _idx(self, x, y):
        return (y * W + x) * 3

    def set(self, x, y, c):
        if 0 <= x < W and 0 <= y < H:
            i = self._idx(x, y)
            self.px[i] = c[0]
            self.px[i + 1] = c[1]
            self.px[i + 2] = c[2]

    def blend(self, x, y, c, a):
        """Blend colour c over the pixel at (x, y) with alpha a (0..255)."""
        if 0 <= x < W and 0 <= y < H and a > 0:
            i = self._idx(x, y)
            inv = 255 - a
            self.px[i] = (c[0] * a + self.px[i] * inv) // 255
            self.px[i + 1] = (c[1] * a + self.px[i + 1] * inv) // 255
            self.px[i + 2] = (c[2] * a + self.px[i + 2] * inv) // 255

    def hline(self, x0, x1, y, c):
        if y < 0 or y >= H:
            return
        x0 = max(0, int(x0))
        x1 = min(W - 1, int(x1))
        if x1 < x0:
            return
        row = bytes(c) * (x1 - x0 + 1)
        i = self._idx(x0, y)
        self.px[i:i + len(row)] = row

    def fill_rect(self, x0, y0, x1, y1, c):
        x0 = max(0, int(x0))
        x1 = min(W - 1, int(x1))
        y0 = max(0, int(y0))
        y1 = min(H - 1, int(y1))
        if x1 < x0 or y1 < y0:
            return
        row = bytes(c) * (x1 - x0 + 1)
        for y in range(y0, y1 + 1):
            i = self._idx(x0, y)
            self.px[i:i + len(row)] = row

    def vgrad(self, y0, y1, stops):
        """Vertical gradient between y0 and y1.

        stops: list of (position 0..1, (r, g, b)) sorted by position.
        """
        for y in range(max(0, y0), min(H, y1 + 1)):
            t = (y - y0) / max(1, (y1 - y0))
            for j in range(len(stops) - 1):
                p0, c0 = stops[j]
                p1, c1 = stops[j + 1]
                if p0 <= t <= p1:
                    f = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
                    c = tuple(
                        int(c0[k] + (c1[k] - c0[k]) * f) for k in range(3)
                    )
                    break
            else:
                c = stops[-1][1]
            row = bytes(c) * W
            i = self._idx(0, y)
            self.px[i:i + len(row)] = row

    def fill_circle(self, cx, cy, r, c):
        r = int(round(r))
        cx = int(round(cx))
        cy = int(round(cy))
        for dy in range(-r, r + 1):
            dx = int(math.sqrt(max(0, r * r - dy * dy)))
            self.hline(cx - dx, cx + dx, cy + dy, c)

    def fill_circle_alpha(self, cx, cy, r, c, a):
        r = int(round(r))
        cx = int(round(cx))
        cy = int(round(cy))
        for dy in range(-r, r + 1):
            dx = int(math.sqrt(max(0, r * r - dy * dy)))
            for x in range(cx - dx, cx + dx + 1):
                self.blend(x, cy + dy, c, a)

    def fill_ellipse(self, cx, cy, rx, ry, c):
        rx = int(round(rx))
        ry = int(round(ry))
        cx = int(round(cx))
        cy = int(round(cy))
        for dy in range(-ry, ry + 1):
            t = 1.0 - (dy * dy) / float(ry * ry)
            dx = int(rx * math.sqrt(max(0.0, t)))
            self.hline(cx - dx, cx + dx, cy + dy, c)

    def fill_ellipse_alpha(self, cx, cy, rx, ry, c, a):
        rx = int(round(rx))
        ry = int(round(ry))
        cx = int(round(cx))
        cy = int(round(cy))
        for dy in range(-ry, ry + 1):
            t = 1.0 - (dy * dy) / float(ry * ry)
            dx = int(rx * math.sqrt(max(0.0, t)))
            for x in range(cx - dx, cx + dx + 1):
                self.blend(x, cy + dy, c, a)

    def fill_poly(self, pts, c):
        ys = [p[1] for p in pts]
        y0 = max(0, int(math.ceil(min(ys))))
        y1 = min(H - 1, int(math.floor(max(ys))))
        n = len(pts)
        for y in range(y0, y1 + 1):
            xs = []
            for i in range(n):
                x1, y1p = pts[i]
                x2, y2p = pts[(i + 1) % n]
                if (y1p <= y < y2p) or (y2p <= y < y1p):
                    t = (y - y1p) / (y2p - y1p)
                    xs.append(x1 + t * (x2 - x1))
            xs.sort()
            for j in range(0, len(xs) - 1, 2):
                self.hline(xs[j], xs[j + 1], y, c)

    def thick_line(self, x1, y1, x2, y2, w, c):
        """A line of width w with round caps, drawn as stamped discs."""
        length = math.hypot(x2 - x1, y2 - y1)
        steps = max(1, int(length / max(1.0, w * 0.45)))
        for i in range(steps + 1):
            t = i / steps
            self.fill_circle(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, w / 2.0, c)


# ------------------------------------------------------------------- font
# Simple stroke capitals on a 5-wide by 7-tall unit grid, y down.
FONT = {
    "T": [((0, 0), (5, 0)), ((2.5, 0), (2.5, 7))],
    "H": [((0, 0), (0, 7)), ((5, 0), (5, 7)), ((0, 3.5), (5, 3.5))],
    "A": [((0, 7), (2.5, 0)), ((5, 7), (2.5, 0)), ((1.25, 4.6), (3.75, 4.6))],
    "L": [((0, 0), (0, 7)), ((0, 7), (5, 7))],
    "V": [((0, 0), (2.5, 7)), ((5, 0), (2.5, 7))],
    "R": [
        ((0, 0), (0, 7)),
        ((0, 0), (3.8, 0)),
        ((3.8, 0), (3.8, 3.5)),
        ((0, 3.5), (3.8, 3.5)),
        ((2.4, 3.5), (5, 7)),
    ],
}


def draw_text(cv, text, x0, y_top, unit, stroke, colour):
    """Draw text with the stroke font; returns the total width in px."""
    x = x0
    for ch in text:
        for (ax, ay), (bx, by) in FONT[ch]:
            cv.thick_line(
                x + ax * unit, y_top + ay * unit,
                x + bx * unit, y_top + by * unit,
                stroke, colour,
            )
        x += 6 * unit
    return x - x0 - unit  # width without the trailing gap


def text_width(text, unit):
    return (len(text) * 6 - 1) * unit


# ------------------------------------------------------------------ scene
SKY = [
    (0.00, (26, 32, 78)),     # deep indigo dusk
    (0.30, (74, 52, 110)),    # violet
    (0.55, (158, 74, 112)),   # rose
    (0.78, (226, 122, 82)),   # warm peach
    (1.00, (250, 184, 104)),  # amber at the horizon
]
SEA = [
    (0.00, (52, 110, 122)),   # teal, lit by the sunset
    (0.45, (34, 82, 100)),
    (1.00, (16, 40, 66)),     # deep lagoon blue
]
HORIZON = 560
BAND_TOP = 830

CREAM = (247, 232, 200)
GOLD = (214, 176, 106)
GOLD_DARK = (146, 108, 52)
NAVY_BAND = (12, 23, 48)


def draw_scene(cv):
    # --- sky ------------------------------------------------------
    cv.vgrad(0, HORIZON, SKY)

    # faint early stars high in the dusk
    for gy in range(20, 240, 4):
        for gx in range(10, W - 10, 4):
            h = (gx * 31 + gy * 57) % 997
            if h < 14:
                a = 60 + (h * 9) % 120
                cv.blend(gx, gy, (255, 244, 214), a)
                if h < 4:
                    cv.blend(gx + 1, gy, (255, 244, 214), a // 2)
                    cv.blend(gx, gy + 1, (255, 244, 214), a // 2)

    # soft evening clouds, warm on their lit undersides: three stacked
    # ellipses each, so the edges feather instead of cutting hard
    for (cx, cy, rx, ry, col, a) in [
        (180, 210, 210, 26, (244, 170, 130), 46),
        (820, 150, 240, 30, (236, 150, 140), 42),
        (700, 330, 260, 24, (250, 190, 140), 50),
        (120, 420, 190, 22, (240, 160, 120), 44),
        (880, 430, 170, 20, (250, 200, 150), 40),
    ]:
        cv.fill_ellipse_alpha(cx, cy, rx, ry, col, a)
        cv.fill_ellipse_alpha(cx, cy + 8, rx * 0.7, ry * 0.7, col, a // 2)
        cv.fill_ellipse_alpha(cx - rx * 0.3, cy - 6, rx * 0.45, ry * 0.6,
                              col, a // 3)

    # --- sun and its glow -----------------------------------------
    # many faint concentric halos so the glow fades smoothly, with no
    # visible rings
    sun_x, sun_y, sun_r = 360, 478, 86
    for r, a in [(290, 5), (262, 6), (234, 7), (208, 9), (184, 11),
                 (162, 13), (142, 16), (124, 20), (108, 26)]:
        cv.fill_circle_alpha(sun_x, sun_y, r, (255, 196, 110), a)
    cv.fill_circle(sun_x, sun_y, sun_r, (255, 226, 160))
    cv.fill_circle(sun_x, sun_y, sun_r - 14, (255, 240, 196))

    # --- sea -------------------------------------------------------
    cv.vgrad(HORIZON, BAND_TOP, SEA)

    # sun's glittering path on the water
    for row in range(HORIZON + 8, BAND_TOP - 6, 6):
        f = (row - HORIZON) / (BAND_TOP - HORIZON)
        half = 26 + f * 95
        for k in range(9):
            h = (row * 131 + k * 733) % 1000
            off = (h / 1000.0) * 2 - 1
            cx = sun_x + off * half
            ln = 8 + (h % 26)
            cv.hline(cx - ln, cx + ln, row, (255, 214, 140))
            cv.hline(cx - ln, cx + ln, row + 1, (255, 214, 140))

    # distant low islands on the horizon
    cv.fill_poly([(30, 560), (150, 528), (260, 548), (330, 560)], (38, 52, 96))
    cv.fill_poly([(760, 560), (850, 540), (930, 552), (1000, 560)], (34, 48, 92))

    # horizon shimmer line
    cv.hline(0, W - 1, HORIZON, (255, 220, 150))
    cv.hline(0, W - 1, HORIZON + 1, (255, 196, 120))

    # --- the Skyglass Spire ---------------------------------------
    tip = (652, 178)
    base_l, base_r = (592, 812), (716, 812)
    # main body: two facets
    cv.fill_poly([base_l, tip, (652, 812)], (168, 214, 228))   # sunlit face
    cv.fill_poly([tip, base_r, (652, 812)], (44, 104, 152))    # shaded face
    # facet bands: thin crystal seams across the spire
    for y, wfrac in [(300, 0.62), (420, 0.72), (540, 0.82), (660, 0.92)]:
        half = (716 - 592) / 2.0 * wfrac / 2.0
        cv.hline(652 - half, 652 + half, y, (30, 80, 122))
        cv.hline(652 - half, 652 + half, y + 1, (210, 235, 245))
    # bright central edge
    cv.thick_line(652, 190, 652, 808, 5, (235, 246, 250))
    # glowing tip star
    cv.fill_circle(tip[0], tip[1], 10, (255, 244, 200))
    cv.thick_line(tip[0] - 26, tip[1], tip[0] + 26, tip[1], 4, (255, 236, 180))
    cv.thick_line(tip[0], tip[1] - 26, tip[0], tip[1] + 26, 4, (255, 236, 180))

    # rocky islets at the spire's foot, with lanterns
    cv.fill_poly([(560, 812), (600, 782), (650, 800), (690, 786), (740, 812)],
                 (20, 34, 62))
    for (lx, ly) in [(588, 776), (664, 772), (712, 780)]:
        cv.fill_circle_alpha(lx, ly, 12, (255, 200, 110), 60)
        cv.fill_circle(lx, ly, 5, (255, 214, 130))
        cv.fill_circle(lx, ly, 2, (255, 244, 210))

    # drifting paper lanterns on the lagoon
    for (lx, ly, s) in [(210, 700, 7), (300, 760, 5), (470, 720, 6),
                         (820, 690, 7), (900, 760, 5), (760, 800, 6)]:
        cv.fill_circle_alpha(lx, ly, s + 8, (255, 190, 100), 55)
        cv.fill_circle(lx, ly, s, (255, 205, 120))
        cv.fill_circle(lx, ly, max(2, s - 3), (255, 240, 200))
        cv.hline(lx - s, lx + s, ly + s + 6, (255, 205, 120))

    # --- foreground headland, lower left ---------------------------
    cv.fill_poly(
        [(0, BAND_TOP), (0, 760), (90, 742), (180, 768), (260, 742),
         (330, 780), (360, BAND_TOP)],
        (13, 26, 54),
    )
    # strange umbrella trees on the headland, canopies lifted so they
    # silhouette against the sea and sky instead of the dark hill
    for (tx, ty, s) in [(70, 736, 46), (150, 730, 56), (235, 738, 42)]:
        cv.thick_line(tx, ty, tx - 4, ty + 62, 7, (13, 26, 54))
        cv.fill_ellipse(tx, ty - 6, s, s * 0.32, (10, 20, 44))
        cv.fill_ellipse(tx, ty - 14, s * 0.7, s * 0.26, (16, 32, 62))

    # --- birds ------------------------------------------------------
    for (bx, by, s) in [(820, 250, 14), (880, 290, 11), (760, 310, 9),
                         (920, 220, 12)]:
        cv.thick_line(bx - s, by, bx, by + s * 0.5, 3, (40, 34, 66))
        cv.thick_line(bx + s, by, bx, by + s * 0.5, 3, (40, 34, 66))

    # --- name band --------------------------------------------------
    cv.fill_rect(0, BAND_TOP, W - 1, H - 1, NAVY_BAND)
    cv.hline(0, W - 1, BAND_TOP, GOLD_DARK)
    cv.hline(0, W - 1, BAND_TOP + 1, GOLD_DARK)

    # gold rules framing the name
    rule_y = 858
    cv.hline(150, 874, rule_y, GOLD)
    cv.hline(150, 874, rule_y + 1, GOLD)
    cv.fill_poly([(880, rule_y - 5), (890, rule_y + 1), (880, rule_y + 7),
                  (870, rule_y + 1)], GOLD)

    # the place name, large and legible, with a soft drop shadow
    name = "THALVARA"
    unit = 17
    tw = text_width(name, unit)
    x0 = (W - tw) // 2
    y_top = 882
    draw_text(cv, name, x0 + 3, y_top + 4, unit, 16, (8, 14, 30))
    draw_text(cv, name, x0, y_top, unit, 16, CREAM)

    # small ornament under the name
    cv.fill_poly([(512, 1012), (520, 1020), (512, 1028), (504, 1020)], GOLD)
    cv.hline(430, 496, 1020, GOLD_DARK)
    cv.hline(528, 594, 1020, GOLD_DARK)


# -------------------------------------------------------------------- png
def write_png(path, cv):
    raw = bytearray()
    stride = W * 3
    for y in range(H):
        row = cv.px[y * stride:(y + 1) * stride]
        raw.append(1)  # Sub filter
        filt = bytearray(stride)
        for i in range(stride):
            left = row[i - 3] if i >= 3 else 0
            filt[i] = (row[i] - left) & 0xFF
        raw += filt
    comp = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", ihdr)
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def main():
    out = os.environ.get("OUTPUT_PATH", "/output/entry.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cv = Canvas()
    draw_scene(cv)
    write_png(out, cv)


if __name__ == "__main__":
    main()
