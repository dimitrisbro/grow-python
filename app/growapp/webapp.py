from flask import Flask, jsonify, render_template, request


def create_app(config, hardware, db, controller):
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/status")
    def status():
        latest = db.latest_readings()
        channels = []
        for channel, settings in config["channels"].items():
            if channel not in hardware.sensors:
                continue
            reading = latest.get(channel)
            channels.append({
                "channel": channel,
                "name": settings["name"],
                "saturation": reading["saturation"] if reading else None,
                "active": bool(reading["active"]) if reading else False,
                "ts": reading["ts"] if reading else None,
                "water_level": settings["water_level"],
                "warn_level": settings["warn_level"],
                "auto_water": settings["auto_water"],
            })
        return jsonify({"channels": channels, "mock": hardware.mock})

    @app.route("/api/history/<int:channel>")
    def history(channel):
        hours = request.args.get("hours", default=24, type=int)
        hours = max(1, min(hours, 24 * 30))
        return jsonify(db.history(channel, hours=hours))

    @app.route("/api/events")
    def events():
        return jsonify(db.recent_events())

    @app.route("/api/water/<int:channel>", methods=["POST"])
    def water(channel):
        if channel not in hardware.pumps:
            return jsonify({"ok": False, "error": "unknown channel"}), 404
        ok = controller.manual_water(channel)
        return jsonify({"ok": ok})

    return app
