.PHONY: all bootstrap install-python install run dev lint format check

HZELLER_DIR := rpi-rgb-led-matrix

# ── Step 0 ── run once before anything else, as normal user ──────────────────
bootstrap:
	@echo "==> Installing system dependencies..."
	sudo apt-get update -qq
	sudo apt-get install -y git build-essential
	@echo "==> Installing uv..."
	curl -LsSf https://astral.sh/uv/install.sh | sh
	@echo ""
	@echo "Done. Restart your shell (or source ~/.bashrc), then run:"
	@echo "  sudo make install-python"

# ── Step 1 ── adafruit script: builds hzeller C lib + Python bindings ────────
# Interactive: select 'Bonnet', then 'Quality' (requires GPIO4->GPIO18 solder).
# Script will offer a reboot at the end — accept it.
# After reboot run:  make install
install-python:
	@echo "==> Running Adafruit RGB Matrix installer..."
	@echo "    When prompted, select:"
	@echo "      Interface : Adafruit RGB Matrix Bonnet"
	@echo "      Mode      : Quality  (you have soldered GPIO4 -> GPIO18)"
	@echo ""
	sudo bash adafruit/rgb-matrix.sh

# ── Step 2 ── Python env + hzeller bindings ───────────────────────────────────
install:
	@if [ ! -d "$(HZELLER_DIR)" ]; then \
		echo "ERROR: $(HZELLER_DIR)/ not found."; \
		echo "Run 'sudo make install-python' first, then reboot, then retry."; \
		exit 1; \
	fi
	@echo "==> Creating venv and syncing dependencies..."
	uv sync --group dev
	@echo "==> Patching hzeller bindings for Python 3.12+ (distutils removed)..."
	sed -i 's/from distutils.core import/from setuptools import/g' ./$(HZELLER_DIR)/bindings/python/setup.py
	@echo "==> Installing rpi-rgb-led-matrix Python bindings..."
	uv pip install setuptools
	uv pip install ./$(HZELLER_DIR)/bindings/python/
	@echo ""
	@echo "Installation complete. Next:"
	@echo "  cp config.toml.example config.toml   # fill in stop IDs"
	@echo "  cp .env.example .env                 # add MBTA_API_KEY"
	@echo "  make run"

# ── Run ───────────────────────────────────────────────────────────────────────
run:
	uv run python -m transit_board

# Dev mode: mock data, no matrix hardware required
dev:
	uv run python -m transit_board --dev

# ── Code quality ──────────────────────────────────────────────────────────────
lint:
	uv run ruff check .

format:
	uv run ruff format .

check: lint
	uv run ruff format --check .
