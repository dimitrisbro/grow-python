import pathlib

import yaml

DEFAULT_CHANNEL = {
    "name": None,
    "enabled": True,
    "wet_point": 0.7,
    "dry_point": 27.6,
    "water_level": 0.3,
    "warn_level": 0.2,
    "auto_water": True,
    "pump_speed": 0.7,
    "pump_time": 0.7,
    "watering_delay_minutes": 30,
    "max_waterings_per_day": 6,
}

DEFAULT_GENERAL = {
    "sample_interval": 300,
    "retention_days": 90,
    "database": "grow.db",
    "host": "0.0.0.0",
    "port": 8080,
}

DEFAULT_TELEGRAM = {
    "enabled": False,
    "bot_token": "",
    "chat_id": "",
    "alert_cooldown_minutes": 360,
}


def load_config(path):
    raw = yaml.safe_load(pathlib.Path(path).read_text()) or {}

    config = {
        "general": {**DEFAULT_GENERAL, **(raw.get("general") or {})},
        "telegram": {**DEFAULT_TELEGRAM, **(raw.get("telegram") or {})},
        "channels": {},
    }

    for channel in (1, 2, 3):
        overrides = (raw.get("channels") or {}).get(channel) or {}
        settings = {**DEFAULT_CHANNEL, **overrides}
        if settings["name"] is None:
            settings["name"] = f"Plant {channel}"
        config["channels"][channel] = settings

    return config
