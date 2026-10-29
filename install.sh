#!/usr/bin/env bash
# Set up Video-Caption-Generator after a clone.
# Usage:
#   bash install.sh               full install
#   bash install.sh --no-system   skip system packages (already installed)
#   bash install.sh --uninstall   remove everything this script added
set -euo pipefail

APP="video-caption-generator"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/$APP"
VENV="$DATA_DIR/venv"
WHISPER_DIR="$DATA_DIR/whisper.cpp"
WHISPER_TAG="v1.7.6"
MODEL="small.en"
BIN_DIR="$HOME/.local/bin"
LAUNCHER="$BIN_DIR/$APP"
DESKTOP="${XDG_DATA_HOME:-$HOME/.local/share}/applications/$APP.desktop"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

uninstall() {
    info "Removing launcher, menu entry and $DATA_DIR"
    rm -f -- "$LAUNCHER" "$DESKTOP"
    # Only delete the folder this script made.
    case "$DATA_DIR" in
        */"$APP") rm -rf -- "$DATA_DIR" ;;
        *) die "Unexpected data folder: $DATA_DIR" ;;
    esac
    info "Done. System packages were left installed."
}

install_system() {
    local pkgs
    if command -v pacman >/dev/null; then
        pkgs=(ffmpeg imagemagick git cmake base-devel python)
        sudo pacman -S --needed --noconfirm "${pkgs[@]}"
    elif command -v apt-get >/dev/null; then
        pkgs=(ffmpeg imagemagick git cmake build-essential python3 python3-venv)
        sudo apt-get update
        sudo apt-get install -y "${pkgs[@]}"
    elif command -v dnf >/dev/null; then
        pkgs=(ffmpeg ImageMagick git cmake gcc-c++ make python3)
        sudo dnf install -y "${pkgs[@]}"
    elif command -v zypper >/dev/null; then
        pkgs=(ffmpeg ImageMagick git cmake gcc-c++ make python3)
        sudo zypper install -y "${pkgs[@]}"
    else
        die "Unknown distro. Install: ffmpeg imagemagick git cmake c++ compiler python3, then run with --no-system"
    fi
}

install_whisper() {
    if [ ! -d "$WHISPER_DIR/.git" ]; then
        info "Downloading whisper.cpp $WHISPER_TAG"
        git clone --depth 1 --branch "$WHISPER_TAG" \
            https://github.com/ggml-org/whisper.cpp.git "$WHISPER_DIR"
    fi
    if [ ! -x "$WHISPER_DIR/build/bin/whisper-cli" ]; then
        info "Building whisper.cpp"
        cmake -S "$WHISPER_DIR" -B "$WHISPER_DIR/build" -DCMAKE_BUILD_TYPE=Release >/dev/null
        cmake --build "$WHISPER_DIR/build" -j"$(nproc)" --config Release --target whisper-cli
    fi
    if [ ! -f "$WHISPER_DIR/models/ggml-$MODEL.bin" ]; then
        info "Downloading model $MODEL"
        bash "$WHISPER_DIR/models/download-ggml-model.sh" "$MODEL"
    fi
}

install_python() {
    info "Creating Python venv"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet -r "$REPO_DIR/requirements.txt"
}

install_launcher() {
    info "Adding launcher and menu entry"
    mkdir -p "$BIN_DIR" "$(dirname "$DESKTOP")"
    cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
export WHISPER_PATH="$WHISPER_DIR"
exec "$VENV/bin/python" "$REPO_DIR/caption_generator.py" "\$@"
EOF
    chmod 755 "$LAUNCHER"
    cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Video Caption Generator
Comment=Add styled captions to videos with whisper.cpp
Exec=$LAUNCHER
Terminal=true
Categories=AudioVideo;Video;
EOF
}

case "${1:-}" in
    --uninstall) uninstall; exit 0 ;;
    --no-system) skip_system=1 ;;
    "") skip_system=0 ;;
    *) die "Unknown option: $1" ;;
esac

[ "$(id -u)" -eq 0 ] && die "Run as your normal user, not root."
mkdir -p "$DATA_DIR"
chmod 700 "$DATA_DIR"
[ "$skip_system" -eq 1 ] || install_system
install_whisper
install_python
install_launcher
info "Done. Run: $APP  (make sure $BIN_DIR is in your PATH)"
