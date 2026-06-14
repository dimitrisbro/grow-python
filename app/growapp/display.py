"""ST7735 HAT display driver.

Runs in a background thread and renders a 3-column moisture overview
on the Grow HAT Mini's 160x80 display. Falls back silently if the
display hardware or PIL are not available.
"""
import logging
import threading
import time

logger = logging.getLogger(__name__)

try:
    import ST7735
    from PIL import Image, ImageDraw, ImageFont
    from fonts.ttf import RobotoMedium as UserFont
    _LIBS_OK = True
except ImportError:
    _LIBS_OK = False

W, H = 160, 80

C_BG     = (0,   0,   0)
C_WHITE  = (255, 255, 255)
C_DIM    = (60,  70,  80)
C_GREEN  = (99,  255, 124)
C_YELLOW = (254, 219, 82)
C_RED    = (247, 0,   63)


def _sat_color(sat, warn, water):
    if sat is None:
        return C_DIM
    if sat < warn:
        return C_RED
    if sat < water:
        return C_YELLOW
    return C_GREEN


class GrowDisplay:
    def __init__(self, config, hardware):
        self._config = config
        self._hardware = hardware
        self._running = False
        self._thread = None
        self._ok = False

        if not _LIBS_OK:
            logger.warning("ST7735/PIL not available — display disabled")
            return
        try:
            self._disp = ST7735.ST7735(
                port=0, cs=1, dc=9, backlight=12, rotation=270, spi_speed_hz=80000000
            )
            self._disp.begin()
            self._img  = Image.new("RGB", (W, H), C_BG)
            self._draw = ImageDraw.Draw(self._img)
            self._font_sm = ImageFont.truetype(UserFont, 10)
            self._font_md = ImageFont.truetype(UserFont, 14)
            self._ok = True
        except Exception as e:
            logger.warning("Display init failed: %s", e)

    def start(self):
        if not self._ok:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="grow-display")
        self._thread.start()
        logger.info("HAT display started")

    def stop(self):
        self._running = False

    def _render(self):
        channels = [
            (ch, cfg)
            for ch, cfg in self._config["channels"].items()
            if cfg["enabled"] and ch in self._hardware.sensors
        ]
        if not channels:
            return

        draw = self._draw
        draw.rectangle((0, 0, W, H), C_BG)

        col_w = W // len(channels)
        BAR_TOP    = 34
        BAR_BOTTOM = H - 4
        BAR_H      = BAR_BOTTOM - BAR_TOP

        for i, (ch, cfg) in enumerate(channels):
            x0 = i * col_w
            sat, _, _ = self._hardware.read(ch)
            color = _sat_color(sat, cfg["warn_level"], cfg["water_level"])

            # Name
            draw.text((x0 + 3, 2), cfg["name"][:7], font=self._font_sm, fill=C_WHITE)

            # Saturation %
            pct = f"{int(sat * 100)}%" if sat is not None else "—"
            draw.text((x0 + 3, 14), pct, font=self._font_md, fill=color)

            # Vertical bar background
            bx = x0 + 6
            bw = col_w - 14
            draw.rectangle((bx, BAR_TOP, bx + bw, BAR_BOTTOM), C_DIM)

            # Fill
            if sat:
                fill_h = int(BAR_H * min(sat, 1.0))
                draw.rectangle((bx, BAR_BOTTOM - fill_h, bx + bw, BAR_BOTTOM), color)

            # Threshold lines
            for level, line_color in (
                (cfg["warn_level"],  C_RED),
                (cfg["water_level"], C_YELLOW),
            ):
                ly = BAR_BOTTOM - int(BAR_H * level)
                draw.line((bx, ly, bx + bw, ly), line_color, width=1)

        self._disp.display(self._img)

    def _loop(self):
        while self._running:
            try:
                self._render()
            except Exception as e:
                logger.warning("Display render error: %s", e)
            time.sleep(2)
