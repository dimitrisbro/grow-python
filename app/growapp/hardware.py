"""Hardware access with a mock fallback.

On the Pi this wraps the growhat Moisture/Pump drivers. On any machine
without RPi.GPIO (development laptop, CI) it falls back to a mock that
produces a slowly drying saturation curve so the rest of the app can be
exercised end to end.
"""

import logging
import random
import time

logger = logging.getLogger(__name__)

try:
    from grow.moisture import Moisture
    from grow.pump import Pump

    HARDWARE_AVAILABLE = True
except (ImportError, RuntimeError):
    HARDWARE_AVAILABLE = False


class MockSensor:
    def __init__(self, channel, wet_point, dry_point):
        self._saturation = random.uniform(0.4, 0.9)

    @property
    def active(self):
        return True

    @property
    def saturation(self):
        # Dry out slowly, with a little noise.
        self._saturation = max(0.0, self._saturation - random.uniform(0.0005, 0.002))
        return round(self._saturation, 3)

    @property
    def moisture(self):
        return round(28 - self._saturation * 27, 2)

    def water(self):
        self._saturation = min(1.0, self._saturation + 0.25)


class MockPump:
    def __init__(self, channel, sensor=None):
        self._sensor = sensor

    def dose(self, speed, timeout=0.1, blocking=True):
        time.sleep(timeout if blocking else 0)
        if self._sensor is not None:
            self._sensor.water()
        return True


class Hardware:
    """Owns the three sensor/pump pairs."""

    def __init__(self, channels_config):
        self.mock = not HARDWARE_AVAILABLE
        if self.mock:
            logger.warning("RPi.GPIO not available - running with mock hardware")

        self.sensors = {}
        self.pumps = {}
        for channel, settings in channels_config.items():
            if not settings["enabled"]:
                continue
            if self.mock:
                sensor = MockSensor(channel, settings["wet_point"], settings["dry_point"])
                self.sensors[channel] = sensor
                self.pumps[channel] = MockPump(channel, sensor)
            else:
                self.sensors[channel] = Moisture(
                    channel=channel,
                    wet_point=settings["wet_point"],
                    dry_point=settings["dry_point"],
                )
                self.pumps[channel] = Pump(channel=channel)

    def read(self, channel):
        """Return (saturation, pulses_per_sec, sensor_active) for a channel."""
        sensor = self.sensors[channel]
        return sensor.saturation, sensor.moisture, sensor.active

    def dose(self, channel, speed, seconds):
        """Run a pump for `seconds`. Blocking; the grow lib serialises pumps
        with a global lock so two pumps never run at once (brownout protection)."""
        return self.pumps[channel].dose(speed, timeout=seconds, blocking=True)
