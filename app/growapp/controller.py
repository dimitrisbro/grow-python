import logging
import threading
import time

logger = logging.getLogger(__name__)

# Sensor needs ~2s after boot before interrupt counts settle.
SENSOR_WARMUP = 5


class Controller:
    """Background loop: sample sensors, store readings, water, notify."""

    def __init__(self, config, hardware, db, notifier):
        self.config = config
        self.hardware = hardware
        self.db = db
        self.notifier = notifier
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._last_prune = 0

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def manual_water(self, channel):
        """Triggered from the web UI. Returns True if the dose ran."""
        settings = self.config["channels"][channel]
        ok = self.hardware.dose(channel, settings["pump_speed"], settings["pump_time"])
        if ok:
            self.db.add_event("manual_watering", channel, f"{settings['pump_time']}s @ speed {settings['pump_speed']}")
            self.notifier.send(f"💧 {settings['name']}: watered manually from the dashboard.")
        return ok

    def _run(self):
        time.sleep(SENSOR_WARMUP)
        interval = self.config["general"]["sample_interval"]
        logger.info("Controller started, sampling every %ss", interval)
        while not self._stop.is_set():
            try:
                self._sample_all()
                self._housekeeping()
            except Exception:
                logger.exception("Controller loop error")
            self._stop.wait(interval)

    def _sample_all(self):
        for channel in self.hardware.sensors:
            settings = self.config["channels"][channel]
            saturation, pulses, active = self.hardware.read(channel)
            self.db.add_reading(channel, saturation, pulses, active)

            if not active:
                self.notifier.send(
                    f"⚠️ {settings['name']}: moisture sensor is not responding. "
                    "Check the cable and that the sensor is in the soil.",
                    cooldown_key=f"inactive-{channel}",
                )
                continue

            if settings["auto_water"] and saturation < settings["water_level"]:
                self._auto_water(channel, settings, saturation)

            if saturation < settings["warn_level"]:
                sent = self.notifier.send(
                    f"🌵 {settings['name']} is very dry: {saturation:.0%} "
                    f"(warn level {settings['warn_level']:.0%}).",
                    cooldown_key=f"dry-{channel}",
                )
                if sent:
                    self.db.add_event("low_moisture", channel, f"saturation {saturation:.3f}")

    def _auto_water(self, channel, settings, saturation):
        now = time.time()
        count_today, last_ts = self.db.waterings_since(channel, now - 86400)

        if count_today >= settings["max_waterings_per_day"]:
            self.notifier.send(
                f"🚱 {settings['name']}: daily watering limit reached "
                f"({settings['max_waterings_per_day']}) but soil is still at {saturation:.0%}. "
                "Check the pump, tube and water reservoir.",
                cooldown_key=f"limit-{channel}",
            )
            return

        if last_ts is not None and now - last_ts < settings["watering_delay_minutes"] * 60:
            return  # let the previous dose soak in

        ok = self.hardware.dose(channel, settings["pump_speed"], settings["pump_time"])
        if ok:
            logger.info("Watered channel %s (saturation %.3f)", channel, saturation)
            self.db.add_event("watering", channel, f"saturation {saturation:.3f}")
            self.notifier.send(
                f"💧 {settings['name']}: soil at {saturation:.0%}, "
                f"watered for {settings['pump_time']}s."
            )
        else:
            logger.warning("Pump %s busy, dose skipped", channel)

    def _housekeeping(self):
        if time.time() - self._last_prune > 86400:
            self.db.prune(self.config["general"]["retention_days"])
            self._last_prune = time.time()
