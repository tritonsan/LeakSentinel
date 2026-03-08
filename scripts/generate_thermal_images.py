from __future__ import annotations

from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


OUT = Path("data/thermal/zone-1")
OUT.mkdir(parents=True, exist_ok=True)


def make_frame(has_leak: bool, seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    w, h = 640, 360
    bg = rng.normal(80, 8, size=(h, w)).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(bg, mode="L").convert("RGB")
    d = ImageDraw.Draw(img)

    py = h // 2
    d.rounded_rectangle([40, py - 20, w - 40, py + 20], radius=20, fill=(120, 120, 120))

    if has_leak:
        x0 = int(rng.integers(120, w - 120))
        y0 = py + int(rng.integers(-40, 40))
        blob = Image.new("L", (w, h), 0)
        bd = ImageDraw.Draw(blob)
        r = int(rng.integers(20, 60))
        bd.ellipse([x0 - r, y0 - r, x0 + r, y0 + r], fill=200)
        blob = blob.filter(ImageFilter.GaussianBlur(radius=20))

        arr = np.array(img).astype(np.float32)
        m = np.array(blob).astype(np.float32) / 255.0
        arr[..., 0] = np.clip(arr[..., 0] + 90 * m, 0, 255)
        img = Image.fromarray(arr.astype(np.uint8), "RGB")

    return img


def main() -> None:
    for i in range(5):
        make_frame(False, 100 + i).save(OUT / f"normal_{i:02d}.png")
    for i in range(5):
        make_frame(True, 200 + i).save(OUT / f"leak_{i:02d}.png")
    print(f"Wrote thermal frames to {OUT}")


if __name__ == "__main__":
    main()

