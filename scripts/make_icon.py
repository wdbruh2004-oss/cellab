"""Generate the application icon (PNG for Qt, multi-size ICO for Windows) with Pillow."""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def draw(size: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 256
    d.rounded_rectangle([8 * s, 8 * s, 248 * s, 248 * s], radius=52 * s, fill=(14, 20, 40, 255))
    d.ellipse([28 * s, 40 * s, 228 * s, 216 * s], fill=(138, 182, 232, 70), outline=(138, 182, 232, 255),
              width=int(6 * s))
    d.ellipse([86 * s, 88 * s, 164 * s, 160 * s], fill=(123, 92, 196, 255))
    d.ellipse([112 * s, 108 * s, 136 * s, 132 * s], fill=(58, 31, 115, 255))
    for x, y, w, h in ((52, 92, 34, 14), (170, 80, 34, 14), (176, 150, 34, 14), (60, 160, 34, 14),
                       (118, 178, 34, 14), (120, 58, 30, 12)):
        d.rounded_rectangle([x * s, y * s, (x + w) * s, (y + h) * s], radius=7 * s, fill=(228, 87, 46, 255))
    for x, y, c in ((70, 128, (78, 168, 222)), (190, 120, (224, 40, 122)), (150, 196, (123, 201, 80))):
        d.ellipse([x * s - 7 * s, y * s - 7 * s, x * s + 7 * s, y * s + 7 * s], fill=c + (255,))
    return img


if __name__ == "__main__":
    big = draw()
    png = ROOT / "src" / "cellab" / "data" / "icons" / "cellab.png"
    big.resize((256, 256), Image.LANCZOS).save(png)
    big.save(ROOT / "packaging" / "cellab.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                                      (128, 128), (256, 256)])
    print("wrote", png, "and packaging/cellab.ico")
