"""PDF/PNG -> SVG dönüştürücü.

Kullanım:
    python convert.py dosya.pdf            # her sayfa için dosya_sayfa1.svg ...
    python convert.py gorsel.png           # gorsel.svg (vektörize eder)
    python convert.py klasor/              # klasördeki tüm pdf/png/jpg dosyaları
    python convert.py dosya.pdf --scan     # taranmış PDF'i zorla katmanlı vektörleştir
    python convert.py gorsel.png --smooth=8  # yumuşatma 0-10 (varsayılan 5)

PDF (vektör): PyMuPDF ile kayıpsız (vektörler vektör, yazılar yol olarak korunur).
Taranmış PDF / PNG / JPG: çizgiler ("Cizgiler" grubu) ve boyalar ("Boyalar" grubu)
ayrı katmanlar olarak vtracer ile vektörleştirilir.
"""
import re
import sys
import tempfile
from pathlib import Path

import fitz  # PyMuPDF
import vtracer
from PIL import Image, ImageFilter

LINE_THRESHOLD = 100  # 0-255; bundan koyu pikseller "çizgi" sayılır
RENDER_DPI = 300      # taranmış PDF sayfaları bu çözünürlükte işlenir
SMOOTH = 5            # 0-10; yumuşatma seviyesi (0 = kapalı), --smooth=N ile değişir


def pdf_to_svg(path: Path, out_dir: Path, force_scan: bool = False):
    doc = fitz.open(path)
    for i, page in enumerate(doc, 1):
        name = f"{path.stem}.svg" if len(doc) == 1 else f"{path.stem}_sayfa{i}.svg"
        out = out_dir / name
        if force_scan or is_scanned(page):
            print(f"Sayfa {i}: taranmış görüntü, katmanlı vektörleştirme yapılıyor...")
            with tempfile.TemporaryDirectory() as tmp:
                png = Path(tmp) / "page.png"
                page.get_pixmap(dpi=RENDER_DPI).save(png)
                layered_trace(png, out)
        else:
            # text_as_path=True: fontlar yüklü olmasa da aynı görünür
            svg = page.get_svg_image(text_as_path=True)
            out.write_text(svg, encoding="utf-8")
        print("OK:", out)


def is_scanned(page) -> bool:
    """Sayfada resim var ama vektör çizim ve metin yoksa taranmış kabul edilir."""
    return bool(page.get_images()) and not page.get_drawings() and not page.get_text().strip()


def inner(svg_text: str):
    """(width, height, iç içerik) döndürür."""
    w = re.search(r'width="(\d+)"', svg_text)
    h = re.search(r'height="(\d+)"', svg_text)
    body = re.search(r"<svg[^>]*>(.*)</svg>", svg_text, re.S).group(1)
    return int(w.group(1)), int(h.group(1)), body


def layered_trace(src: Path, out: Path):
    """Görseli 'Boyalar' ve 'Cizgiler' katmanlarına ayırıp tek SVG yapar."""
    img = Image.open(src).convert("RGB")
    orig_w, orig_h = img.size
    s = max(0, min(10, SMOOTH))
    scale = 1
    color_img = img  # boya katmanı özgün boyutta kalır (çizgiler zaten üstünde)
    if s > 0:
        # Yumuşatma: çizgi maskesi büyütülüp bulanıklaştırılır (piksel
        # basamaklarını eritir), sonra eğri parametreleri gevşetilir.
        scale = 2 if s < 7 else 3
        img = img.resize((orig_w * scale, orig_h * scale), Image.LANCZOS)
        img = img.filter(ImageFilter.GaussianBlur(radius=s * 0.25 * scale / 2))
        # Bant/şekil patlamasını önlemek için boyalar sınırlı paletle çıkarılır
        color_img = color_img.quantize(colors=32, method=Image.MEDIANCUT).convert("RGB")
    gray = img.convert("L")
    corner = 60 + s * 8          # yüksek = köşeler yerine eğriler
    length = 4.0 + s * 0.8       # yüksek = daha az, daha uzun segment
    speck_color = 8 + s
    speck_line = 3 + s // 2

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        color_png, line_png = tmp / "c.png", tmp / "l.png"
        color_svg, line_svg = tmp / "c.svg", tmp / "l.svg"

        # Boya katmanı: renkli görsel, orta detay (gürültü azaltılmış)
        color_img.save(color_png)
        vtracer.convert_image_to_svg_py(
            str(color_png), str(color_svg),
            colormode="color", hierarchical="stacked", mode="spline",
            filter_speckle=speck_color, color_precision=6, layer_difference=24,
            corner_threshold=corner, length_threshold=length, splice_threshold=45,
            path_precision=5,
        )

        # Çizgi katmanı: koyu pikseller siyah, gerisi beyaz -> ikili vektörleştirme
        gray.point(lambda p: 0 if p < LINE_THRESHOLD else 255).convert("1").save(line_png)
        vtracer.convert_image_to_svg_py(
            str(line_png), str(line_svg),
            colormode="binary", mode="spline",
            filter_speckle=speck_line, corner_threshold=corner,
            length_threshold=length, splice_threshold=45, path_precision=5,
        )

        cw, ch, color_body = inner(color_svg.read_text(encoding="utf-8"))
        w, h, line_body = inner(line_svg.read_text(encoding="utf-8"))
        if scale != 1:  # boya katmanını çizgi koordinat sistemine ölçekle
            color_body = f'<g transform="scale({scale})">{color_body}</g>'

    # width/height özgün boyut; viewBox büyütülmüş koordinatlara göre
    out.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{orig_w}" height="{orig_h}" '
        f'viewBox="0 0 {w} {h}">\n'
        f'<g id="Boyalar">{color_body}</g>\n'
        f'<g id="Cizgiler">{line_body}</g>\n</svg>\n',
        encoding="utf-8",
    )


def img_to_svg(path: Path, out_dir: Path):
    out = out_dir / f"{path.stem}.svg"
    layered_trace(path, out)
    print("OK:", out)


def main():
    global SMOOTH
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force_scan = "--scan" in sys.argv
    for a in sys.argv[1:]:
        if a.startswith("--smooth="):
            SMOOTH = int(a.split("=", 1)[1])
    if not args:
        print(__doc__)
        return
    target = Path(args[0])
    files = sorted(target.iterdir()) if target.is_dir() else [target]
    for f in files:
        ext = f.suffix.lower()
        if ext == ".pdf":
            pdf_to_svg(f, f.parent, force_scan)
        elif ext in (".png", ".jpg", ".jpeg"):
            img_to_svg(f, f.parent)


if __name__ == "__main__":
    main()
