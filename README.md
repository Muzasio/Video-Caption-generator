# Video-Caption-Generator

> **Archived.** This project is finished and no longer updated. I now use [Remotion](https://www.remotion.dev/) and its captions package for this job.

Adds styled, animated captions to videos. Speech is turned into text locally with [whisper.cpp](https://github.com/ggml-org/whisper.cpp), and the captions are drawn with MoviePy 2.x.

## Features

- Local speech-to-text with whisper.cpp (no cloud), output as SRT
- 5 caption styles:

| Style | Look |
|---|---|
| engaging | Big bold words, pop and scale (viral / short-form) |
| gaming | Pixel font, shake, slide and glitch effects |
| podcast | Clean text with speaker tags |
| cinematic | Letterbox bars, elegant serif text |
| asmr | Soft, calm text |

- Or turn a text file into an SRT and caption a video with it
- `pipeline.py`: full auto edit (normalize, jump cuts, audio cleanup, color grade, captions, transitions, watermark, background music)

## Install

```bash
git clone https://github.com/Muzasio/Video-Caption-generator.git
cd Video-Caption-generator
bash install.sh
```

The installer:
- installs system packages (Arch, Debian/Ubuntu, Fedora, openSUSE): ffmpeg, imagemagick, git, cmake, compiler
- builds whisper.cpp and downloads the `small.en` model into `~/.local/share/video-caption-generator/`
- makes a Python venv with the packages from `requirements.txt`
- adds the `video-caption-generator` command and a menu entry

Options: `--no-system` (skip system packages), `--uninstall` (remove it all).

## Use

```bash
video-caption-generator
```

It asks for a video/audio file (or a text file) and a style. It writes `captions.srt` and `viral_captions.mp4` in the folder you run it from.

Full auto edit:

```bash
~/.local/share/video-caption-generator/venv/bin/python pipeline.py clip1.mp4 clip2.mp4 out.mp4 --style gaming
```

## Settings

Edit `config.json`:
- `font.path`: font file for each style. Change these to fonts you have installed.
- `pipeline.watermark.text`: your watermark text (`YOUR_NAME` by default).
- To use a whisper.cpp build in another folder, set `WHISPER_PATH=/path/to/whisper.cpp`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Whisper binary not found` | Run `bash install.sh --no-system` again, or set `WHISPER_PATH` |
| Font error / plain text | Fix `font.path` in `config.json` |
| `command not found` | Add `~/.local/bin` to your PATH |

## License

MIT
