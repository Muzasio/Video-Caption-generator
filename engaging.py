#!/usr/bin/env python3
from config_manager import CONFIG
from dynamic_caption import make_dynamic_caption
import random, time

def fadein(clip, duration):
    return clip
def fadeout(clip, duration):
    return clip

# session seed — changes per run so placement varies each time
_SESSION_SEED = int(time.time()) % 99991

# phrase counter — increments per call so each phrase gets unique placement
_phrase_counter = [0]

def make_viral_caption(txt, duration, video_w=1080, video_h=1920):
    """
    Engaging style: semantic per-word animation + dynamic screen placement.
    Delegates fully to dynamic_caption.make_dynamic_caption.
    Returns (clip, x, y) tuple so caption_generator can place it absolutely.
    """
    if not txt or not txt.strip():
        return None

    idx = _phrase_counter[0]
    _phrase_counter[0] += 1

    clip, x, y = make_dynamic_caption(
        phrase       = txt,
        duration     = duration,
        video_w      = video_w,
        video_h      = video_h,
        phrase_index = idx,
        session_seed = _SESSION_SEED,
    )
    if clip is None:
        return None

    # attach x, y as attributes so caption_generator can read them
    clip._dynamic_x = x
    clip._dynamic_y = y
    return clip
