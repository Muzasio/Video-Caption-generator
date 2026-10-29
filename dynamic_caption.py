#!/usr/bin/env python3
"""
dynamic_caption.py — semantic word classifier + animated caption placement.
Animations use opacity and position only — no resized() calls.
resized() with time-varying lambdas causes (N,0) broadcast errors in MoviePy 2.x
when the clip mask and frame sizes desync. Avoided entirely here.
"""

import re
import math
import random
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from text_clip import create_text_clip
from config_manager import CONFIG

# ─── word classifiers ─────────────────────────────────────────────────────────

SHOUT_WORDS = {
    "wait","stop","look","watch","insane","crazy","unbelievable",
    "impossible","literally","actually","seriously","omg","bro",
    "dude","guys","everyone","nobody","always","never","every",
    "breaking","urgent","warning","alert","boom","wow","damn",
    "fire","legend","goat","massive","huge","giant","biggest",
    "best","worst","first","last","only","secret","revealed",
    "shocking","viral","trending","hack","trick","method",
}

NEGATIVE_WORDS = {
    "no","not","never","nothing","nobody","nowhere","neither",
    "nor","without","lack","fail","failed","failure","wrong",
    "bad","terrible","awful","horrible","worst","broken","dead",
    "dying","lost","losing","lose","miss","missed","hate",
    "stop","quit","end","over","done","finished",
}

CALM_WORDS = {
    "so","just","like","and","the","a","an","of","in",
    "to","is","was","are","were","be","been","being",
    "have","has","had","do","does","did","will","would",
    "could","should","may","might","shall","can","this",
    "that","these","those","it","its","they","them","their",
    "we","our","you","your","he","she","his","her",
    "with","from","at","by","for","on","about","into",
    "through","during","before","after","above","below",
    "then","than","but","or","if","when","where","how",
}

def classify_word(word):
    clean = word.strip(".,!?;:\"'()[]").lower()
    if word.rstrip(".,!?") == "...":
        return "ellipsis"
    if "?" in word:
        return "question"
    if re.fullmatch(r'[\d,.$%+\-/]+', clean):
        return "number"
    stripped = word.rstrip(".,!?;:")
    if stripped == stripped.upper() and len(clean) > 1 and clean.isalpha():
        return "caps"
    if clean in NEGATIVE_WORDS:
        return "negative"
    if clean in SHOUT_WORDS:
        return "shout"
    if clean in CALM_WORDS:
        return "calm"
    return "normal"

def word_energy(word_type):
    return {
        "shout":    1.0,
        "caps":     0.95,
        "number":   0.85,
        "negative": 0.80,
        "question": 0.60,
        "normal":   0.45,
        "calm":     0.20,
        "ellipsis": 0.10,
    }.get(word_type, 0.45)

# ─── avatar safe zone ─────────────────────────────────────────────────────────

def get_avatar_zone(video_h, video_w):
    av       = CONFIG.get("avatar", {})
    zone_pct = av.get("zone_height_pct", 0.35)
    zone_h   = int(video_h * zone_pct)
    return {"top": video_h - zone_h, "bottom": video_h, "height": zone_h}

# ─── placement ────────────────────────────────────────────────────────────────

def compute_y_position(phrase, clip_h, video_h, video_w, phrase_index, session_seed):
    avatar      = get_avatar_zone(video_h, video_w)
    safe_top    = int(video_h * 0.08)
    safe_bottom = avatar["top"] - 20
    usable_h    = safe_bottom - safe_top

    words      = phrase.strip().split()
    word_count = len(words)
    types      = [classify_word(w) for w in words]
    energies   = [word_energy(t) for t in types]
    max_energy = max(energies) if energies else 0.45

    if max_energy >= 0.85:
        base_frac = 0.18
    elif max_energy >= 0.60:
        base_frac = 0.35
    elif word_count <= 2:
        base_frac = 0.60
    else:
        base_frac = 0.45

    base_y = safe_top + int(usable_h * base_frac)
    rng    = random.Random(session_seed + phrase_index * 31)
    drift  = rng.randint(-55, 55)
    y      = base_y + drift
    y      = max(safe_top, min(safe_bottom - clip_h, y))
    return y

def compute_x_drift(phrase_index, session_seed):
    rng = random.Random(session_seed + phrase_index * 17)
    return rng.randint(-60, 60)

# ─── animations (position + opacity only, NO resized()) ───────────────────────
# All animations take (clip, base_x, base_y, duration) and return a positioned clip.
# base_x/base_y are absolute frame coordinates.

def _apply_slam(clip, base_x, base_y, duration):
    """Drops in from 20px above with fast ease."""
    def pos(t):
        if t < 0.08:
            drop = int(20 * (1 - t / 0.08) ** 2)
            return (base_x, base_y - drop)
        return (base_x, base_y)
    return clip.with_position(pos)

def _apply_pop(clip, base_x, base_y, duration):
    """Fades in from 0.6 opacity — no position change."""
    def pos(t):
        return (base_x, base_y)
    return clip.with_position(pos)

def _apply_bounce(clip, base_x, base_y, duration):
    """Bounces up then settles."""
    def pos(t):
        if t < 0.30:
            dy = int(-10 * math.sin(math.pi * t / 0.15) * max(0, 1 - t / 0.30))
            return (base_x, base_y + dy)
        return (base_x, base_y)
    return clip.with_position(pos)

def _apply_drift(clip, base_x, base_y, duration):
    """Slides in from 15px right."""
    def pos(t):
        if t < 0.20:
            dx = int(15 * (1 - t / 0.20))
            return (base_x + dx, base_y)
        return (base_x, base_y)
    return clip.with_position(pos)

def _apply_punch(clip, base_x, base_y, duration):
    """Drops in hard from 30px above."""
    def pos(t):
        if t < 0.05:
            drop = int(30 * (1 - t / 0.05))
            return (base_x, base_y - drop)
        return (base_x, base_y)
    return clip.with_position(pos)

def _apply_shake(clip, base_x, base_y, duration):
    """Shakes horizontally for 0.15s."""
    rng     = random.Random(base_x % 97)
    offsets = [rng.randint(-7, 7) for _ in range(200)]
    def pos(t):
        if t < 0.15:
            idx = int(t / 0.15 * len(offsets)) % len(offsets)
            intensity = 1 - t / 0.15
            dx = int(offsets[idx] * intensity)
            return (base_x + dx, base_y)
        return (base_x, base_y)
    return clip.with_position(pos)

ANIM_FN = {
    "shout":    _apply_slam,
    "caps":     _apply_slam,
    "number":   _apply_punch,
    "negative": _apply_shake,
    "question": _apply_bounce,
    "ellipsis": _apply_drift,
    "calm":     _apply_drift,
    "normal":   _apply_pop,
}

COLOR_MAP = {
    "caps":     "yellow",
    "shout":    "white",
    "negative": "#FF4444",
    "number":   "#00FFFF",
}

# ─── main entry ───────────────────────────────────────────────────────────────

def make_dynamic_caption(phrase, duration, video_w, video_h, phrase_index, session_seed):
    """
    Returns (composite_clip, 0, 0).
    Full-frame composite — caption_generator places at (0, 0).
    """
    if not phrase or not phrase.strip():
        return None, 0, 0

    font_cfg  = dict(CONFIG["font"])
    base_size = font_cfg["size"]
    words     = phrase.strip().split()
    if not words:
        return None, 0, 0

    types    = [classify_word(w) for w in words]
    energies = [word_energy(t) for t in types]
    spacing  = 14

    # Step 1: build clips at fixed sizes — no resized() anywhere
    base_clips = []
    for word, wtype, energy in zip(words, types, energies):
        this_font = dict(font_cfg)
        color = COLOR_MAP.get(wtype)
        if color:
            this_font["color"] = color
        # Font size is fixed per word — baked into TextClip, never animated
        size_scale        = 0.85 + 0.35 * energy
        this_font["size"] = max(30, int(base_size * size_scale))
        style = {
            "font":   this_font,
            "align":  CONFIG.get("align", "center"),
            "margin": (8, 8, 8, 8),
        }
        wclip = create_text_clip(word, style)
        if wclip is None:
            continue
        w, h = wclip.size
        if w < 2 or h < 2:
            continue
        wclip = wclip.with_duration(duration)
        base_clips.append((wclip, w, h, wtype, energy))

    if not base_clips:
        return None, 0, 0

    # Step 2: layout
    total_w = sum(w for _, w, _, _, _ in base_clips) + spacing * (len(base_clips) - 1)
    max_h   = max(h for _, _, h, _, _ in base_clips)

    y       = compute_y_position(phrase, max_h, video_h, video_w, phrase_index, session_seed)
    x_drift = compute_x_drift(phrase_index, session_seed)
    x_start = max(0, min(video_w - total_w, (video_w - total_w) // 2 + x_drift))

    # Step 3: apply position-only animations — no resized()
    frame_clips = []
    x_cursor    = x_start

    for (wclip, w, h, wtype, energy) in base_clips:
        base_x  = x_cursor
        base_y  = y + (max_h - h) // 2
        anim_fn = ANIM_FN.get(wtype, _apply_pop)
        animated = anim_fn(wclip, base_x, base_y, duration)
        frame_clips.append(animated)
        x_cursor += w + spacing

    # Full-frame composite — nothing overflows
    composite = CompositeVideoClip(frame_clips, size=(video_w, video_h))
    composite = composite.with_duration(duration)
    return composite, 0, 0
