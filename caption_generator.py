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
def get_available_fonts():
    """
    Returns a list of (display_name, path) for all usable fonts.
    Uses fontconfig (fc-list) for system fonts, and scans the script folder for .ttf/.otf.
    """
    fonts = []
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. System fonts via fc-list
    try:
        result = subprocess.run(['fc-list', '-f', '%{family}||%{file}\n'],
                                capture_output=True, text=True, check=True)
        lines = result.stdout.strip().split('\n')
        seen = set()
        for line in lines:
            if not line.strip():
                continue
            family, filepath = line.split('||', 1)
            # Skip duplicates (same file path)
            if filepath in seen:
                continue
            seen.add(filepath)
            fonts.append((family, filepath))
    except Exception as e:
        print(f"⚠ Could not retrieve system fonts: {e}")

    # 2. Local font files in script folder
    local_fonts = glob.glob(os.path.join(script_dir, '*.ttf')) + \
                  glob.glob(os.path.join(script_dir, '*.otf'))
    for f in local_fonts:
        # Use filename as display name
        display = os.path.basename(f)
        fonts.append((display, f))

    # Remove duplicates by path (keep first occurrence)
    unique = {}
    for name, path in fonts:
        if path not in unique:
            unique[path] = name
    fonts = [(name, path) for path, name in unique.items()]
    return fonts

def select_font():
    """Interactively ask user to choose a font, return its path or None.Interactively prompts the user to choose a font from the available list."""
    fonts = get_available_fonts()
    if not fonts:
        print("⚠ No custom fonts found. Using default system font.")
        return None

    print("\n📝 Available fonts:")
    print("0. Default system font")
    for i, (name, path) in enumerate(fonts, start=1):
        # Trim long names for display
        if len(name) > 50:
            name = name[:47] + "..."
        print(f"{i}. {name}")

    while True:
        choice = input("\nSelect font number (or 0 for default): ").strip()
        if choice == '':
            choice = '0'
        if choice == '0':
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(fonts):
                selected_path = fonts[idx][1]
                print(f"✓ Using font: {fonts[idx][0]}")
                return selected_path
            else:
                print("❌ Invalid number, try again.")
        except ValueError:
            print("❌ Please enter a number.")
# ------------------------------------------------------------
# TextClip creation – uses correct MoviePy 2.x parameter names (Creates a TextClip with the given text, style, and margin, trying multiple fallback methods.)
# ------------------------------------------------------------
def create_text_clip(text, config, font=None, color=None, stroke_color=None,
                     stroke_width=None, font_size=None, align='center',
                     margin=(40, 40, 40, 40)):
    """
    Create a TextClip using settings from config.json (if provided).
    Explicit parameters override config values.

    - If ImageMagick is available, a clip with stroke and margin is created.
    - Otherwise, a simpler PIL clip is created and a warning is printed.
    This ensures visual consistency throughout the video.
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
            else:
                print(f"⚠ Font from config not found: {font_path}")
        # else font remains None (system default)

    if color is None:
        color = font_cfg.get("color", "white")
    if stroke_color is None:
        stroke_color = font_cfg.get("stroke_color", "black")
    if stroke_width is None:
        stroke_width = font_cfg.get("stroke_width", 6)
    if font_size is None:
        font_size = font_cfg.get("size", 72)

    # Check if ImageMagick is available (binary is set in global config)
    if mpconfig.IMAGEMAGICK_BINARY is not None:
        # Use full features (stroke + margin) – requires ImageMagick
        try:
            clip = TextClip(
                text=text,
                font=font,
                color=color,
                font_size=font_size,
                stroke_color=stroke_color,
                stroke_width=stroke_width,
                margin=margin
            )
            print("✅ TextClip created with ImageMagick (stroke + margin)")
            return clip
        except Exception as e:
            # If full features fail, we could fall back, but that would risk inconsistency.
            # Instead, we raise a clear error so the user can fix their environment.
            raise RuntimeError(
                f"ImageMagick is available but TextClip creation failed: {e}\n"
                "Please ensure ImageMagick is properly installed and configured."
            )
    else:
        # No ImageMagick – use PIL method (no stroke, no margin)
        print("⚠ ImageMagick not found – using PIL method (no stroke/margin).")
        try:
            clip = TextClip(
                text=text,
                font=font,
                color=color,
                font_size=font_size,
                method='label'  # PIL‑based rendering
            )
            print("✅ TextClip created with PIL (no stroke/margin)")
            return clip
        except Exception as e:
            raise RuntimeError(f"PIL TextClip creation failed: {e}")

# ------------------------------------------------------------
# Caption with pop, shake, and fade effects (Wraps a text clip with a pop‑scale animation and short fade‑in/out effects.)
# ------------------------------------------------------------
def make_viral_caption(txt, duration, config):
    """Create a single caption clip with a subtle, almost imperceptible pop effect."""
    clip = create_text_clip(txt, config)
    if clip is None:
        return None

    clip = clip.with_duration(duration)
    orig_w, orig_h = clip.size

    # ---- configurable scale factor (default: 5% increase) ----
    scale_amount = 0.05   # change this to 0.01 for 1% pop, or 0.0 for none
    # Optionally read from config.json: scale_amount = config.get("pop_scale", 0.05)
    # ---------------------------------------------------------

    def scale_effect(t):
        if t < 0.05:                     # pop up in 0.05s
            prog = t / 0.05
            ease = 1 - (1 - prog) ** 3
            return 1 + scale_amount * ease
        elif t < 0.1:                    # pop back in 0.05s
            prog = (t - 0.05) / 0.05
            ease = prog ** 3
            return (1 + scale_amount) - scale_amount * ease
        else:
            return 1.0

    clip = clip.resized(lambda t: (orig_w * scale_effect(t), orig_h * scale_effect(t)))

    # Even shorter fade in/out for a crisp transition
    clip = fadein(clip, 0.03)
    clip = fadeout(clip, 0.03)

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
    Punctuation is attached to the preceding word, and apostrophe contractions
    (e.g., 's, 't, 're) are merged with the previous word for proper display.
    """
    # ---- configurable parameters ----
    MAX_PHRASE_WORDS = 5          # maximum words per subtitle
    MAX_LINE_CHARS = 40           # if phrase longer, split into two lines
    PAUSE_THRESHOLD = 0.3         # seconds – break phrase if gap > this
    # --------------------------------

    # Generate word-level SRT (one word per line)
    cmd = [BINARY_PATH, "-m", MODEL_PATH, "-osrt", "-ml", "1", audio_path]
    subprocess.run(cmd, capture_output=True, text=True, check=True)

    word_srt = audio_path + ".srt"
    if not os.path.exists(word_srt):
        print(f"❌ Word‑level SRT not generated at {word_srt}")
        sys.exit(1)

    # Parse word-level SRT into (start, end, word)
    all_words = []
    with open(word_srt, 'r', encoding='utf-8') as f:
        content = f.read()
    blocks = re.split(r'\n\s*\n', content.strip())
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            time_line = lines[1]
            text = ' '.join(lines[2:])
            start_str, end_str = time_line.split(' --> ')
            start = time_to_seconds(start_str)
            end = time_to_seconds(end_str)
            if text.strip():
                all_words.append((start, end, text))

    if not all_words:
        print("❌ No words found in word‑level SRT.")
        sys.exit(1)

    # ---------- Merge punctuation and apostrophe contractions ----------
    merged_words = []
    for i, (start, end, word) in enumerate(all_words):
        # 1. Merge tokens that consist only of punctuation (e.g., ",", ";", ":")
        if re.fullmatch(r'[^\w\s]+', word):
            if merged_words:
                prev_start, prev_end, prev_word = merged_words[-1]
                merged_words[-1] = (prev_start, end, prev_word + word)
            else:
                # First token is punctuation – discard it
                continue
        # 2. Merge apostrophe contractions (e.g., "'s", "'t", "'re", "'ve", "'ll")
        elif re.fullmatch(r"['’][a-zA-Z]+", word):
            if merged_words:
                prev_start, prev_end, prev_word = merged_words[-1]
                merged_words[-1] = (prev_start, end, prev_word + word)
            else:
                # Should not happen – if it does, keep it as a word
                merged_words.append((start, end, word))
        else:
            merged_words.append((start, end, word))
    all_words = merged_words
    # ---------------------------------------------------------

    # Group words into phrases
    phrases = []
    current_phrase = []
    for i, (start, end, word) in enumerate(all_words):
        # If current phrase is empty, start a new one
        if not current_phrase:
            current_phrase.append((start, end, word))
            continue

        # Check if we should break the current phrase
        prev_end = current_phrase[-1][1]
        gap = start - prev_end

        # Break conditions:
        # 1. Punctuation at end of last word (e.g., ., ?, !)
        last_word_orig = current_phrase[-1][2]
        last_char = last_word_orig[-1] if last_word_orig else ''
        break_on_punct = last_char in '.?!'

        # 2. Pause longer than threshold
        break_on_pause = gap > PAUSE_THRESHOLD

        # 3. Reached maximum words in phrase
        break_on_max = len(current_phrase) >= MAX_PHRASE_WORDS

        if break_on_punct or break_on_pause or break_on_max:
            # Finalize current phrase
            phrase_start = current_phrase[0][0]
            phrase_end = current_phrase[-1][1]
            phrase_words = [w[2] for w in current_phrase]   # include punctuation
            phrase_text = ' '.join(phrase_words)

            # Optionally split into two lines if too long
            if len(phrase_text) > MAX_LINE_CHARS:
                # Find a space near the middle to break
                half = len(phrase_text) // 2
                split_pos = phrase_text.rfind(' ', 0, half)
                if split_pos == -1:
                    split_pos = phrase_text.find(' ', half)
                if split_pos != -1:
                    line1 = phrase_text[:split_pos]
                    line2 = phrase_text[split_pos+1:]
                    phrase_text = line1 + '\n' + line2
                # If no space found, keep as one line

            phrases.append((phrase_start, phrase_end, phrase_text))

            # Start a new phrase with current word
            current_phrase = [(start, end, word)]
        else:
            current_phrase.append((start, end, word))

    # Add the last phrase if any
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
                line1 = phrase_text[:split_pos]
                line2 = phrase_text[split_pos+1:]
                phrase_text = line1 + '\n' + line2
        phrases.append((phrase_start, phrase_end, phrase_text))

    # Write final SRT
    with open(srt_path, 'w', encoding='utf-8') as f:
        for i, (start, end, text) in enumerate(phrases, 1):
            f.write(f"{i}\n")
            f.write(f"{format_time(start)} --> {format_time(end)}\n")
            f.write(f"{text}\n\n")

    # Clean up temporary word‑level SRT
    os.remove(word_srt)
    print(f"✅ Phrase‑level SRT created: {srt_path} (1-{MAX_PHRASE_WORDS} words, punctuation kept)")
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

def parse_srt(srt_path):  #Parses an SRT file into a list of (start_time, end_time, text) tuples.
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    blocks = re.split(r'\n\s*\n', content.strip())
    subs = []
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            time_line = lines[1]
            text = ' '.join(lines[2:])
            start_str, end_str = time_line.split(' --> ')
            start = time_to_seconds(start_str)
            end = time_to_seconds(end_str)
            subs.append((start, end, text))
    return subs
# ------------------------------------------------------------
#Converts an SRT timestamp string to seconds as a float.
# ------------------------------------------------------------
def time_to_seconds(t_str):
    h, m, s = t_str.split(':')
    s, ms = s.split(',')
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

def generate_styled_video(video_path, srt_path, output_path, config):
    """Overlays animated captions using exact phrase timings from the SRT."""
    if not os.path.exists(video_path):
        print(f"❌ Video not found: {video_path}")
        sys.exit(1)
    print(f"Loading video: {video_path}")
    video = VideoFileClip(video_path)

    print(f"Loading subtitles: {srt_path}")
    subs = parse_srt(srt_path)

    # Get offset from config (default 0.0)
    offset = config.get("timestamp_offset", 0.0)

    # Get bottom margin (pixels from bottom edge)
    bottom_margin = config.get("caption_bottom_margin", 80)

    caption_clips = []
    for start, end, text in subs:
        duration = end - start
        if duration <= 0:
            continue

        # Apply offset to both start and end times
        start += offset
        end += offset
        if start < 0:
            start = 0

        clip = make_viral_caption(text, duration, config)
        if clip is None:
            continue

        # Position: horizontally centered, vertically at bottom minus margin
        # Note: clip.h is known after creation
        y_pos = video.h - bottom_margin - clip.h
        # Prevent negative y (shouldn't happen with reasonable margin)
        if y_pos < 0:
            y_pos = 0

        clip = clip.with_start(start).with_position(('center', y_pos))
        caption_clips.append(clip)

    if not caption_clips:
        print("❌ No valid captions to add.")
        return

    final = CompositeVideoClip([video] + caption_clips)

    video_cfg = config.get("video", {})
    fps = video_cfg.get("fps", 60)
    codec = video_cfg.get("codec", "libx264")

    print(f"Rendering: {output_path} (this takes ~2-5 min)...")
    final.write_videofile(output_path, fps=fps, codec=codec, audio_codec='aac')

    video.close()
    for clip in caption_clips:
        clip.close()
    final.close()
    print(f"✅ Video ready: {output_path}")

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
