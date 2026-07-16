import base64
import logging
import httpx
from io import BytesIO
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("sakhi-backend")

def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

def generate_ad_creative(base_image_url: str, product_name: str, price: int) -> Optional[str]:
    """Composites a promotional border, price bubble, and product-name banner
    directly onto the REAL product photo using Pillow. The base photo's pixels
    are never altered or regenerated - this deliberately avoids AI image
    generation, which was producing unrelated/hallucinated product images
    instead of the actual listed item. Returns a base64 data: URL, or None if
    compositing fails (caller falls back to the plain base_image_url)."""
    try:
        img_bytes = httpx.get(base_image_url, timeout=15.0, follow_redirects=True).content
        product_img = Image.open(BytesIO(img_bytes)).convert("RGBA")

        border = 24
        banner_h = 64
        canvas_w = product_img.width + border * 2
        canvas_h = product_img.height + border * 2 + banner_h

        # Meesho jamuni-colored frame; the product photo is pasted in unaltered.
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (159, 32, 137, 255))
        canvas.paste(product_img, (border, border))
        draw = ImageDraw.Draw(canvas)

        # Price bubble, top-right corner
        bubble_text = f"Rs {price}"
        price_font = _load_font(26)
        text_bbox = draw.textbbox((0, 0), bubble_text, font=price_font)
        text_w, text_h = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
        pad = 14
        bubble_x2 = canvas_w - border - 10
        bubble_x1 = bubble_x2 - text_w - pad * 2
        bubble_y1 = border + 10
        bubble_y2 = bubble_y1 + text_h + pad * 2
        draw.rounded_rectangle([bubble_x1, bubble_y1, bubble_x2, bubble_y2], radius=16, fill=(66, 188, 158, 255))
        draw.text((bubble_x1 + pad, bubble_y1 + pad - text_bbox[1]), bubble_text, font=price_font, fill=(255, 255, 255, 255))

        # Bottom banner with product name
        banner_y = border * 2 + product_img.height
        draw.rectangle([0, banner_y, canvas_w, canvas_h], fill=(30, 30, 36, 255))
        name_font = _load_font(22)
        name_bbox = draw.textbbox((0, 0), product_name, font=name_font)
        name_h = name_bbox[3] - name_bbox[1]
        draw.text((border, banner_y + (banner_h - name_h) // 2 - name_bbox[1]), product_name, font=name_font, fill=(255, 255, 255, 255))

        buffer = BytesIO()
        canvas.convert("RGB").save(buffer, format="JPEG", quality=90)
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        logger.warning(f"Ad creative compositing failed, using base product photo instead: {e}")
        return None
