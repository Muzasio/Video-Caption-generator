#!/usr/bin/env python3
import subprocess
import os
import math
import sys
import re
import shutil
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
import moviepy.config as mpconfig
import json
import random

# Import our modules
from config_manager import CONFIG
from text_clip import create_text_clip
from engaging import make_viral_caption
from gaming import make_gaming_caption
from podcast import make_podcast_caption
from cinematic import make_cinematic_caption

# ------------------------------------------------------------
# Try to import fade effects (MoviePy 2.x) – used for ASMR style
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
# ASMR style – kept here for now (can be moved later)
# ------------------------------------------------------------
def make_asmr_caption(txt, duration):
    asmr_cfg = CONFIG["asmr"]
    style_config = {
        "font": asmr_cfg["font"],
        "align": asmr_cfg["align"],
        "margin": asmr_cfg["margin"]
    }
    clip = create_text_clip(txt, style_config)
    if clip is None:
        return None
    clip = clip.with_duration(duration)

    softness = asmr_cfg["softness"]
    glow_intensity = asmr_cfg["glow_intensity"]
    clip = clip.with_opacity(softness)

    def gentle_breathing(t):
        return 1 + 0.008 * math.sin(t * 0.8)
    orig_w, orig_h = clip.size
    clip = clip.resized(lambda t: (orig_w * gentle_breathing(t), orig_h * gentle_breathing(t)))
    clip = fadein(clip, 0.3)
    clip = fadeout(clip, 0.4)
    if mpconfig.IMAGEMAGICK_BINARY and glow_intensity > 0:
        try:
            from moviepy.video.fx import lum_contrast
            clip = lum_contrast(clip, contrast=0.95)
        except:
            pass
    return clip

# ------------------------------------------------------------
# Whisper and SRT handling (unchanged)
# ------------------------------------------------------------
# Where whisper.cpp is built. Change it with the WHISPER_PATH environment variable.
WHISPER_PATH = os.environ.get("WHISPER_PATH", os.path.expanduser("~/.local/share/video-caption-generator/whisper.cpp"))
BINARY_PATH = f"{WHISPER_PATH}/build/bin/whisper-cli"
MODEL_PATH = f"{WHISPER_PATH}/models/ggml-small.en.bin"

def check_paths():
    if not os.path.exists(WHISPER_PATH):
        raise FileNotFoundError(f"Whisper path not found: {WHISPER_PATH}")
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model not found: {MODEL_PATH}")
    if not os.path.exists(BINARY_PATH):
        raise FileNotFoundError(f"Whisper binary not found: {BINARY_PATH}")

def voice_to_srt(audio_path, srt_path):
    MAX_PHRASE_WORDS = 5
    MAX_LINE_CHARS = 40
    PAUSE_THRESHOLD = 0.3

    cmd = [BINARY_PATH, "-m", MODEL_PATH, "-osrt", "-ml", "1", audio_path]
    subprocess.run(cmd, capture_output=True, text=True, check=True)

    word_srt = audio_path + ".srt"
    if not os.path.exists(word_srt):
        print(f"❌ Word‑level SRT not generated at {word_srt}")
        sys.exit(1)

    with open(word_srt, 'r', encoding='utf-8') as f:
        content = f.read()

    blocks = [block.strip() for block in content.split('\n\n') if block.strip()]
    all_words = []
    all_words_append = all_words.append

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

    merged_words = []
    merged_append = merged_words.append
    for i, (start, end, word) in enumerate(all_words):
        if re.fullmatch(r'[^\w\s]+', word) or re.fullmatch(r"['’][a-zA-Z]+", word):
            if merged_words:
                prev_start, prev_end, prev_word = merged_words[-1]
                merged_words[-1] = (prev_start, end, prev_word + word)
            elif not re.fullmatch(r"['’][a-zA-Z]+", word):
                pass
            else:
                merged_append((start, end, word))
        else:
            merged_append((start, end, word))
    all_words = merged_words

    phrases = []
    phrases_append = phrases.append
    current_phrase = []
    for i, (start, end, word) in enumerate(all_words):
        if not current_phrase:
            current_phrase.append((start, end, word))
            continue
        prev_end = current_phrase[-1][1]
        gap = start - prev_end
        last_char = current_phrase[-1][2][-1] if current_phrase[-1][2] else ''
        should_break = (
            len(current_phrase) >= MAX_PHRASE_WORDS or
            gap > PAUSE_THRESHOLD or
            last_char in '.?!'
        )
        if should_break:
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
            current_phrase = [(start, end, word)]
        else:
            current_phrase.append((start, end, word))
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

    with open(srt_path, 'w', encoding='utf-8') as f:
        output_lines = []
        for i, (start, end, text) in enumerate(phrases, 1):
            output_lines.append(f"{i}\n{format_time(start)} --> {format_time(end)}\n{text}\n")
        f.write('\n'.join(output_lines))
    os.remove(word_srt)
    print(f"✅ Phrase‑level SRT created: {srt_path}")

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

def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

def parse_srt(srt_path):
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    blocks = [block.strip() for block in content.split('\n\n') if block.strip()]
    subs = []
    subs_append = subs.append
    for block in blocks:
        lines = block.split('\n')
        if len(lines) >= 3:
            time_line = lines[1]
            if ' --> ' in time_line:
                start_str, end_str = time_line.split(' --> ')
                text = ' '.join(lines[2:])
                h1, m1, s1 = start_str.split(':')
                s1, ms1 = s1.split(',')
                start = int(h1) * 3600 + int(m1) * 60 + int(s1) + int(ms1) / 1000
                h2, m2, s2 = end_str.split(':')
                s2, ms2 = s2.split(',')
                end = int(h2) * 3600 + int(m2) * 60 + int(s2) + int(ms2) / 1000
                subs_append((start, end, text))
    return subs

def time_to_seconds(t_str):
    h, m, s_ms = t_str.split(':')
    s, ms = s_ms.split(',')
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

# ------------------------------------------------------------
# Video generation (uses global CONFIG)
# ------------------------------------------------------------
def generate_styled_video(video_path, srt_path, output_path):
    if not os.path.exists(video_path):
        print(f"❌ Video not found: {video_path}")
        sys.exit(1)

    print(f"Loading video: {video_path}")
    video = VideoFileClip(video_path)

    print(f"Loading subtitles: {srt_path}")
    subs = parse_srt(srt_path)

    offset = CONFIG.get("timestamp_offset", 0.0)
    bottom_margin = CONFIG.get("caption_bottom_margin", 80)

    caption_clips = []
    caption_clips_append = caption_clips.append
    video_h = video.h

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
        caption_style = CONFIG.get("caption_style", "engaging")
        clip = make_caption_by_style(text, duration, caption_style, video.w, video.h)
        if clip is None:
            continue
        # dynamic_caption returns full-frame composite — position is (0,0)
        if caption_style == "engaging":
            clip = clip.with_start(start).with_position((0, 0))
        else:
            y_pos = video_h - bottom_margin - clip.h
            if y_pos < 0:
                y_pos = 0
            clip = clip.with_start(start).with_position(('center', y_pos))
        caption_clips_append(clip)

    if not caption_clips:
        print("❌ No valid captions to add.")
        return

    final = CompositeVideoClip([video] + caption_clips)

    video_cfg = CONFIG.get("video", {})
    fps = video_cfg.get("fps", 60)
    codec = "libx264"
    threads = CONFIG.get("threads", os.cpu_count())

    ffmpeg_params = ['-threads', str(threads)]
    ffmpeg_params.extend(['-preset', 'medium', '-crf', '23', '-pix_fmt', 'yuv420p'])
    ffmpeg_params.extend(['-x264-params', f'threads={threads}:frame-threads={min(threads, 4)}'])
    ffmpeg_params.extend(['-bufsize', '4000k', '-maxrate', '8000k'])

    print(f"Rendering with {threads} threads, codec: {codec}")
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

    video.close()
    for clip in reversed(caption_clips):
        clip.close()
    final.close()

# ------------------------------------------------------------
# Factory function (no config parameter)
# ------------------------------------------------------------
def make_caption_by_style(txt, duration, style="engaging", video_width=1920, video_height=1080):
    style_map = {
        "engaging":  lambda t, d: make_viral_caption(t, d, video_w=video_width, video_h=video_height),
        "gaming":    lambda t, d: make_gaming_caption(t, d),
        "podcast":   lambda t, d: make_podcast_caption(t, d),
        "cinematic": lambda t, d: make_cinematic_caption(t, d, video_width),
        "asmr":      lambda t, d: make_asmr_caption(t, d),
    }
    maker = style_map.get(style, style_map["engaging"])
    return maker(txt, duration)

# ------------------------------------------------------------
# Interactive style selection (updates CONFIG in memory)
# ------------------------------------------------------------
def select_caption_style():
    print("\n" + "="*50)
    print("🎨 SELECT CAPTION STYLE")
    print("="*50)
    print("1. engaging    - Pop effect (MrBeast style) [DEFAULT]")
    print("2. gaming       - Glitch effects + shake (gaming content)")
    print("3. podcast      - Clean with speaker tags (interviews/podcasts)")
    print("4. cinematic    - Letterbox + elegant (movie trailers)")
    print("5. asmr         - Soft, gentle, calming (meditation/ASMR)")
    print("="*50)

    while True:
        try:
            choice = input("Select style (1-5) [default: 1]: ").strip()
            if choice == "" or choice == "1":
                style = "engaging"
                break
            elif choice == "2":
                style = "gaming"
                break
            elif choice == "3":
                style = "podcast"
                break
            elif choice == "4":
                style = "cinematic"
                break
            elif choice == "5":
                style = "asmr"
                break
            else:
                print("❌ Invalid choice. Please select 1-5.")
        except KeyboardInterrupt:
            print("\n❌ Cancelled")
            sys.exit(0)

    CONFIG["caption_style"] = style
    print(f"\n✅ Selected style: {style.upper()}")
    print("="*50 + "\n")

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def main():
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

    select_caption_style()

    selected_style = CONFIG.get("caption_style", "engaging")
    if selected_style == "engaging":
        font_path = CONFIG.get("font", {}).get("path")
        if not font_path:
            print("❌ No font path found for 'engaging' style in config.json.")
            return
    else:
        style_cfg = CONFIG.get(selected_style)
        if not style_cfg or not style_cfg.get("font", {}).get("path"):
            print(f"❌ No font path found for '{selected_style}' style in config.json.")
            return

    if choice == '1':
        check_paths()
        audio_path = "temp.wav"
        print(f"Extracting audio from {input_path}...")
        subprocess.run(['ffmpeg', '-y', '-i', input_path, '-vn', '-ar', '16000', '-ac', '1', audio_path],
                       check=True, capture_output=True)
        try:
            voice_to_srt(audio_path, srt_path)
            generate_styled_video(input_path, srt_path, output_mp4)
        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)
    elif choice == '2':
        text_to_srt(input_path, srt_path)
        video_path = input("Video path for styling (Enter for SRT only): ").strip()
        if video_path:
            video_path = os.path.expanduser(video_path)
            generate_styled_video(video_path, srt_path, output_mp4)
        else:
            print("✅ SRT ready!")
    else:
        print("❌ Invalid choice")

if __name__ == "__main__":
    main()