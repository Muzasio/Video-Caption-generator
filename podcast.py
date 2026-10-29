#!/usr/bin/env python3
from moviepy.video.VideoClip import ColorClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from text_clip import create_text_clip
from config_manager import CONFIG

# Fade effects fallback
try:
    from moviepy.video.fx.all import fadein, fadeout
except ImportError:
    try:
        from moviepy.video.fx import fadein, fadeout
    except ImportError:
        def fadein(clip, duration):
            return clip
        def fadeout(clip, duration):
            return clip
        print("⚠ Fade effects not available, proceeding without fades.")

def make_podcast_caption(txt, duration):
    """
    Podcast style: clean rectangular background, optional speaker name.
    Uses global CONFIG['podcast'].
    """
    podcast_cfg = CONFIG["podcast"]
    style_config = {
        "font": podcast_cfg["font"],
        "align": podcast_cfg["align"],
        "margin": podcast_cfg["margin"]
    }

    # Split speaker name if present
    speaker_name = None
    quote_text = txt
    if ': ' in txt and len(txt.split(': ')[0]) < 30:
        parts = txt.split(': ', 1)
        speaker_name = parts[0]
        quote_text = parts[1]

    # Background color from hex
    bg_color_hex = podcast_cfg["background_color"].lstrip('#')
    if len(bg_color_hex) == 6:
        bg_color = tuple(int(bg_color_hex[i:i+2], 16) for i in (0, 2, 4))
    elif len(bg_color_hex) == 3:
        bg_color = tuple(int(c*2, 16) for c in bg_color_hex)
    else:
        raise ValueError("Invalid background_color hex")

    bg_opacity = podcast_cfg["background_opacity"]
    padding = podcast_cfg["background_padding"]
    speaker_gap = podcast_cfg["speaker_gap"]
    speaker_color = podcast_cfg["speaker_color"]
    speaker_size = podcast_cfg["speaker_size"]

    # Quote text clip
    quote_clip = create_text_clip(quote_text, style_config)
    if quote_clip is None:
        return None
    quote_clip = quote_clip.with_duration(duration)

    # Speaker name clip (if any)
    speaker_clip = None
    if speaker_name:
        speaker_style = {
            "font": style_config["font"].copy(),
            "align": style_config["align"],
            "margin": style_config["margin"]
        }
        speaker_style["font"]["color"] = speaker_color
        speaker_style["font"]["size"] = speaker_size
        speaker_style["font"]["stroke_width"] = 2
        speaker_clip = create_text_clip(speaker_name, speaker_style)
        if speaker_clip:
            speaker_clip = speaker_clip.with_duration(duration)

    # Background dimensions
    if speaker_clip:
        total_text_height = speaker_clip.h + quote_clip.h + speaker_gap
        max_width = max(speaker_clip.w, quote_clip.w)
        bg_width = max_width + 2 * padding
        bg_height = total_text_height + 2 * padding
    else:
        bg_width = quote_clip.w + 2 * padding
        bg_height = quote_clip.h + 2 * padding

    bg_clip = ColorClip(size=(bg_width, bg_height), color=bg_color).with_opacity(bg_opacity).with_duration(duration)

    # Position text inside background
    if speaker_clip:
        speaker_x = (bg_width - speaker_clip.w) / 2
        speaker_y = padding
        speaker_clip = speaker_clip.with_position((speaker_x, speaker_y))
        quote_y = speaker_y + speaker_clip.h + speaker_gap
        quote_x = (bg_width - quote_clip.w) / 2
        quote_clip = quote_clip.with_position((quote_x, quote_y))
    else:
        quote_x = (bg_width - quote_clip.w) / 2
        quote_y = (bg_height - quote_clip.h) / 2
        quote_clip = quote_clip.with_position((quote_x, quote_y))

    # Composite
    components = [bg_clip, quote_clip]
    if speaker_clip:
        components.append(speaker_clip)
    final_clip = CompositeVideoClip(components, size=(bg_width, bg_height))
    final_clip = final_clip.with_duration(duration)
    final_clip = fadein(final_clip, 0.08)
    final_clip = fadeout(final_clip, 0.08)
    return final_clip