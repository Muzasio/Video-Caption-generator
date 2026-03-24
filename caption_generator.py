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
# TextClip creation – uses correct MoviePy 2.x parameter names
# ------------------------------------------------------------
def create_text_clip(text, font=None, color='white',
                     stroke_color='black', stroke_width=3, font_size=60):
    """
    Create a TextClip with fallbacks.
    font=None lets ImageMagick/PIL use a system default.
    """
    if not text or not text.strip():
        return None

    candidates = [
        # Full features (stroke) – requires ImageMagick
        {'text': text, 'font': font, 'color': color, 'font_size': font_size,
         'stroke_color': stroke_color, 'stroke_width': stroke_width},
        # Without stroke
        {'text': text, 'font': font, 'color': color, 'font_size': font_size},
        # Basic PIL (method='label') – no custom font
        {'text': text, 'color': color, 'font_size': font_size, 'method': 'label'},
        # Minimal PIL
        {'text': text, 'font_size': font_size, 'method': 'label'}
    ]

    for i, kwargs in enumerate(candidates, 1):
        try:
            clip = TextClip(**kwargs)
            print(f"✅ TextClip created with candidate {i}")
            return clip
        except Exception as e:
            print(f"⚠ Candidate {i} failed: {e}")

    raise RuntimeError("Could not create TextClip. Check MoviePy and ImageMagick.")

# ------------------------------------------------------------
# Caption with pop, shake, and fade effects
# ------------------------------------------------------------
def make_viral_caption(txt, duration):
    """Create a single caption clip with effects."""
    clip = create_text_clip(txt)
    if clip is None:
        return None

    # Set duration
    clip = clip.with_duration(duration)

    # Store original dimensions for scaling
    orig_w, orig_h = clip.size

    # Pop effect: scale up then back down in first 0.4s
    def pop_effect(t):
        if t < 0.2:
            return 1 + 0.4 * (t / 0.2)
        elif t < 0.4:
            return 1.4 - 0.4 * ((t - 0.2) / 0.2)
        else:
            return 1.0

    # Resize using a lambda that returns new dimensions
    clip = clip.resized(lambda t: (orig_w * pop_effect(t), orig_h * pop_effect(t)))

    # Shake effect: small rotational oscillation
    clip = clip.rotated(lambda t: 3 * abs(math.sin(t * 5) * 0.1))

    # Fade in/out using direct function calls (not .fx)
    clip = fadein(clip, 0.5)
    clip = fadeout(clip, 0.5)

    return clip

# ------------------------------------------------------------
# Whisper and SRT handling (unchanged)
# ------------------------------------------------------------
WHISPER_PATH = "/home/muzasio/Documents/projects/libraries_AI/whisper.cpp"
BINARY_PATH = f"{WHISPER_PATH}/build/bin/whisper-cli"
MODEL_PATH = f"{WHISPER_PATH}/models/ggml-base.en.bin"

def check_paths():
    if not os.path.exists(WHISPER_PATH):
        raise FileNotFoundError(f"Whisper path not found: {WHISPER_PATH}")
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model not found: {MODEL_PATH}")
    if not os.path.exists(BINARY_PATH):
        raise FileNotFoundError(f"Whisper binary not found: {BINARY_PATH}")

def voice_to_srt(audio_path, srt_path):
    cmd = [BINARY_PATH, "-m", MODEL_PATH, "-osrt", audio_path]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    srt_generated = audio_path + ".srt"
    print(f"Checking for SRT: {srt_generated}")
    if os.path.exists(srt_generated):
        os.rename(srt_generated, srt_path)
        print(f"✅ SRT created: {srt_path}")
    else:
        print("❌ SRT not generated")
        sys.exit(1)

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

def time_to_seconds(t_str):
    h, m, s = t_str.split(':')
    s, ms = s.split(',')
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

def generate_styled_video(video_path, srt_path, output_path):
    if not os.path.exists(video_path):
        print(f"❌ Video not found: {video_path}")
        sys.exit(1)
    print(f"Loading video: {video_path}")
    video = VideoFileClip(video_path)

    print(f"Loading subtitles: {srt_path}")
    subs = parse_srt(srt_path)

    caption_clips = []
    for start, end, text in subs:
        duration = end - start
        if duration <= 0:
            continue
        clip = make_viral_caption(text, duration)
        if clip is None:
            print(f"⚠ Skipping empty caption at {start:.2f}s")
            continue
        # Use with_start and with_position (MoviePy 2.x)
        clip = clip.with_start(start).with_position(('center', 'bottom'))
        caption_clips.append(clip)

    if not caption_clips:
        print("❌ No valid captions to add.")
        return

    final = CompositeVideoClip([video] + caption_clips)

    print(f"Rendering: {output_path} (this takes ~2-5 min)...")
    # MoviePy 2.x no longer supports 'verbose' and 'logger' arguments
    final.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac')

    video.close()
    for clip in caption_clips:
        clip.close()
    final.close()
    print(f"✅ Video ready: {output_path}")

# ------------------------------------------------------------
# Main program
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
    
    check_paths()
    
    if choice == '1':
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
    
    print("🎉 Done! Import viral_captions.mp4 into Kdenlive for B-rolls/SFX!")

if __name__ == "__main__":
    main()
