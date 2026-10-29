#!/usr/bin/env python3
from moviepy.video.VideoClip import TextClip
import moviepy.config as mpconfig
from config_manager import CONFIG

def create_text_clip(text, style_config=None):
    """
    Create a TextClip using settings from CONFIG.
    If style_config is provided (e.g., for a specific style like gaming),
    it must contain 'font', 'align', 'margin' keys.
    Otherwise, uses top-level CONFIG.
    """
    if not text or not text.strip():
        return None

    # Use style_config if given, otherwise fallback to global CONFIG
    cfg = style_config if style_config is not None else CONFIG

    font_cfg = cfg["font"]
    font = font_cfg["path"]
    color = font_cfg["color"]
    stroke_color = font_cfg["stroke_color"]
    stroke_width = font_cfg["stroke_width"]
    font_size = font_cfg["size"]
    align = cfg["align"]
    margin = cfg["margin"]

    if isinstance(margin, list):
        margin = tuple(margin)

    # Use ImageMagick if available
    if mpconfig.IMAGEMAGICK_BINARY is not None:
        try:
            actual_margin = margin if margin != (0, 0, 0, 0) else None
            clip = TextClip(
                text=text,
                font=font,
                color=color,
                font_size=font_size,
                stroke_color=stroke_color,
                stroke_width=stroke_width,
                margin=actual_margin
            )
            return clip
        except Exception as e:
            raise RuntimeError(
                f"ImageMagick TextClip creation failed: {e}\n"
                "Ensure ImageMagick is properly installed."
            )
    else:
        print("⚠ ImageMagick not found – using PIL method (no stroke/margin).")
        try:
            clip = TextClip(
                text=text,
                font=font,
                color=color,
                font_size=font_size,
                method='label'
            )
            return clip
        except Exception as e:
            raise RuntimeError(f"PIL TextClip creation failed: {e}")