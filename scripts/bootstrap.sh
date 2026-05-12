#!/usr/bin/env bash
# Transit Board — one-time system bootstrap
# Run as normal user (sudo is invoked internally where needed)
set -euo pipefail

echo "==> Transit Board Bootstrap"
echo ""

# System packages
echo "--> apt: installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y \
    git \
    build-essential \
    python3-dev \
    libopenjp2-7 \
    libtiff5-dev \
    libfreetype6-dev

# uv
if command -v uv &>/dev/null; then
    echo "--> uv already installed: $(uv --version)"
else
    echo "--> Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    echo ""
    echo "    uv installed. Restart your shell (or: source ~/.bashrc / ~/.zshrc)"
fi

echo ""
echo "Bootstrap complete. Next steps (in order):"
echo ""
echo "  1. Restart shell if uv was just installed"
echo "  2. sudo make install-python   # Adafruit script: builds hzeller C lib"
echo "     (Select: Adafruit RGB Matrix Bonnet → Quality mode, then reboot)"
echo "  3. make install               # uv sync + hzeller Python bindings"
echo "  4. cp config.toml.example config.toml   # edit with your stop IDs"
echo "  5. cp .env.example .env                 # add MBTA_API_KEY"
echo "  6. make run"
