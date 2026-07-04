#!/usr/bin/env python3
"""Render an authentic, seamlessly-looping Matrix digital-rain video.

Film-accurate details: mirrored half-width katakana + digits, bright
white-green head glyphs, exponential trail fade, per-drop speed/length/depth
(dim distant columns), and in-place glyph shimmer. Output: 3840x1080 @ 30fps
H.264 (played doubled to 7680x2160 — glyphs stay crisp, decode stays cheap).
"""
import os
import random
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 3840, 1080
FPS = 30
LOOP_SECONDS = 48
FADE_FRAMES = 90            # 3s crossfade tail->head makes the loop invisible
WARMUP = 200
CELL = 24
COLS, ROWS = W // CELL, H // CELL
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "matrix_loop.mp4")
FFMPEG = (shutil.which("ffmpeg")
          or os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffmpeg-bin"))
assert FFMPEG and os.path.exists(FFMPEG), "ffmpeg not found — install it first"

random.seed(7)
np.random.seed(7)

# ---- glyph atlas: mirrored katakana etc., rendered once ----
CHARS = [chr(c) for c in range(0xFF66, 0xFF9E)] + list("0123456789") + list("Z=*+-<>¦:.\"")
FONT_CANDIDATES = [
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc", 0),
]
font = None
for path, idx in FONT_CANDIDATES:
    if os.path.exists(path):
        font = ImageFont.truetype(path, int(CELL * 0.95), index=idx)
        break
if font is None:  # any distro: ask fontconfig for a CJK face
    try:
        path = subprocess.check_output(
            ["fc-match", "-f", "%{file}", "Noto Sans CJK JP:bold"]).decode().strip()
        font = ImageFont.truetype(path, int(CELL * 0.95))
    except Exception:
        pass
assert font, "no CJK font found — install a Noto Sans CJK package"

ATLAS = np.zeros((len(CHARS), CELL, CELL), dtype=np.float32)
for i, ch in enumerate(CHARS):
    img = Image.new("L", (CELL, CELL), 0)
    d = ImageDraw.Draw(img)
    d.text((CELL // 2, CELL // 2), ch, fill=255, font=font, anchor="mm")
    img = img.transpose(Image.FLIP_LEFT_RIGHT)   # the film mirrors its glyphs
    ATLAS[i] = np.asarray(img, dtype=np.float32) / 255.0
assert ATLAS.max() > 0.5, "glyph atlas rendered empty"
NCHAR = len(CHARS)

# ---- color LUTs: brightness -> RGB (trail green; heads overlaid whiter) ----
lut_b = np.linspace(0.0, 1.0, 256) ** 1.15
TRAIL_LUT = np.stack([
    (lut_b * 30),            # R: faint
    (lut_b * 255),           # G: the green
    (lut_b * 92),            # B: slight teal cast like the film print
], axis=1).astype(np.uint8)
HEAD_RGB = np.array([200, 255, 200], dtype=np.float32)
BLOOM_STRENGTH = 0.55
BLOOM_TINT = np.array([0.45, 1.0, 0.65], dtype=np.float32)  # green glow

# ---- simulation state ----
bright = np.zeros((ROWS, COLS), dtype=np.float32)   # trail brightness per cell
glyph = np.random.randint(0, NCHAR, size=(ROWS, COLS))
depth = np.ones(COLS, dtype=np.float32)             # per-column depth dimmer


class Drop:
    __slots__ = ("col", "row", "speed", "acc", "trail", "gain", "alive")

    def __init__(self, col):
        self.col = col
        self.row = -random.randint(0, ROWS)          # stagger entry above screen
        self.speed = random.uniform(0.18, 0.55)      # cells per frame
        self.acc = 0.0
        self.trail = random.randint(8, 30)
        self.gain = random.uniform(0.45, 1.0)        # depth: dim = far away
        self.alive = True

    def step(self):
        self.acc += self.speed
        while self.acc >= 1.0:
            self.acc -= 1.0
            self.row += 1
            if 0 <= self.row < ROWS:
                bright[self.row, self.col] = self.gain
                glyph[self.row, self.col] = random.randrange(NCHAR)
        if self.row - self.trail > ROWS:
            self.alive = False


drops = []
COLUMN_DENSITY = 1.0                                 # every column participates
SPAWN_RATE = 0.044                                   # per column per frame
MAX_PER_COL = 2                                      # film runs stacked streams

def spawn():
    percol = {}
    for d in drops:
        percol.setdefault(d.col, []).append(d)
    for c in range(COLS):
        ds = percol.get(c, [])
        if len(ds) >= MAX_PER_COL:
            continue
        # a second stream may enter only after the first head clears its tail,
        # so heads never stack right on top of each other
        if ds and any(d.row <= d.trail for d in ds):
            continue
        if random.random() < SPAWN_RATE * COLUMN_DENSITY:
            drops.append(Drop(c))


def sim_frame():
    global bright
    spawn()
    for d in drops:
        d.step()
    drops[:] = [d for d in drops if d.alive]
    # exponential fade; independent of anyone's refresh rate
    bright *= 0.935
    bright[bright < 0.012] = 0.0
    # in-place shimmer on lit cells
    lit = np.argwhere(bright > 0.05)
    if len(lit):
        pick = lit[np.random.rand(len(lit)) < 0.02]
        for r, c in pick:
            glyph[r, c] = random.randrange(NCHAR)


def compose():
    canvas = np.zeros((H, W), dtype=np.float32)
    headmask = np.zeros((H, W), dtype=np.float32)
    heads = {(d.row, d.col): d.gain for d in drops if 0 <= d.row < ROWS}
    rr, cc = np.nonzero(bright)
    for r, c in zip(rr, cc):
        y, x = r * CELL, c * CELL
        g = ATLAS[glyph[r, c]]
        b = bright[r, c]
        head = heads.get((r, c))
        if head is not None:
            headmask[y:y + CELL, x:x + CELL] = g * head
            canvas[y:y + CELL, x:x + CELL] = g * head
        else:
            canvas[y:y + CELL, x:x + CELL] = g * b
    idx = (np.clip(canvas, 0, 1) * 255).astype(np.uint8)
    rgb = TRAIL_LUT[idx]                              # (H, W, 3)
    hm = headmask[..., None]
    rgb = (rgb.astype(np.float32) * (1 - hm) + HEAD_RGB * hm)
    # bloom: blur the bright cells at quarter res (wide + cheap), then add a
    # green-tinted glow back on top — halos the heads like a phosphor screen
    src = np.clip(canvas * 0.6 + headmask * 1.2, 0.0, 1.0)
    small = (src.reshape(H // 4, 4, W // 4, 4).mean(axis=(1, 3)) * 255).astype(np.uint8)
    glow_img = Image.fromarray(small, "L") \
        .filter(ImageFilter.GaussianBlur(3)) \
        .resize((W, H), Image.BILINEAR)
    glow = np.asarray(glow_img, dtype=np.float32) / 255.0
    rgb += glow[..., None] * (BLOOM_TINT * (255.0 * BLOOM_STRENGTH))
    return np.clip(rgb, 0, 255).astype(np.uint8)


def main():
    nframes = LOOP_SECONDS * FPS
    enc = subprocess.Popen(
        [FFMPEG, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
         "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", OUT],
        stdin=subprocess.PIPE)
    for _ in range(WARMUP):
        sim_frame()
    head_frames = []
    for i in range(nframes):
        sim_frame()
        frame = compose()
        if i < FADE_FRAMES:
            head_frames.append(frame.copy())
        if i >= nframes - FADE_FRAMES:
            t = (i - (nframes - FADE_FRAMES) + 1) / FADE_FRAMES
            frame = (frame.astype(np.float32) * (1 - t)
                     + head_frames[i - (nframes - FADE_FRAMES)].astype(np.float32) * t
                     ).astype(np.uint8)
        enc.stdin.write(frame.tobytes())
        if i % 150 == 0:
            print(f"frame {i}/{nframes}", flush=True)
    enc.stdin.close()
    enc.wait()
    print("ENCODED", OUT, os.path.getsize(OUT) // (1024 * 1024), "MB")


if __name__ == "__main__":
    sys.exit(main())
