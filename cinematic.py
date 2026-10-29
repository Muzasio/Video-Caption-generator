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

def make_cinematic_caption(txt, duration, video_width=1920):
    """
    Cinematic style: letterbox bar, elegant positioning, slow fades.
    Uses global CONFIG['cinematic'].
    video_width: pass the actual video width so the letterbox spans the full frame.
    """
    cinematic_cfg = CONFIG["cinematic"]
    style_config = {
        "font": cinematic_cfg["font"],
        "align": cinematic_cfg["align"],
        "margin": cinematic_cfg["margin"]
    }

    clip = create_text_clip(txt, style_config)
    if clip is None:
        return None
    clip = clip.with_duration(duration)

    letterbox_height = cinematic_cfg["letterbox_height"]
    letterbox_color_hex = cinematic_cfg["letterbox_color"].lstrip('#')
    if len(letterbox_color_hex) == 6:
        letterbox_color = tuple(int(letterbox_color_hex[i:i+2], 16) for i in (0, 2, 4))
    elif len(letterbox_color_hex) == 3:
        letterbox_color = tuple(int(c*2, 16) for c in letterbox_color_hex)
    else:
        raise ValueError("Invalid letterbox_color hex")
    letterbox_opacity = cinematic_cfg["letterbox_opacity"]

    letterbox = ColorClip(size=(video_width, letterbox_height), color=letterbox_color).with_opacity(letterbox_opacity).with_duration(duration)
    letterbox = letterbox.with_position(('center', 'bottom'))

    text_y = -letterbox_height/2 + clip.h/2 + 20
    clip = clip.with_position(('center', text_y))

    clip = fadein(clip, 0.15)
    clip = fadeout(clip, 0.25)

    final_clip = CompositeVideoClip([letterbox, clip])
    final_clip = final_clip.with_duration(duration)
    return final_clip