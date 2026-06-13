# Grow App

A self-contained plant monitor for the Pimoroni Grow HAT Mini on a Raspberry Pi Zero W. It:

1. Samples soil moisture for up to 3 plants on a schedule
2. Stores readings and events in a local SQLite database
3. Serves a web dashboard with live status, history charts and a manual "water now" button
4. Automatically runs the pumps when saturation drops below a per-plant threshold (with soak delay and a daily safety cap)
5. Sends Telegram notifications for waterings, very dry soil, dead sensors and hitting the daily watering limit

Without the HAT attached (e.g. on your laptop) it runs with **mock hardware** so you can develop and preview the dashboard anywhere:

```bash
cd app
python3 main.py --config config.dev.yaml   # then open http://localhost:8080
```

(`config.yaml` is the Pi config — its database path lives under `/home/pi`, so always pass `config.dev.yaml` off-Pi.)

## Setup on the Pi

Assuming a fresh Raspberry Pi OS (Raspbian) with the Grow HAT Mini attached:

```bash
# 1. Enable the interfaces the HAT needs
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0
echo "dtoverlay=spi0-cs,cs0_pin=14" | sudo tee -a /boot/config.txt
sudo reboot

# 2. Get the code and dependencies
sudo apt install -y git python3-pip python3-yaml python3-flask python3-requests python3-rpi.gpio
git clone <your fork of this repo> /home/pi/grow-python
cd /home/pi/grow-python
sudo pip3 install .          # installs the growhat drivers from this repo

# 3. Configure
nano app/config.yaml         # thresholds, plant names, telegram

# 4. Try it
python3 app/main.py
# then open http://<pi-ip>:8080 from your phone/laptop
```

### Run as a service (start on boot)

```bash
sudo cp app/grow-app.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now grow-app
journalctl -u grow-app -f    # watch the logs
```

## Telegram setup

1. In Telegram, talk to **@BotFather** → `/newbot` → pick a name. Copy the **token**.
2. Send any message to your new bot (this opens the chat).
3. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and copy the
   `"chat":{"id": ...}` number — that's your **chat_id**.
4. Put both in `app/config.yaml` and set `telegram.enabled: true`.

You'll get a "🌱 Grow monitor started" message on the next restart if it's wired up correctly.

## Calibrating the sensors

The defaults (`wet_point: 0.7`, `dry_point: 27.6`, in pulses/sec) are reasonable, but soil varies:

- With the sensor in **dry** soil, note the `pulses` value in the dashboard's latest reading
  (or `sqlite3 grow.db "SELECT * FROM readings ORDER BY ts DESC LIMIT 3"`) → set as `dry_point`.
- Water thoroughly, wait ~5 minutes, note the value → set as `wet_point`.

Restart the service after editing the config.

## Tuning watering

Per channel in `config.yaml`:

| Setting | Meaning |
|---|---|
| `water_level` | Auto-water when saturation drops below this (0–1) |
| `warn_level` | Telegram "very dry" alert below this |
| `pump_time` / `pump_speed` | How long/fast each dose runs — start small, the pumps are strong |
| `watering_delay_minutes` | Soak time before another dose is allowed |
| `max_waterings_per_day` | Safety cap — if hit, you get an alert instead of a flood |

The daily cap matters: if a tube pops off or the reservoir runs dry, saturation never rises and
the app would otherwise pump forever. With the cap you get a Telegram warning instead.

## Architecture

```
main.py ── loads config.yaml
  ├─ Hardware   (growapp/hardware.py)  grow lib drivers, or mocks off-Pi
  ├─ Database   (growapp/database.py)  SQLite: readings + events
  ├─ Notifier   (growapp/notifier.py)  Telegram Bot API with alert cooldowns
  ├─ Controller (growapp/controller.py) background sample/water/notify loop
  └─ Flask app  (growapp/webapp.py)    dashboard + JSON API
```
