"""Build the application ICO from the supplied artwork."""

from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "微信图片_20260324203125_293_65.webp"
OUTPUT = ROOT / "icon.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> None:
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Icon source not found: {SOURCE}")
    with Image.open(SOURCE) as source:
        rgba = source.convert("RGBA")
        square = ImageOps.fit(rgba, (256, 256), method=Image.Resampling.LANCZOS)
        square.save(OUTPUT, format="ICO", sizes=[(size, size) for size in SIZES])
    print(f"Icon generated: {OUTPUT}")


if __name__ == "__main__":
    main()
