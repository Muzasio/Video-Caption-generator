#!/usr/bin/env python3
"""
Gaming caption style – viral, aggressive, glitchy, and arcade‑like.
Option: word‑by‑word swipe from bottom border (off‑screen) then swipe down.
Includes fallback to standard style if word swipe fails.
"""

import random
import math
import re
from moviepy.video.VideoClip import ColorClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
import moviepy.config as mpconfig

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


def make_word_swipe_caption(txt, duration, style_config, gaming_cfg):
    """
    Create a caption where each word swipes up from below the screen,
    one by one, then after the full line, all words swipe down together.
    Returns None if any error occurs (fallback to standard style).
    """
    # Split words and filter out punctuation‑only tokens (e.g., "....", "?", "!")
    raw_words = txt.split()
    words = []
    for w in raw_words:
        # Keep only tokens that contain at least one alphanumeric character
        if re.search(r'[a-zA-Z0-9]', w):
            words.append(w)
        else:
            # Skip pure punctuation (like "...", ",", ".")
            continue

    if len(words) == 0:
        print("⚠ No valid words found for swipe effect, falling back to standard style.")
        return None

    # Animation timings
    word_appear_duration = gaming_cfg.get("word_appear_duration", 0.25)
    word_stagger = gaming_cfg.get("word_stagger", 0.15)
    hold_time = gaming_cfg.get("hold_time", 0.5)
    swipe_down_duration = gaming_cfg.get("swipe_down_duration", 0.3)
    start_offset = gaming_cfg.get("swipe_start_offset", 500)

    total_needed = len(words) * word_stagger + word_appear_duration + hold_time + swipe_down_duration
    if duration < total_needed:
        scale = duration / total_needed
        word_stagger *= scale
        word_appear_duration *= scale
        hold_time *= scale
        swipe_down_duration *= scale

    # Create temporary clips to measure word widths and heights
    temp_clips = []
    for w in words:
        clip = create_text_clip(w, style_config)
        if clip is None or clip.w == 0 or clip.h == 0:
            print(f"⚠ Word '{w}' has zero size, skipping swipe effect.")
            return None
        temp_clips.append(clip)

    # Calculate horizontal positions (centered within the composite)
    spacing = gaming_cfg.get("word_spacing", 10)
    x_positions = []
    current_x = 0
    for clip in temp_clips:
        x_positions.append(current_x)
        current_x += clip.w + spacing
    total_width = current_x - spacing
    if total_width <= 0:
        print("⚠ Total width zero, skipping swipe effect.")
        return None

    # We'll keep the composite's own coordinate system: x=0 is left edge of the whole phrase.
    # The main script will center this composite on the video.
    # No hardcoded 1920 centering here.

    # Final y position (relative to composite's top, 0 = top of composite)
    final_y = 0
    start_y = final_y + start_offset
    end_y = start_y

    all_up_time = (len(words) - 1) * word_stagger + word_appear_duration
    swipe_down_start = all_up_time + hold_time
    swipe_down_end = swipe_down_start + swipe_down_duration

    # Composite height must accommodate the start_y offset (off‑screen below)
    max_word_height = max(clip.h for clip in temp_clips)
    composite_height = max_word_height + start_offset + 50  # extra padding

    # For each word, create a clip with combined position function
    final_clips = []
    for i, clip in enumerate(temp_clips):
        word_start_time = i * word_stagger

        def make_position_func(idx, w_start, w_dur, up_y, down_start, down_dur, off_y):
            def pos_func(t):
                if t < w_start:
                    return (x_positions[idx], off_y)
                elif t < w_start + w_dur:
                    prog = (t - w_start) / w_dur
                    ease = 1 - (1 - prog) ** 3
                    y = off_y + (up_y - off_y) * ease
                    return (x_positions[idx], y)
                elif t < down_start:
                    return (x_positions[idx], up_y)
                elif t < down_start + down_dur:
                    prog = (t - down_start) / down_dur
                    y = up_y + (off_y - up_y) * prog
                    return (x_positions[idx], y)
                else:
                    return (x_positions[idx], off_y)
            return pos_func

        pos_func = make_position_func(
            i, word_start_time, word_appear_duration,
            final_y, swipe_down_start, swipe_down_duration, start_y
        )
        animated = clip.with_position(pos_func).with_duration(duration)
        final_clips.append(animated)

    composite = CompositeVideoClip(final_clips, size=(total_width, composite_height))
    return composite


def make_standard_gaming_caption(txt, duration, gaming_cfg):
    """Original gaming style with scale, shake, glitch, flash."""
    style_config = {
        "font": gaming_cfg["font"],
        "align": gaming_cfg["align"],
        "margin": gaming_cfg["margin"]
    }

    base_clip = create_text_clip(txt, style_config)
    if base_clip is None:
        return None

    base_clip = base_clip.with_duration(duration)
    orig_w, orig_h = base_clip.size

    # Scale pop
    scale_peak = gaming_cfg.get("scale_peak", 1.12)
    scale_duration = gaming_cfg.get("scale_duration", 0.12)

    def scale_effect(t):
        if t >= scale_duration:
            return 1.0
        progress = t / scale_duration
        if progress < 0.6:
            return 1.0 + (scale_peak - 1.0) * (progress / 0.6)
        else:
            return scale_peak - (scale_peak - 1.0) * ((progress - 0.6) / 0.4)

    scaled_clip = base_clip.resized(lambda t: (orig_w * scale_effect(t), orig_h * scale_effect(t)))

    # Shake + slide
    shake_intensity = gaming_cfg.get("shake_intensity", 10)
    shake_duration = gaming_cfg.get("shake_duration", 0.15)
    slide_enabled = gaming_cfg.get("slide_enabled", True)
    slide_direction = gaming_cfg.get("slide_direction", "right")
    slide_distance = gaming_cfg.get("slide_distance", orig_w)
    slide_dur = 0.1

    def combined_position(t):
        dx = 0
        dy = 0
        if slide_enabled and t < slide_dur:
            prog = t / slide_dur
            ease = 1 - (1 - prog) ** 3
            if slide_direction == "right":
                dx = -slide_distance * (1 - ease)
            elif slide_direction == "left":
                dx = slide_distance * (1 - ease)
            elif slide_direction == "top":
                dy = slide_distance * (1 - ease)
            elif slide_direction == "bottom":
                dy = -slide_distance * (1 - ease)
        if t < shake_duration:
            intensity = shake_intensity * (1 - t / shake_duration)
            dx += random.randint(-int(intensity), int(intensity))
            dy += random.randint(-int(intensity), int(intensity))
        return (int(dx), int(dy))

    positioned_clip = scaled_clip.with_position(combined_position)

    # Glitch (simple RGB shift composite)
    glitch_intensity = gaming_cfg.get("glitch_intensity", 15)
    glitch_active_duration = gaming_cfg.get("glitch_active_duration", 0.2)

    red_shift = positioned_clip.with_position((glitch_intensity, 0))
    blue_shift = positioned_clip.with_position((-glitch_intensity, 0))
    glitch_composite = CompositeVideoClip([
        positioned_clip,
        red_shift,
        blue_shift
    ], size=positioned_clip.size)

    glitch_clip = glitch_composite.with_start(0).with_end(min(glitch_active_duration, duration))
    if glitch_active_duration < duration:
        normal_clip = positioned_clip.with_start(glitch_active_duration).with_end(duration)
        final_before_flash = CompositeVideoClip([glitch_clip, normal_clip], size=positioned_clip.size)
    else:
        final_before_flash = glitch_clip

    # Kill flash
    flash_enabled = gaming_cfg.get("flash_enabled", True)
    flash_color = gaming_cfg.get("flash_color", "white")
    flash_duration_val = gaming_cfg.get("flash_duration", 0.05)

    if flash_enabled:
        if flash_color == "white":
            flash_rgb = (255, 255, 255)
        elif flash_color == "red":
            flash_rgb = (255, 0, 0)
        else:
            fc = flash_color.lstrip('#')
            if len(fc) == 6:
                flash_rgb = tuple(int(fc[i:i+2], 16) for i in (0, 2, 4))
            else:
                flash_rgb = (255, 255, 255)
        flash = ColorClip(size=final_before_flash.size, color=flash_rgb).with_duration(flash_duration_val)
        flash = flash.with_opacity(0.7).with_start(0)
        final_clip = CompositeVideoClip([final_before_flash, flash], size=final_before_flash.size)
    else:
        final_clip = final_before_flash

    final_clip = fadein(final_clip, 0.02)
    final_clip = fadeout(final_clip, 0.02)
    return final_clip


def make_gaming_caption(txt, duration):
    """
    Gaming style: either standard (scale, shake, glitch, flash) or word‑by‑word swipe.
    Falls back to standard if word swipe fails.
    """
    if not txt or not txt.strip():
        return None

    gaming_cfg = CONFIG["gaming"]

    if gaming_cfg.get("word_swipe_enabled", False):
        print(f"🎮 GAMING WORD SWIPE | text: {txt[:50]}...")
        style_config = {
            "font": gaming_cfg["font"],
            "align": gaming_cfg["align"],
            "margin": gaming_cfg["margin"]
        }
        swipe_clip = make_word_swipe_caption(txt, duration, style_config, gaming_cfg)
        if swipe_clip is not None:
            return swipe_clip
        else:
            print("⚠ Word swipe failed, falling back to standard gaming style.")
            # Fall through to standard style

    print(f"🎮 GAMING STYLE (standard) | text: {txt[:50]}...")
    return make_standard_gaming_caption(txt, duration, gaming_cfg)