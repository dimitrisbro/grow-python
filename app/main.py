#!/usr/bin/env python3
import argparse
import logging
import pathlib

from growapp.config import load_config
from growapp.controller import Controller
from growapp.database import Database
from growapp.hardware import Hardware
from growapp.notifier import TelegramNotifier
from growapp.webapp import create_app


def main():
    parser = argparse.ArgumentParser(description="Grow HAT Mini monitor")
    parser.add_argument(
        "--config",
        default=pathlib.Path(__file__).parent / "config.yaml",
        help="Path to config.yaml",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = load_config(args.config)

    db_path = pathlib.Path(config["general"]["database"])
    db_path.parent.mkdir(parents=True, exist_ok=True)

    hardware = Hardware(config["channels"])
    db = Database(db_path)
    notifier = TelegramNotifier(config["telegram"])

    controller = Controller(config, hardware, db, notifier)
    controller.start()
    notifier.send("🌱 Grow monitor started.")

    app = create_app(config, hardware, db, controller)
    # threaded=True so API calls work while a blocking pump dose runs.
    app.run(
        host=config["general"]["host"],
        port=config["general"]["port"],
        threaded=True,
    )


if __name__ == "__main__":
    main()
