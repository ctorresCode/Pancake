import io

from PIL import Image, ImageOps

# Una foto de celular de 50 MP cabe; una "bomba" de 100+ MP que pesa pocos KB no.
MAX_PIXELS = 60_000_000


def open_photo(upload, max_side):
    """Abre la foto sin gastar memoria de más. Lanza ValueError si no sirve."""
    try:
        img = Image.open(upload)
        if img.width * img.height > MAX_PIXELS:
            raise ValueError("too many pixels")
        img.draft("RGB", (max_side * 2, max_side * 2))  # los JPEG grandes se leen ya reducidos
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "P"):  # fondo blanco para PNG transparentes
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, "white")
            bg.paste(img, mask=img.getchannel("A"))
            img = bg
        return img.convert("RGB")
    except (OSError, SyntaxError, Image.DecompressionBombError) as e:
        raise ValueError(str(e)) from e


def to_jpeg(img, quality=82):
    out = io.BytesIO()
    img.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    return out.getvalue()
