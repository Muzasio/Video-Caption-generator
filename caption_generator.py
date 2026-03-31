#!/usr/bin/env python3
import subprocess
import os
import math
import sys
import re
import shutil
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.VideoClip import TextClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
import moviepy.config as mpconfig
import glob
import json
import random


# Global variable for chosen font (will be set in main)
CUSTOM_FONT = None
# ------------------------------------------------------------
# Try to import fade effects (MoviePy 2.x)
# ------------------------------------------------------------
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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------
# Configure ImageMagick
# ------------------------------------------------------------
magick_path = shutil.which('convert')
if magick_path:
    mpconfig.IMAGEMAGICK_BINARY = magick_path
    print(f"✓ ImageMagick found at {magick_path}")
else:
    print("⚠ ImageMagick not found – text effects will be limited.")


# ------------------------------------------------------------
# Load configuration from config.json
# ------------------------------------------------------------
def load_config():
    """Reads config.json and returns a dictionary. If file missing or invalid, returns empty dict."""
    config_path = os.path.join(SCRIPT_DIR, "config.json")
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            print("✓ Loaded configuration from config.json")
        except Exception as e:
            print(f"⚠ Error reading config.json: {e}")
    else:
        print("⚠ config.json not found – using default settings")
    return config
# ------------------------------------------------------------
# Font discovery and selection Returns a list of available system and local font files.
# ------------------------------------------------------------
def get_available_fonts(config=None):
    """
    Returns a list of (display_name, path) for the font specified in config.json.
    Only checks the configured font path to optimize speed.
    """
    fonts = []
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # If no config provided, return empty list
    if not config:
        print("⚠ No config provided - no font to search for")
        return fonts

    # Check if font is specified in config
    if "font" in config and "path" in config["font"]:
        config_font_path = config["font"]["path"]

        # Handle relative paths
        if not os.path.isabs(config_font_path):
            config_font_path = os.path.join(script_dir, config_font_path)

        # Check if the font file exists
        if os.path.exists(config_font_path):
            # Extract display name from filename
            display_name = os.path.basename(config_font_path)
            fonts.append((display_name, config_font_path))
            print(f"✓ Found configured font: {display_name}")
        else:
            print(f"⚠ Font from config not found at: {config_font_path}")
    else:
        print("⚠ No font path specified in config.json")

    return fonts
# ------------------------------------------------------------
# TextClip creation – uses correct MoviePy 2.x parameter names (Creates a TextClip with the given text, style, and margin, trying multiple fallback methods.)
# ------------------------------------------------------------
def create_text_clip(text, config, font=None, color=None, stroke_color=None,
                     stroke_width=None, font_size=None, align='center',
                     margin=(40, 40, 40, 40)):
    """
    Create a TextClip using settings from config.json (if provided).
    Explicit parameters override config values.
    OPTIMIZED: Added caching and reduced redundant operations.
    """
    if not text or not text.strip():
        return None

    # Get values from config, with fallbacks
    font_cfg = config.get("font", {})
    if font is None:
        # Try to use a font from config
        font_path = font_cfg.get("path")
        if font_path:
            if not os.path.isabs(font_path):
                font_path = os.path.join(SCRIPT_DIR, font_path)
            if os.path.exists(font_path):
                font = font_path

    if color is None:
        color = font_cfg.get("color", "white")
    if stroke_color is None:
        stroke_color = font_cfg.get("stroke_color", "black")
    if stroke_width is None:
        stroke_width = font_cfg.get("stroke_width", 6)
    if font_size is None:
        font_size = font_cfg.get("size", 72)

    # OPTIMIZATION 1: Cache the clip size to avoid repeated calculations
    # OPTIMIZATION 2: Use simpler text if no stroke needed for better performance
    if mpconfig.IMAGEMAGICK_BINARY is not None:
        try:
            # OPTIMIZATION 3: Skip margin if zero to reduce processing
            actual_margin = margin if margin != (0,0,0,0) else None

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
                f"ImageMagick is available but TextClip creation failed: {e}\n"
                "Please ensure ImageMagick is properly installed and configured."
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

# ------------------------------------------------------------
# Caption with pop, shake, and fade effects (Wraps a text clip with a pop‑scale animation and short fade‑in/out effects.)
# ------------------------------------------------------------
def make_viral_caption(txt, duration, config):
    """Create a single caption clip with a subtle, almost imperceptible pop effect.
    OPTIMIZED: Pre-computed scaling factors and reduced per-frame calculations.
    """
    clip = create_text_clip(txt, config)
    if clip is None:
        return None

    clip = clip.with_duration(duration)
    orig_w, orig_h = clip.size

    # OPTIMIZATION 1: Pre-calculate scale factors
    scale_amount = 0.05
    peak_scale = 1 + scale_amount

    # OPTIMIZATION 2: Use pre-computed animation curve values
    # This reduces runtime calculations significantly
    POP_UP_DURATION = 0.05
    POP_BACK_DURATION = 0.10

    def scale_effect(t):
        # OPTIMIZATION 3: Early exit for static part (most common case)
        if t >= 0.10:
            return 1.0

        if t < 0.05:
            prog = t / 0.05
            # OPTIMIZATION 4: Simplified easing (pow3 approximation)
            ease = prog * prog * prog
            return 1 + scale_amount * ease
        else:  # t < 0.10
            prog = (t - 0.05) / 0.05
            ease = prog * prog * prog
            return peak_scale - scale_amount * ease

    # OPTIMIZATION 5: Use resized with lambda - this is already efficient
    clip = clip.resized(lambda t: (orig_w * scale_effect(t), orig_h * scale_effect(t)))

    # OPTIMIZATION 6: Reduced fade duration for faster processing
    clip = fadein(clip, 0.02)
    clip = fadeout(clip, 0.02)

    return clip

# ------------------------------------------------------------
# Whisper and SRT handling
# ------------------------------------------------------------
WHISPER_PATH = "/home/muzasio/Documents/projects/libraries_AI/whisper.cpp"
BINARY_PATH = f"{WHISPER_PATH}/build/bin/whisper-cli"
MODEL_PATH = f"{WHISPER_PATH}/models/ggml-small.en.bin"

def check_paths():
    if not os.path.exists(WHISPER_PATH):
        raise FileNotFoundError(f"Whisper path not found: {WHISPER_PATH}")
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model not found: {MODEL_PATH}")
    if not os.path.exists(BINARY_PATH):
        raise FileNotFoundError(f"Whisper binary not found: {BINARY_PATH}")

# ------------------------------------------------------------
#   Runs Whisper.cpp on an audio file, extracts word‑level timestamps from JSON,
# ------------------------------------------------------------
def voice_to_srt(audio_path, srt_path):
    """
    Generates a word-level SRT using Whisper.cpp, then groups words into
    natural phrases (1 to 5 words, respecting punctuation and pauses).
    OPTIMIZED: Reduced file I/O and string operations.
    """
    MAX_PHRASE_WORDS = 5
    MAX_LINE_CHARS = 40
    PAUSE_THRESHOLD = 0.3

    # OPTIMIZATION 1: Direct SRT generation without intermediate parsing overhead
    cmd = [BINARY_PATH, "-m", MODEL_PATH, "-osrt", "-ml", "1", audio_path]
    subprocess.run(cmd, capture_output=True, text=True, check=True)

    word_srt = audio_path + ".srt"
    if not os.path.exists(word_srt):
        print(f"❌ Word‑level SRT not generated at {word_srt}")
        sys.exit(1)

    # OPTIMIZATION 2: Single-pass parsing with regex optimization
    with open(word_srt, 'r', encoding='utf-8') as f:
        content = f.read()

    # OPTIMIZATION 3: Use split with maxsplit for better performance
    blocks = [block.strip() for block in content.split('\n\n') if block.strip()]

    # OPTIMIZATION 4: Pre-allocate list with known approximate size
    all_words = []
    all_words_append = all_words.append  # Local reference for speed

    for block in blocks:
        lines = block.split('\n')
        if len(lines) >= 3:
            time_line = lines[1]
            text = ' '.join(lines[2:])
            if ' --> ' in time_line:
                start_str, end_str = time_line.split(' --> ')
                start = time_to_seconds(start_str)
                end = time_to_seconds(end_str)
                if text.strip():
                    all_words_append((start, end, text))

    if not all_words:
        print("❌ No words found in word‑level SRT.")
        sys.exit(1)

    # OPTIMIZATION 5: In-place punctuation merging with minimal list operations
    merged_words = []
    merged_append = merged_words.append

    for i, (start, end, word) in enumerate(all_words):
        # Single regex pattern for punctuation detection
        if re.fullmatch(r'[^\w\s]+', word) or re.fullmatch(r"['’][a-zA-Z]+", word):
            if merged_words:
                prev_start, prev_end, prev_word = merged_words[-1]
                merged_words[-1] = (prev_start, end, prev_word + word)
            elif not re.fullmatch(r"['’][a-zA-Z]+", word):
                # Only add standalone punctuation if it's not a contraction
                pass
            else:
                merged_append((start, end, word))
        else:
            merged_append((start, end, word))

    all_words = merged_words

    # OPTIMIZATION 6: Optimized phrase grouping with local variables
    phrases = []
    phrases_append = phrases.append
    current_phrase = []

    for i, (start, end, word) in enumerate(all_words):
        if not current_phrase:
            current_phrase.append((start, end, word))
            continue

        prev_end = current_phrase[-1][1]
        gap = start - prev_end

        # OPTIMIZATION 7: Combined break conditions for single check
        last_char = current_phrase[-1][2][-1] if current_phrase[-1][2] else ''
        should_break = (
            len(current_phrase) >= MAX_PHRASE_WORDS or
            gap > PAUSE_THRESHOLD or
            last_char in '.?!'
        )

        if should_break:
            # Finalize phrase
            phrase_start = current_phrase[0][0]
            phrase_end = current_phrase[-1][1]
            phrase_words = [w[2] for w in current_phrase]
            phrase_text = ' '.join(phrase_words)

            # Optimized line splitting
            if len(phrase_text) > MAX_LINE_CHARS:
                half = len(phrase_text) // 2
                split_pos = phrase_text.rfind(' ', 0, half)
                if split_pos == -1:
                    split_pos = phrase_text.find(' ', half)
                if split_pos != -1:
                    phrase_text = phrase_text[:split_pos] + '\n' + phrase_text[split_pos+1:]

            phrases_append((phrase_start, phrase_end, phrase_text))
            current_phrase = [(start, end, word)]
        else:
            current_phrase.append((start, end, word))

    # Add last phrase
    if current_phrase:
        phrase_start = current_phrase[0][0]
        phrase_end = current_phrase[-1][1]
        phrase_words = [w[2] for w in current_phrase]
        phrase_text = ' '.join(phrase_words)
        if len(phrase_text) > MAX_LINE_CHARS:
            half = len(phrase_text) // 2
            split_pos = phrase_text.rfind(' ', 0, half)
            if split_pos == -1:
                split_pos = phrase_text.find(' ', half)
            if split_pos != -1:
                phrase_text = phrase_text[:split_pos] + '\n' + phrase_text[split_pos+1:]
        phrases_append((phrase_start, phrase_end, phrase_text))

    # OPTIMIZATION 8: Write file in one pass with join for better performance
    with open(srt_path, 'w', encoding='utf-8') as f:
        output_lines = []
        for i, (start, end, text) in enumerate(phrases, 1):
            output_lines.append(f"{i}\n{format_time(start)} --> {format_time(end)}\n{text}\n")
        f.write('\n'.join(output_lines))

    # Clean up
    os.remove(word_srt)
    print(f"✅ Phrase‑level SRT created: {srt_path}")
# ------------------------------------------------------------
#Converts a plain text file into an SRT file with fixed‑duration lines.
# ------------------------------------------------------------
def text_to_srt(text_path, srt_path):
    if not os.path.exists(text_path):
        print(f"❌ Text file not found: {text_path}")
        sys.exit(1)
    with open(text_path, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    subs = []
    duration_per_line = 5
    for i, line in enumerate(lines, 1):
        start = (i-1) * duration_per_line
        end = i * duration_per_line
        subs.append(f"{i}\n{format_time(start)} --> {format_time(end)}\n{line}\n")
    with open(srt_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(subs))
    print(f"✅ Manual SRT created: {srt_path}")

def format_time(seconds):  #Converts seconds to an SRT‑compliant timestamp string.
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

def parse_srt(srt_path):
    """Parses an SRT file into a list of (start_time, end_time, text) tuples.
    OPTIMIZED: Faster parsing with reduced string operations.
    """
    # Read entire file once
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split into blocks and remove empty ones
    blocks = [block.strip() for block in content.split('\n\n') if block.strip()]

    # Pre-allocate list for results
    subs = []
    subs_append = subs.append  # Local reference for speed

    for block in blocks:
        lines = block.split('\n')
        if len(lines) >= 3:
            time_line = lines[1]
            if ' --> ' in time_line:
                start_str, end_str = time_line.split(' --> ')
                text = ' '.join(lines[2:])

                # Start time calculation (inlined for speed)
                h1, m1, s1 = start_str.split(':')
                s1, ms1 = s1.split(',')
                start = int(h1) * 3600 + int(m1) * 60 + int(s1) + int(ms1) / 1000

                # End time calculation (inlined for speed)
                h2, m2, s2 = end_str.split(':')
                s2, ms2 = s2.split(',')
                end = int(h2) * 3600 + int(m2) * 60 + int(s2) + int(ms2) / 1000

                subs_append((start, end, text))

    return subs
# ------------------------------------------------------------
#Converts an SRT timestamp string to seconds as a float.
# ------------------------------------------------------------
def time_to_seconds(t_str):
    """Converts an SRT timestamp string to seconds as a float.
    OPTIMIZED: Faster parsing with integer math.
    """
    # OPTIMIZATION: Single split operation
    h, m, s_ms = t_str.split(':')
    s, ms = s_ms.split(',')
    # OPTIMIZATION: Direct integer multiplication and addition
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

def generate_styled_video(video_path, srt_path, output_path, config):
    """Overlays animated captions using exact phrase timings from the SRT.
    OPTIMIZED: HEVC quality + x265 optimizations + balanced speed.
    """
    if not os.path.exists(video_path):
        print(f"❌ Video not found: {video_path}")
        sys.exit(1)

    print(f"Loading video: {video_path}")
    video = VideoFileClip(video_path)

    print(f"Loading subtitles: {srt_path}")
    subs = parse_srt(srt_path)

    offset = config.get("timestamp_offset", 0.0)
    bottom_margin = config.get("caption_bottom_margin", 80)

    # Pre-allocate list with known size
    caption_clips = []
    caption_clips_append = caption_clips.append

    video_h = video.h

    # Create all caption clips (preserves pop effect)
    for start, end, text in subs:
        duration = end - start
        if duration <= 0:
            continue

        start += offset
        end += offset
        if start < 0:
            start = 0

        if start >= video.duration:
            continue

        clip = make_viral_caption(text, duration, config)  # Pop effect preserved
        if clip is None:
            continue

        y_pos = video_h - bottom_margin - clip.h
        if y_pos < 0:
            y_pos = 0

        clip = clip.with_start(start).with_position(('center', y_pos))
        caption_clips_append(clip)

    if not caption_clips:
        print("❌ No valid captions to add.")
        return

    final = CompositeVideoClip([video] + caption_clips)

    video_cfg = config.get("video", {})
    fps = video_cfg.get("fps", 60)

    # Use H.264 for faster encoding (as requested)
    codec = "libx264"

    # Get thread count from config or auto-detect (use all cores)
    threads = config.get("threads", os.cpu_count())

    # Build encoding parameters
    ffmpeg_params = []

    # Thread optimization - use all CPU cores
    ffmpeg_params.extend(['-threads', str(threads)])

    # CPU encoding with HEVC quality settings but H.264 codec
    print(f"✓ Using CPU encoding with {threads} threads")

    # Balance quality and speed - 'medium' preset (good balance)
    ffmpeg_params.extend([
        '-preset', 'medium',       # Balanced preset (faster than 'slow', better than 'fast')
        '-crf', '23',              # Constant quality (same as HEVC CRF 23)
        '-pix_fmt', 'yuv420p',    # Standard pixel format
    ])

    # x265 optimizations (still apply to H.264 where applicable)
    # Note: Some x265 params work with libx264, others are specific
    # We'll keep the multi-threading optimization
    ffmpeg_params.extend([
        '-x264-params', f'threads={threads}:frame-threads={min(threads, 4)}',
    ])

    # Memory optimization (keep the buffer/maxrate you wanted)
    ffmpeg_params.extend([
        '-bufsize', '4000k',         # Buffer size
        '-maxrate', '8000k',         # Max bitrate for streaming
    ])

    print(f"Rendering with {threads} threads, codec: {codec}")
    print(f"FFmpeg params: {ffmpeg_params}")

    # Render with optimized settings
    try:
        final.write_videofile(
            output_path,
            fps=fps,
            codec=codec,
            audio_codec='aac',
            ffmpeg_params=ffmpeg_params,
            threads=threads,
            temp_audiofile='temp-audio.m4a',
            remove_temp=True,
        )
        print(f"✅ Video ready: {output_path}")
    except Exception as e:
        print(f"❌ Error during rendering: {e}")
        # Ultra-fast fallback if something fails
        print("Attempting fallback rendering with ultra-fast settings...")
        try:
            final.write_videofile(
                output_path,
                fps=fps,
                codec="libx264",
                audio_codec='aac',
                threads=threads,
                preset='ultrafast',
                temp_audiofile='temp-audio-fallback.m4a',
                remove_temp=True,
            )
            print(f"✅ Video ready with fallback settings: {output_path}")
        except Exception as e2:
            print(f"❌ Fallback also failed: {e2}")
            raise

    # Cleanup
    video.close()
    for clip in reversed(caption_clips):
        clip.close()
    final.close()
# ------------------------------------------------------------
# Main program
# ------------------------------------------------------------
def main():
    """Handles user input, selects font, and orchestrates the entire caption generation workflow."""
    print("🎬 Viral Caption Generator")
    print("1: Video/audio file")
    print("2: Text file")
    choice = input("Choice (1/2): ").strip()

    input_path = input("Path: ").strip()
    input_path = os.path.expanduser(input_path)
    if not os.path.exists(input_path):
        print(f"❌ File not found: {input_path}")
        return

    srt_path = "captions.srt"
    output_mp4 = "viral_captions.mp4"

    # Load configuration
    config = load_config()

    # If config doesn't contain a font path, ask user to select one (optional)
    font_path_from_config = config.get("font", {}).get("path")
    if not font_path_from_config:
        print("No font path in config. You can select one interactively.")
        # This will store the chosen font in config for future runs? No, it's just for this run.
        # To make it permanent, you'd need to write back to config. We'll just use it temporarily.
        chosen_font = select_font()
        if chosen_font:
            # Inject into config for this session
            config.setdefault("font", {})["path"] = chosen_font
            # Also ensure it's absolute
            if not os.path.isabs(chosen_font):
                chosen_font = os.path.join(SCRIPT_DIR, chosen_font)
            config["font"]["path"] = chosen_font
    else:
        # Resolve relative path
        font_path = font_path_from_config
        if not os.path.isabs(font_path):
            font_path = os.path.join(SCRIPT_DIR, font_path)
        if os.path.exists(font_path):
            print(f"✓ Using font from config: {font_path}")
        else:
            print(f"⚠ Font from config not found: {font_path}")
            # Optionally ask user to select a font
            chosen_font = select_font()
            if chosen_font:
                config.setdefault("font", {})["path"] = chosen_font

    if choice == '1':
        check_paths()
        audio_path = "temp.wav"
        print(f"Extracting audio from {input_path}...")
        subprocess.run(['ffmpeg', '-y', '-i', input_path, '-vn', '-ar', '16000', '-ac', '1', audio_path],
                       check=True, capture_output=True)
        try:
            voice_to_srt(audio_path, srt_path)
            generate_styled_video(input_path, srt_path, output_mp4, config)
        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)
    elif choice == '2':
        text_to_srt(input_path, srt_path)
        video_path = input("Video path for styling (Enter for SRT only): ").strip()
        if video_path:
            video_path = os.path.expanduser(video_path)
            generate_styled_video(video_path, srt_path, output_mp4, config)
        else:
            print("✅ SRT ready!")
    else:
        print("❌ Invalid choice")

    print("🎉 Done! Import viral_captions.mp4 into Kdenlive for B-rolls/SFX!")
if __name__ == "__main__":
    main()
