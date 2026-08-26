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

from PIL import Image, ImageEnhance

log = logging.getLogger(__name__)

_SCALE = 4  # dev-mode window scale factor


class MatrixDisplay:
    def __init__(
        self,
        dev: bool = False,
        brightness: int = 50,
        rotation: int = 0,
        y_offset: int = 0,
    ) -> None:
        self._dev = dev
        self._brightness = brightness
        self._rotation = rotation if rotation in (0, 180) else 0
        self._y_offset = y_offset
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
        # Always 100 here — dimming is done in render() by scaling pixel values
        # instead (see set_brightness()). The library's own PWM brightness
        # control keeps the blue channel disproportionately bright at reduced
        # levels (observed on hardware: whites/yellows/teals all shift blue
        # at 60%, pure green unaffected — a channel-balance artifact, not
        # something scaling pixel values in software can reproduce, since
        # that multiplies R/G/B by the same factor and can't shift hue).
        opts.brightness = 100
        opts.gpio_slowdown = 5  # recommended for Pi 4
        opts.drop_privileges = False  # dropping mid-run breaks venv imports for subsequent modules
        opts.disable_hardware_pulsing = False

        self._matrix = RGBMatrix(options=opts)
        self._canvas = self._matrix.CreateFrameCanvas()
        self._width: int = self._matrix.width
        self._height: int = self._matrix.height
        log.info(
            "Matrix ready: %d×%d px, software brightness %d%% (hardware PWM fixed at 100%%)",
            self._width,
            self._height,
            brightness,
        )

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    # ── Brightness ───────────────────────────────────────────────────────────

    def set_brightness(self, brightness: int) -> None:
        """
        Update panel brightness at runtime (0-100), e.g. for a day/night schedule.

        Applied by scaling pixel values in render() (both on hardware and in
        dev mode) rather than the matrix's own PWM brightness control — see
        the comment in _init_hardware() for why.
        """
        self._brightness = max(0, min(100, brightness))

    # ── Rendering ─────────────────────────────────────────────────────────────

    def render(self, image: Image.Image) -> None:
        """Push *image* to the display (or dev preview)."""
        img = image.convert("RGB")
        if self._brightness < 100:
            img = ImageEnhance.Brightness(img).enhance(self._brightness / 100.0)
        if self._rotation == 180:
            img = img.rotate(180)
        if self._y_offset:
            shifted = Image.new("RGB", (self._width, self._height), (0, 0, 0))
            shifted.paste(img, (0, self._y_offset))
            img = shifted
        if self._dev:
            if self._pygame is not None and self._screen is not None:
                self._render_pygame(img)
            else:
                img.save("/tmp/transit_board_frame.png")
        else:
            # unsafe=True uses image.im.unsafe_ptrs, a Pillow internal removed in Pillow 12
            self._canvas.SetImage(img, unsafe=False)
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
