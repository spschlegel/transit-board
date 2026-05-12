"""
Matrix display driver.

In --dev mode: opens a pygame window (4× scaled) if pygame is available,
               otherwise saves each frame to /tmp/transit_board_frame.png.

In normal mode: drives the hzeller rgbmatrix library via Adafruit Hat PWM
                (requires the GPIO4→GPIO18 solder bridge and the E→8 bridge).
"""

from __future__ import annotations

import logging
from typing import Optional

from PIL import Image

log = logging.getLogger(__name__)

_SCALE = 4  # dev-mode window scale factor


class MatrixDisplay:
    def __init__(self, dev: bool = False, brightness: int = 50) -> None:
        self._dev = dev
        self._brightness = brightness
        self._pygame: Optional[object] = None
        self._screen: Optional[object] = None
        self._scale = _SCALE

        if dev:
            self._width = 128
            self._height = 64
            self._init_dev()
        else:
            self._init_hardware(brightness)

    # ── Init ──────────────────────────────────────────────────────────────────

    def _init_dev(self) -> None:
        try:
            import pygame  # type: ignore[import]

            pygame.init()
            w = self._width * self._scale
            h = self._height * self._scale
            self._screen = pygame.display.set_mode((w, h))
            pygame.display.set_caption("Transit Board — Dev Mode")
            self._pygame = pygame
            log.info(
                "Dev mode: pygame window %dx%d (matrix %dx%d × %dx scale)",
                w,
                h,
                self._width,
                self._height,
                self._scale,
            )
        except ImportError:
            self._pygame = None
            self._screen = None
            log.info(
                "Dev mode: pygame not installed — frames saved to /tmp/transit_board_frame.png"
            )

    def _init_hardware(self, brightness: int) -> None:
        try:
            from rgbmatrix import RGBMatrix, RGBMatrixOptions  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "rgbmatrix Python bindings not found. "
                "Run 'sudo make install-python' (Adafruit script) then "
                "'make install' to build and install them."
            ) from exc

        opts = RGBMatrixOptions()
        opts.rows = 64
        opts.cols = 64
        opts.chain_length = 2  # two panels chained → 128 wide
        opts.parallel = 1
        opts.hardware_mapping = "adafruit-hat-pwm"  # requires GPIO4→GPIO18 bridge
        opts.brightness = max(0, min(100, brightness))
        opts.gpio_slowdown = 4  # recommended for Pi 4
        opts.drop_privileges = True
        opts.disable_hardware_pulsing = False

        self._matrix = RGBMatrix(options=opts)
        self._canvas = self._matrix.CreateFrameCanvas()
        self._width: int = self._matrix.width
        self._height: int = self._matrix.height
        log.info("Matrix ready: %d×%d px, brightness %d%%", self._width, self._height, brightness)

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    # ── Rendering ─────────────────────────────────────────────────────────────

    def render(self, image: Image.Image) -> None:
        """Push *image* to the display (or dev preview)."""
        img = image.convert("RGB")
        if self._dev:
            if self._pygame is not None and self._screen is not None:
                self._render_pygame(img)
            else:
                img.save("/tmp/transit_board_frame.png")
        else:
            self._canvas.SetImage(img)
            self._canvas = self._matrix.SwapOnVSync(self._canvas)

    def _render_pygame(self, img: Image.Image) -> None:
        pygame = self._pygame  # type: ignore[assignment]
        # Drain events so the window stays responsive
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit(0)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_q:
                pygame.quit()
                raise SystemExit(0)

        raw = img.tobytes()
        surf = pygame.image.fromstring(raw, (img.width, img.height), "RGB")
        scaled = pygame.transform.scale(surf, (img.width * self._scale, img.height * self._scale))
        self._screen.blit(scaled, (0, 0))
        pygame.display.flip()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def clear(self) -> None:
        if not self._dev:
            self._matrix.Clear()

    def close(self) -> None:
        """Clear display and release resources."""
        self.clear()
        if self._dev and self._pygame is not None:
            try:
                self._pygame.quit()  # type: ignore[union-attr]
            except Exception:
                pass
