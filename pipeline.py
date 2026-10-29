#!/usr/bin/env python3
"""
Muzasio pipeline.py — master orchestrator
All files must be in the same directory: pipeline.py, caption_generator.py,
config_manager.py, text_clip.py, engaging.py, gaming.py, podcast.py, cinematic.py

Stages per clip:
  normalize → jump cuts → audio cleanup → color grade → transcribe → styled captions

Assembly:
  beat-synced xfade concat → PNG overlays → watermark → sidechain BGM

Usage:
  python pipeline.py clip1.mp4 [clip2.mp4 ...] [output.mp4]
  python pipeline.py clip1.mp4 --style gaming
  python pipeline.py clip1.mp4 final.mp4 --style cinematic --transparent

Styles: engaging | gaming | podcast | cinematic | asmr
"""

import os, sys, json, re, subprocess, shutil, argparse, shlex
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

try:
    from caption_generator import (
        check_paths,
        voice_to_srt,
        generate_styled_video,
        parse_srt,
        format_time,
    )
except ImportError as e:
    sys.exit(f"caption_generator.py not in same directory: {e}")

try:
    from renderModule import render_captions_only
except (ImportError, SyntaxError):
    render_captions_only = None

try:
    import librosa
    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False

from config_manager import CONFIG

P = CONFIG.get("pipeline", {})

VALID_STYLES = {"engaging", "gaming", "podcast", "cinematic", "asmr"}

GRADE_PRESETS = {
    "gaming":  "eq=contrast=1.10:saturation=1.50:brightness=0.02:gamma=0.95",
    "cyber":   "eq=contrast=1.15:saturation=0.90:brightness=0.01:gamma=1.05,hue=h=-8:s=1",
    "neutral": "eq=contrast=1.05:saturation=1.10:brightness=0.01",
}

# ─── utils ────────────────────────────────────────────────────────────────────

def run(cmd: str, check=True) -> subprocess.CompletedProcess:
    r = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True)
    if check and r.returncode != 0:
        print(f"[ffmpeg error]\n{r.stderr[-2000:]}")
        sys.exit(1)
    return r

def probe(path: str) -> dict:
    r = run(f'ffprobe -v quiet -print_format json -show_streams -show_format "{path}"')
    return json.loads(r.stdout)

def dur(path: str) -> float:
    return float(probe(path)["format"]["duration"])

def mkdirs(*paths):
    for p in paths:
        Path(p).mkdir(parents=True, exist_ok=True)

# ─── orientation detection ────────────────────────────────────────────────────

def detect_orientation(src: str) -> tuple:
    """
    Returns ("vertical", w, h) or ("horizontal", w, h).
    Accounts for rotation metadata (phones record rotated streams).
    Canonical dims are always (width, height) as they will appear on screen.
    """
    info = probe(src)
    vid  = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if vid is None:
        sys.exit(f"No video stream found in {src}")

    raw_w = int(vid["width"])
    raw_h = int(vid["height"])

    # rotation tag flips the display dimensions (90 or 270 degrees)
    rotation = 0
    tags = vid.get("tags", {})
    if "rotate" in tags:
        rotation = abs(int(tags["rotate"]))
    # also check side_data_list for displaymatrix rotation
    for sd in vid.get("side_data_list", []):
        if sd.get("side_data_type") == "Display Matrix" and "rotation" in sd:
            rotation = abs(int(float(sd["rotation"])))
            break

    if rotation in (90, 270):
        w, h = raw_h, raw_w
    else:
        w, h = raw_w, raw_h

    orientation = "vertical" if h > w else "horizontal"
    return orientation, w, h


# ─── normalize ────────────────────────────────────────────────────────────────

def normalize_clip(src: str, dst: str, orientation: str, src_w: int, src_h: int):
    fps = P.get("fps", CONFIG.get("video", {}).get("fps", 60))

    # Target resolution: respect source orientation, snap to standard dims
    if orientation == "vertical":
        # 9:16 → 1080x1920 (Shorts/Reels/TikTok)
        tw, th = 1080, 1920
    else:
        # 16:9 → 1920x1080
        tw, th = 1920, 1080

    run(
        f'ffmpeg -y -i "{src}" '
        f'-vf "scale={tw}:{th}:force_original_aspect_ratio=decrease,'
        f'pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color=black" '
        f'-r {fps} -c:v libx264 -preset fast -crf 18 '
        f'-c:a aac -ar 48000 -ac 2 "{dst}"'
    )

# ─── jump cuts ────────────────────────────────────────────────────────────────

def detect_silences(path: str) -> list:
    jc = P.get("jump_cuts", {})
    out = run(
        f'ffmpeg -i "{path}" '
        f'-af "silencedetect=noise={jc.get("threshold", "-35dB")}:d={jc.get("min_dur", 0.30)}" '
        f'-f null -', check=False
    ).stderr
    starts = [float(x) for x in re.findall(r'silence_start:\s*([\d.]+)', out)]
    ends   = [float(x) for x in re.findall(r'silence_end:\s*([\d.]+)', out)]
    return list(zip(starts, ends))

def jump_cut_clip(src: str, dst: str, tmp: str):
    jc       = P.get("jump_cuts", {})
    pad      = jc.get("pad", 0.05)
    silences = detect_silences(src)
    total    = dur(src)

    if not silences:
        shutil.copy(src, dst)
        return

    keep, prev = [], 0.0
    for si, se in silences:
        seg_end = max(prev, si - pad)
        if seg_end > prev + 0.1:
            keep.append((prev, seg_end))
        prev = se + pad
    if total - prev > 0.1:
        keep.append((prev, total))

    if not keep:
        shutil.copy(src, dst)
        return

    segs = []
    for i, (s, e) in enumerate(keep):
        seg = f"{tmp}/jc_{Path(src).stem}_{i:03d}.mp4"
        run(f'ffmpeg -y -ss {s:.3f} -to {e:.3f} -i "{src}" '
            f'-c:v libx264 -preset fast -crf 18 -c:a aac -avoid_negative_ts 1 "{seg}"')
        segs.append(seg)

    lst = f"{tmp}/jc_{Path(src).stem}.txt"
    with open(lst, "w") as f:
        for sf in segs:
            f.write(f"file '{os.path.abspath(sf)}'\n")
    run(f'ffmpeg -y -f concat -safe 0 -i "{lst}" -c copy "{dst}"')
    print(f"    removed {len(silences)} silence(s), kept {len(keep)} segment(s)")

# ─── audio ────────────────────────────────────────────────────────────────────

def process_audio(src: str, dst: str):
    ac = P.get("audio", {})
    filters = []
    if ac.get("denoise", True):
        filters.append("afftdn=nf=-25:nt=w")
    if ac.get("normalize", True):
        filters.append("loudnorm=I=-16:LRA=11:TP=-1.5")
    if not filters:
        shutil.copy(src, dst)
        return
    run(f'ffmpeg -y -i "{src}" -af "{",".join(filters)}" -c:v copy "{dst}"')

# ─── color grade ──────────────────────────────────────────────────────────────

# Vertical (mobile) grade: punchier contrast/saturation for small screens
GRADE_PRESETS_VERTICAL = {
    "gaming":  "eq=contrast=1.15:saturation=1.70:brightness=0.02:gamma=0.92",
    "cyber":   "eq=contrast=1.20:saturation=0.95:brightness=0.01:gamma=1.05,hue=h=-10:s=1",
    "neutral": "eq=contrast=1.08:saturation=1.20:brightness=0.01",
}

def color_grade(src: str, dst: str, orientation: str = "horizontal"):
    cg  = P.get("color_grade", {})
    lut = cg.get("lut")
    if lut and Path(lut).exists():
        vf = f"lut3d='{lut}'"
    else:
        preset = cg.get("preset", "neutral")
        table  = GRADE_PRESETS_VERTICAL if orientation == "vertical" else GRADE_PRESETS
        vf     = table.get(preset, table["neutral"])
    run(f'ffmpeg -y -i "{src}" -vf "{vf}" -c:a copy "{dst}"')

# ─── beat detection ───────────────────────────────────────────────────────────

def detect_beats(bgm_path: str) -> list:
    if not HAS_LIBROSA:
        print("    librosa not installed — beat sync skipped")
        return []
    y, sr    = librosa.load(bgm_path, mono=True, res_type="kaiser_fast")
    _, beats = librosa.beat.beat_track(y=y, sr=sr)
    times    = librosa.frames_to_time(beats, sr=sr).tolist()
    if len(times) > 1:
        print(f"    {len(times)} beats @ ~{60 / (times[1] - times[0]):.0f} BPM")
    return times

def snap_to_beat(offset: float, beats: list) -> float:
    return min(beats, key=lambda b: abs(b - offset)) if beats else offset

# ─── concat with beat-synced xfade ────────────────────────────────────────────

def concat_xfade(clips: list, dst: str, beats: list = None):
    if len(clips) == 1:
        shutil.copy(clips[0], dst)
        return

    tr      = P.get("transition", {})
    tr_type = tr.get("type", "zoomin")
    tr_dur  = float(tr.get("duration", 0.5))
    sync    = tr.get("beat_sync", True) and beats
    n       = len(clips)
    durs    = [dur(c) for c in clips]
    inputs  = " ".join(f'-i "{c}"' for c in clips)

    vparts = []
    offset = durs[0] - tr_dur
    if sync:
        offset = snap_to_beat(offset, beats)
    vparts.append(
        f"[0:v][1:v]xfade=transition={tr_type}:duration={tr_dur}:offset={offset:.3f}[xf1]"
    )
    for i in range(2, n):
        offset += durs[i-1] - tr_dur
        if sync:
            offset = snap_to_beat(offset, beats)
        vparts.append(
            f"[xf{i-1}][{i}:v]xfade=transition={tr_type}:"
            f"duration={tr_dur}:offset={offset:.3f}[xf{i}]"
        )

    acat = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[outa]"
    fg   = ";".join(vparts + [acat])
    run(
        f'ffmpeg -y {inputs} -filter_complex "{fg}" '
        f'-map "[xf{n-1}]" -map "[outa]" '
        f'-c:v libx264 -crf 18 -preset fast -c:a aac "{dst}"'
    )

# ─── PNG overlays ─────────────────────────────────────────────────────────────

def apply_png_overlays(src: str, dst: str):
    overlays = P.get("png_overlays", [])
    if not overlays:
        shutil.copy(src, dst)
        return

    inputs = f'-i "{src}"'
    parts  = ["[0:v]null[b0]"]
    prev   = "b0"

    for i, ov in enumerate(overlays):
        idx   = i + 1
        s, e  = ov.get("start", 0), ov.get("end", 999)
        x, y  = ov.get("x", 0), ov.get("y", 0)
        sc    = ov.get("scale")
        label = f"p{i}"
        nxt   = f"b{i+1}"
        inputs += f' -i "{ov["path"]}"'
        scale_f = f"scale={sc}:-1," if sc else ""
        parts.append(f"[{idx}:v]{scale_f}setpts=PTS-STARTPTS[{label}]")
        parts.append(
            f"[{prev}][{label}]overlay={x}:{y}:enable='between(t,{s},{e})'[{nxt}]"
        )
        prev = nxt

    run(f'ffmpeg -y {inputs} -filter_complex "{";".join(parts)}" '
        f'-map "[{prev}]" -map "0:a" -c:a copy "{dst}"')

# ─── sidechain BGM ────────────────────────────────────────────────────────────

def mix_bgm(src: str, bgm: str, dst: str):
    ac   = P.get("audio", {})
    bvol = ac.get("bgm_volume", 0.20)
    d    = dur(src)

    if ac.get("sidechain", True):
        fg = (
            f"[0:a]asplit=2[vocal][sc];"
            f"[1:a]volume={bvol},aloop=loop=-1:size=2000000000,"
            f"atrim=0:{d:.3f},asetpts=PTS-STARTPTS[bgm_raw];"
            f"[bgm_raw][sc]sidechaincompress="
            f"threshold=0.03:ratio=8:attack=50:release=600:level_sc=0.8[bgm_d];"
            f"[vocal][bgm_d]amix=inputs=2:duration=first[outa]"
        )
    else:
        fg = (
            f"[0:a]volume=1.0[vocal];"
            f"[1:a]volume={bvol},aloop=loop=-1:size=2000000000,"
            f"atrim=0:{d:.3f},asetpts=PTS-STARTPTS[bgm_raw];"
            f"[vocal][bgm_raw]amix=inputs=2:duration=first[outa]"
        )
    run(
        f'ffmpeg -y -i "{src}" -i "{bgm}" -filter_complex "{fg}" '
        f'-map 0:v -map "[outa]" -c:v copy -c:a aac -shortest "{dst}"'
    )

# ─── watermark ───────────────────────────────────────────────────────────────

def add_watermark(src: str, dst: str, orientation: str = "horizontal"):
    wm = P.get("watermark", {})
    if not wm.get("enabled", True):
        shutil.copy(src, dst)
        return

    # vertical: bottom-center (thumb safe zone); horizontal: top-right
    if orientation == "vertical":
        default_pos = "bottom-center"
    else:
        default_pos = "top-right"

    pos_key = wm.get("position", default_pos)
    pos_map = {
        "top-right":     "x=w-tw-24:y=24",
        "top-left":      "x=24:y=24",
        "bottom-right":  "x=w-tw-24:y=h-th-24",
        "bottom-left":   "x=24:y=h-th-24",
        "bottom-center": "x=(w-tw)/2:y=h-th-60",
        "top-center":    "x=(w-tw)/2:y=24",
    }
    pos = pos_map.get(pos_key, pos_map["top-right"])
    ff  = CONFIG.get("font", {}).get("path", "")
    txt = wm.get("text", "")
    # slightly larger on vertical for readability on mobile
    fsize = 48 if orientation == "vertical" else 40
    run(
        f'ffmpeg -y -i "{src}" '
        f'-vf "drawtext=text=\'{txt}\':fontfile={ff}:'
        f'fontcolor=white:fontsize={fsize}:alpha=0.55:{pos}" '
        f'-c:a copy "{dst}"'
    )

# ─── per-clip stage ───────────────────────────────────────────────────────────

def process_clip(src: str, idx: int, style: str, tmp: str) -> str:
    tag  = f"{idx:02d}"
    stem = Path(src).stem

    orientation, src_w, src_h = detect_orientation(src)
    print(f"\n[{idx+1}] {stem}  [{orientation} {src_w}x{src_h}]")

    # Adjust caption config for vertical: tighter margins, keep font readable
    if orientation == "vertical":
        CONFIG["caption_bottom_margin"] = CONFIG.get("caption_bottom_margin_vertical",
                                                      CONFIG.get("caption_bottom_margin", 120))
        for section in ("gaming", "podcast", "cinematic", "asmr"):
            if section in CONFIG and "margin" in CONFIG[section]:
                CONFIG[section]["margin"] = CONFIG[section].get(
                    "margin_vertical", [20, 20, 20, 20]
                )
    else:
        CONFIG["caption_bottom_margin"] = CONFIG.get("caption_bottom_margin", 80)

    norm = f"{tmp}/{tag}_norm.mp4"
    print("  normalize")
    normalize_clip(src, norm, orientation, src_w, src_h)
    current = norm

    if P.get("jump_cuts", {}).get("enabled", True):
        jc_out = f"{tmp}/{tag}_jc.mp4"
        print("  jump cuts")
        jump_cut_clip(current, jc_out, tmp)
        current = jc_out

    audio_out = f"{tmp}/{tag}_audio.mp4"
    print("  audio")
    process_audio(current, audio_out)
    current = audio_out

    graded = f"{tmp}/{tag}_grade.mp4"
    print("  color grade")
    color_grade(current, graded, orientation)
    current = graded

    wav = f"{tmp}/{tag}_raw.wav"
    srt = f"{tmp}/{tag}.srt"
    print("  transcribe")
    run(f'ffmpeg -y -i "{current}" -vn -ar 16000 -ac 1 "{wav}"')
    voice_to_srt(wav, srt)

    captioned = f"{tmp}/{tag}_cap.mp4"
    print(f"  captions [{style}]")
    CONFIG["caption_style"] = style
    generate_styled_video(current, srt, captioned)

    return captioned, orientation

# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Muzasio video pipeline — fully automated",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python pipeline.py clip1.mp4\n"
            "  python pipeline.py clip1.mp4 clip2.mp4 final.mp4 --style gaming\n"
            "  python pipeline.py clip1.mp4 --style cinematic --transparent\n"
        )
    )
    parser.add_argument("inputs", nargs="+", help="Input video files. Last arg treated as output if it ends with .mp4 and doesn't exist.")
    parser.add_argument("--style", choices=sorted(VALID_STYLES), default=None,
                        help="Caption style (default: reads caption_style from config.json)")
    parser.add_argument("--transparent", action="store_true",
                        help="Also export caption frames as alpha PNG sequence via renderModule")
    args = parser.parse_args()

    # Split inputs vs output filename
    inputs = args.inputs
    output_name = "final.mp4"
    if len(inputs) > 1 and inputs[-1].endswith(".mp4") and not Path(inputs[-1]).exists():
        output_name = inputs[-1]
        inputs = inputs[:-1]

    # Validate all input files exist
    for f in inputs:
        if not Path(f).exists():
            sys.exit(f"File not found: {f}")

    # Resolve style: CLI flag > config.json > fallback to engaging
    style = args.style
    if style is None:
        style = CONFIG.get("caption_style", "engaging")
    if style not in VALID_STYLES:
        sys.exit(f"Unknown style '{style}'. Valid: {', '.join(sorted(VALID_STYLES))}")

    tmp = P.get("temp_dir", ".vtmp")
    out = P.get("output_dir", "output")
    mkdirs(tmp, out)

    check_paths()

    print(f"Style: {style}")
    print(f"Clips: {len(inputs)}")
    print(f"Output: {out}/{output_name}\n")

    results     = [process_clip(c, i, style, tmp) for i, c in enumerate(inputs)]
    processed   = [r[0] for r in results]
    orientations = [r[1] for r in results]
    # Use the majority orientation for assembly stages; prefer vertical if mixed
    final_orientation = "vertical" if orientations.count("vertical") >= len(orientations) / 2 else "horizontal"
    print(f"\nOrientation: {final_orientation}")

    beats = []
    bgm   = P.get("audio", {}).get("bgm_path")
    if bgm and Path(bgm).exists() and P.get("transition", {}).get("beat_sync", True):
        print("\nbeat detection...")
        beats = detect_beats(bgm)

    print("\nconcatenate + transitions")
    concat_out = f"{tmp}/concat.mp4"
    concat_xfade(processed, concat_out, beats)
    current = concat_out

    if P.get("png_overlays"):
        print("PNG overlays")
        ov_out = f"{tmp}/overlay.mp4"
        apply_png_overlays(current, ov_out)
        current = ov_out

    print("watermark")
    wm_out = f"{tmp}/wm.mp4"
    add_watermark(current, wm_out, final_orientation)
    current = wm_out

    final = f"{out}/{output_name}"
    if bgm and Path(bgm).exists():
        print("BGM + sidechain ducking")
        mix_bgm(current, bgm, final)
    else:
        shutil.copy(current, final)

    if args.transparent:
        if render_captions_only:
            print("\nexporting transparent caption frames...")
            full_wav = f"{tmp}/final_audio.wav"
            full_srt = f"{tmp}/final.srt"
            run(f'ffmpeg -y -i "{final}" -vn -ar 16000 -ac 1 "{full_wav}"')
            voice_to_srt(full_wav, full_srt)
            render_captions_only(final, full_srt, f"{out}/caption_frames")
        else:
            print("--transparent skipped: renderModule.py not found")

    shutil.rmtree(tmp, ignore_errors=True)

    info = probe(final)
    vid  = next(s for s in info["streams"] if s["codec_type"] == "video")
    print(
        f"\n✓ {final}  |  "
        f"{vid['width']}x{vid['height']} @ {vid.get('r_frame_rate', '?')}fps  |  "
        f"{dur(final):.1f}s"
    )


if __name__ == "__main__":
    main()
