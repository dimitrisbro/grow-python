import threading
import time
from datetime import timedelta

import gpiod
from gpiod.line import Edge

MOISTURE_1_PIN = 23
MOISTURE_2_PIN = 8
MOISTURE_3_PIN = 25
MOISTURE_INT_PIN = 4

GPIO_CHIP = "/dev/gpiochip0"


class Moisture(object):
    """Grow moisture sensor driver."""

    def __init__(self, channel=1, wet_point=None, dry_point=None):
        """Create a new moisture sensor.

        Uses a libgpiod edge event to count pulses on the GPIO pin corresponding to the selected channel.

        The moisture reading is given as pulses per second.

        :param channel: One of 1, 2 or 3. 4 can optionally be used to set up a sensor on the Int pin (BCM4)
        :param wet_point: Wet point in pulses/sec
        :param dry_point: Dry point in pulses/sec

        """
        self._gpio_pin = [MOISTURE_1_PIN, MOISTURE_2_PIN, MOISTURE_3_PIN, MOISTURE_INT_PIN][channel - 1]

        self._count = 0
        self._reading = 0
        self._history = []
        self._history_length = 200
        self._last_pulse = time.time()
        self._new_data = False
        self._wet_point = wet_point if wet_point is not None else 0.7
        self._dry_point = dry_point if dry_point is not None else 27.6
        self._time_last_reading = time.time()
        try:
            self._request = gpiod.request_lines(
                GPIO_CHIP,
                consumer=f"grow-moisture-{channel}",
                config={
                    self._gpio_pin: gpiod.LineSettings(
                        edge_detection=Edge.RISING,
                        debounce_period=timedelta(milliseconds=1),
                    )
                },
            )
        except OSError as e:
            if self._gpio_pin == 8:
                raise RuntimeError("""Unable to set up edge detection on BCM8.

Please ensure you add the following to /boot/config.txt and reboot:

dtoverlay=spi0-cs,cs0_pin=14 # Re-assign CS0 from BCM 8 so that Grow can use it

""")
            else:
                raise RuntimeError(f"Unable to set up edge detection on BCM{self._gpio_pin}: {e}")

        threading.Thread(target=self._watch, daemon=True).start()

        self._time_start = time.time()

    def _watch(self):
        # Blocks until an edge event is available - no polling, no CPU cost while idle.
        while True:
            for _event in self._request.read_edge_events():
                self._event_handler()

    def _event_handler(self):
        self._count += 1
        self._last_pulse = time.time()
        if self._time_elapsed >= 1.0:
            self._reading = self._count / self._time_elapsed
            self._history.insert(0, self._reading)
            self._history = self._history[:self._history_length]
            self._count = 0
            self._time_last_reading = time.time()
            self._new_data = True

    @property
    def history(self):
        history = []

        for moisture in self._history:
            saturation = float(moisture - self._dry_point) / self.range
            saturation = round(saturation, 3)
            history.append(max(0.0, min(1.0, saturation)))

        return history

    @property
    def _time_elapsed(self):
        return time.time() - self._time_last_reading

    def set_wet_point(self, value=None):
        """Set the sensor wet point.

        This is the watered, wet state of your soil.

        It should be set shortly after watering. Leave ~5 mins for moisture to permeate.

        :param value: Wet point value to set in pulses/sec, leave as None to set the last sensor reading.

        """
        self._wet_point = value if value is not None else self._reading

    def set_dry_point(self, value=None):
        """Set the sensor dry point.

        This is the unwatered, dry state of your soil.

        It should be set when the soil is dry to the touch.

        :param value: Dry point value to set in pulses/sec, leave as None to set the last sensor reading.

        """
        self._dry_point = value if value is not None else self._reading

    @property
    def moisture(self):
        """Return the raw moisture level.

        The value returned is the pulses/sec read from the soil moisture sensor.

        This value is inversely proportional to the amount of moisture.

        Full immersion in water is approximately 50 pulses/sec.

        Fully dry (in air) is approximately 900 pulses/sec.

        """
        self._new_data = False
        return self._reading

    @property
    def active(self):
        """Check if the moisture sensor is producing a valid reading."""
        return (time.time() - self._last_pulse) < 1.0 and self._reading > 0 and self._reading < 28

    @property
    def new_data(self):
        """Check for new reading.

        Returns True if moisture value has been updated since last reading moisture or saturation.

        """
        return self._new_data

    @property
    def range(self):
        """Return the range sensor range (wet - dry points)."""
        return self._wet_point - self._dry_point

    @property
    def saturation(self):
        """Return saturation as a float from 0.0 to 1.0.

        This value is calculated using the wet and dry points.

        """
        saturation = float(self.moisture - self._dry_point) / self.range
        saturation = round(saturation, 3)
        return max(0.0, min(1.0, saturation))
