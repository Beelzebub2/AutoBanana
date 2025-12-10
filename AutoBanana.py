import atexit
import configparser
import itertools
import logging
import os
import sys
import threading
import time
import uuid
import webbrowser
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Deque, Dict, List, Optional
try:  # winreg is Windows-only; fallback to None on Linux/macOS
    import winreg as reg
except ImportError:
    reg = None

import psutil
import requests
import vdf  # type: ignore
from flask import Flask, jsonify, render_template, request, send_from_directory

import utils
import utils.steam_manager


APP_DIR = Path(__file__).parent
LOCK_PATH = APP_DIR / "autobanana.lock"
LOG_PATH = APP_DIR / "AutoBanana.log"
ICON_PATH = APP_DIR / "banana.ico"
UI_PORT = 5055
UI_HOST = "127.0.0.1"

logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("main")


def iso_or_none(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


class AutoBananaService:
    """Backend service that owns scheduling, Steam automation, and UI state."""

    available_themes = ["fire", "ice", "pinkneon", "rainbow", "matrix", "sunset", "default"]

    def __init__(self) -> None:
        self.is_windows = os.name == "nt"
        self.user_id_file = APP_DIR / "user_id.txt"
        self.usage_logged_file = APP_DIR / "usage_logged.txt"
        self.config = self.read_config()
        self.game_open_count = 0
        self.account_names: List[str] = []
        self.steam_install_location = self.get_steam_install_location()
        self.steam_account_changer = utils.steam_manager.SteamAccountChanger()
        self.events: Deque[Dict] = deque(maxlen=500)
        self.stop_event = threading.Event()
        self.manual_trigger = threading.Event()
        self.paused = False
        self.current_state = "idle"  # idle|running|waiting|stopped
        self.worker_thread: Optional[threading.Thread] = None
        self.next_run_at: Optional[datetime] = None
        self.last_run_at: Optional[datetime] = None
        self.lock_fd: Optional[int] = None
        self.ui_url = f"http://{UI_HOST}:{UI_PORT}"

        self.update_config_file()
        self.apply_startup_setting()
        self.register_usage()

    # ------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------
    def read_config(self) -> Dict:
        config = configparser.ConfigParser()
        config.read("config.ini")

        defaults = {
            "run_on_startup": False,
            "games": [],
            "time_to_wait": 60,
            "run_interval_seconds": 10800,
            "batch_size": 5,
            "theme": "fire",
            "switch_steam_accounts": False,
        }

        settings = config["Settings"] if "Settings" in config else {}

        cfg = {
            "run_on_startup": settings.getboolean("run_on_startup", fallback=defaults["run_on_startup"])
            if settings
            else defaults["run_on_startup"],
            "games": [game.strip() for game in settings.get("games", "").split(",") if game.strip()] if settings else defaults["games"],
            "time_to_wait": settings.getint("time_to_wait", fallback=defaults["time_to_wait"]) if settings else defaults["time_to_wait"],
            "run_interval_seconds": settings.getint("run_interval_seconds", fallback=defaults["run_interval_seconds"])
            if settings
            else defaults["run_interval_seconds"],
            "batch_size": settings.getint("batch_size", fallback=defaults["batch_size"]) if settings else defaults["batch_size"],
            "theme": settings.get("theme", defaults["theme"]).lower() if settings else defaults["theme"],
            "switch_steam_accounts": settings.getboolean("switch_steam_accounts", fallback=defaults["switch_steam_accounts"])
            if settings
            else defaults["switch_steam_accounts"],
        }

        if "Settings" not in config:
            config["Settings"] = {
                "run_on_startup": "yes" if cfg["run_on_startup"] else "no",
                "games": ",".join(cfg["games"]),
                "time_to_wait": str(cfg["time_to_wait"]),
                "run_interval_seconds": str(cfg["run_interval_seconds"]),
                "batch_size": str(cfg["batch_size"]),
                "theme": cfg["theme"],
                "switch_steam_accounts": "yes" if cfg["switch_steam_accounts"] else "no",
            }
            with open("config.ini", "w", encoding="utf-8") as configfile:
                config.write(configfile)

        return cfg

    def write_config(self) -> None:
        cfg = configparser.ConfigParser()
        cfg["Settings"] = {
            "run_on_startup": "yes" if self.config.get("run_on_startup") else "no",
            "games": ",".join(self.config.get("games", [])),
            "time_to_wait": str(self.config.get("time_to_wait", 60)),
            "run_interval_seconds": str(self.config.get("run_interval_seconds", 10800)),
            "batch_size": str(self.config.get("batch_size", 5)),
            "theme": self.config.get("theme", "fire"),
            "switch_steam_accounts": "yes" if self.config.get("switch_steam_accounts") else "no",
        }
        with open("config.ini", "w", encoding="utf-8") as configfile:
            cfg.write(configfile)

    def update_config_from_payload(self, payload: Dict) -> None:
        dirty = False
        for key in ("time_to_wait", "run_interval_seconds", "batch_size"):
            if key in payload:
                try:
                    self.config[key] = max(1, int(payload[key]))
                    dirty = True
                except (TypeError, ValueError):
                    continue

        for key in ("run_on_startup", "switch_steam_accounts"):
            if key in payload:
                self.config[key] = bool(payload[key])
                dirty = True

        if "games" in payload and isinstance(payload["games"], list):
            self.config["games"] = [str(g).strip() for g in payload["games"] if str(g).strip()]
            dirty = True

        if "theme" in payload and str(payload["theme"]).lower() in self.available_themes:
            self.config["theme"] = str(payload["theme"]).lower()
            dirty = True

        if dirty:
            self.write_config()
            self.apply_startup_setting()
            self.schedule_next_run(respect_existing=False)
            self.log_event("Configuration updated via UI", "info")

    # ------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------
    def log_event(self, message: str, level: str = "info") -> None:
        timestamp = datetime.utcnow().timestamp()
        entry = {"timestamp": timestamp, "level": level, "message": message}
        self.events.append(entry)

        if level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
        else:
            logger.info(message)

    # ------------------------------------------------------------
    # Environment setup
    # ------------------------------------------------------------
    def acquire_lock(self) -> bool:
        try:
            self.lock_fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            atexit.register(self.release_lock)
            return True
        except FileExistsError:
            return False

    def release_lock(self) -> None:
        if self.lock_fd:
            try:
                os.close(self.lock_fd)
            except OSError:
                pass
            self.lock_fd = None
        if LOCK_PATH.exists():
            try:
                LOCK_PATH.unlink()
            except OSError:
                pass

    def apply_startup_setting(self) -> None:
        if not self.is_windows or reg is None:
            return

        key_value = r"Software\Microsoft\Windows\CurrentVersion\Run"
        script_path = os.path.abspath(sys.argv[0])

        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, key_value, 0, reg.KEY_ALL_ACCESS) as open_key:
                if self.config.get("run_on_startup"):
                    reg.SetValueEx(open_key, "OpenBanana", 0, reg.REG_SZ, script_path)
                    logger.info("Registered AutoBanana to run on startup")
                else:
                    try:
                        reg.DeleteValue(open_key, "OpenBanana")
                    except FileNotFoundError:
                        pass
        except Exception as exc:
            logger.error(f"Failed updating startup setting: {exc}")

    def register_usage(self) -> None:
        try:
            user_id = None
            if self.user_id_file.exists():
                user_id = self.user_id_file.read_text(encoding="utf-8")
            else:
                user_id = str(uuid.uuid4())
                self.user_id_file.write_text(user_id, encoding="utf-8")

            if not self.usage_logged_file.exists():
                web_app_url = "https://script.google.com/macros/s/AKfycbxKQlXPVPq38RxqaqtOwGWTgpmNQIZyu2q2aAH5mSsvxlCiRe9jToIzv7yBA8kZECZ0/exec"
                response = requests.post(web_app_url, data={"user_id": user_id}, timeout=5)
                if response.status_code == 200:
                    self.usage_logged_file.write_text("logged", encoding="utf-8")
                    logger.info("Usage logged successfully")
                else:
                    logger.warning("Usage logging failed")
        except Exception as exc:
            logger.error(f"Failed to register usage: {exc}")

    # ------------------------------------------------------------
    # Steam helpers
    # ------------------------------------------------------------
    def get_steam_install_location(self) -> Optional[str]:
        if self.is_windows and reg is not None:
            try:
                steam_key = reg.OpenKey(reg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Wow6432Node\Valve\Steam")
                steam_install_location = reg.QueryValueEx(steam_key, "InstallPath")[0]
                reg.CloseKey(steam_key)
                return steam_install_location
            except FileNotFoundError:
                logger.error("Steam registry key not found; falling back to defaults")
            except Exception as exc:
                logger.error(f"Failed to read Steam path from registry: {exc}")

        for path in (
            os.environ.get("STEAM_PATH"),
            os.path.expanduser("~/.local/share/Steam"),
            os.path.expanduser("~/.steam/steam"),
            os.path.expanduser("~/.steam/root"),
        ):
            if path and os.path.exists(path):
                return path

        logger.warning("Steam installation not found. Set STEAM_PATH to override.")
        return None

    def _check_app_manifest(self, steam_apps_path: str, app_id: str) -> Optional[str]:
        manifest_file = os.path.join(steam_apps_path, f"appmanifest_{app_id}.acf")
        if os.path.exists(manifest_file):
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest = vdf.load(f)
                install_location = os.path.join(
                    steam_apps_path, "common", manifest["AppState"].get("installdir", "")
                )
                if os.path.exists(install_location):
                    return install_location
        return None

    def get_game_install_path(self, app_id: str) -> Optional[str]:
        if not self.steam_install_location:
            return None
        steam_apps_path = os.path.join(self.steam_install_location, "steamapps")

        install_path = self._check_app_manifest(steam_apps_path, app_id)
        if install_path:
            return install_path

        library_folders_file = os.path.join(steam_apps_path, "libraryfolders.vdf")
        if os.path.exists(library_folders_file):
            with open(library_folders_file, "r", encoding="utf-8") as f:
                library_folders = vdf.load(f).get("libraryfolders", {})

            for key, library in library_folders.items():
                if key == "0":
                    continue
                library_path = os.path.join(library.get("path", ""), "steamapps")
                install_path = self._check_app_manifest(library_path, app_id)
                if install_path:
                    return install_path
        return None

    def get_steam_games(self) -> Dict[str, str]:
        games: Dict[str, str] = {}
        if not self.steam_install_location:
            return games

        for game_id in self.config.get("games", []):
            install_path = self.get_game_install_path(game_id)
            if install_path:
                for _, _, files in os.walk(install_path):
                    for file in files:
                        if file.endswith(".exe") and file not in ("UnityCrashHandler64.exe", "UnityCrashHandler32.exe"):
                            games[file] = install_path
        return games

    def update_config_file(self) -> None:
        if not self.steam_install_location:
            return

        try:
            with open("config.ini", "r", encoding="utf-8") as configfile:
                lines = configfile.readlines()
        except FileNotFoundError:
            return

        games = self.config.get("games", [])
        installed_games = []
        removed_games = []

        for game in games:
            if self.get_game_install_path(game.strip()):
                installed_games.append(game)
            else:
                removed_games.append(game)

        new_games_line = f"games = {','.join(installed_games)}\n"

        with open("config.ini", "w", encoding="utf-8") as configfile:
            for line in lines:
                if line.startswith("games ="):
                    configfile.write(new_games_line)
                else:
                    configfile.write(line)

        if removed_games:
            message = "Removed non-installed game IDs from config: " + ", ".join(removed_games)
            self.log_event(message, "warning")
            self.config["games"] = installed_games

    # ------------------------------------------------------------
    # Core automation
    # ------------------------------------------------------------
    def open_games(self, time_to_wait: int) -> None:
        all_games = self.get_steam_games()

        def find_running_steam_games(steam_games):
            running_games = []
            for proc in psutil.process_iter(["pid", "name", "create_time"]):
                if proc.info.get("name") in steam_games:
                    start_time = datetime.fromtimestamp(proc.info["create_time"])
                    process_age = datetime.now() - start_time
                    running_games.append((proc, start_time, process_age))
            return running_games

        def open_single_game(game_id: str) -> bool:
            try:
                steam_run_url = f"steam://rungameid/{game_id}"
                webbrowser.open(steam_run_url)
                self.log_event(f"Opened {steam_run_url}", "success")
                return True
            except Exception as exc:
                self.log_event(f"Failed to open the game: {exc}", "error")
                return False

        def batch(iterable, n=1):
            it = iter(iterable)
            while True:
                chunk = list(itertools.islice(it, n))
                if not chunk:
                    break
                yield chunk

        try:
            games = self.config.get("games", [])
            if not games:
                self.log_event("No games configured to launch.", "warning")
                return

            self.log_event(f"Launching {len(games)} game(s) in batches of {self.config['batch_size']}.")

            for game_batch in batch(games, self.config["batch_size"]):
                for game_id in game_batch:
                    open_single_game(game_id)
                    time.sleep(1)

                if game_batch:
                    self.log_event(f"Waiting {time_to_wait}s before closing newly started games.")
                    time.sleep(time_to_wait)

                running_games = find_running_steam_games(all_games)
                self.close_games(running_games)
        except Exception as exc:
            self.log_event(f"Failed to open or close the game: {exc}", "error")

    def close_games(self, running_games) -> None:
        threshold_minutes = 1.5
        for proc, start_time, process_age in running_games:
            try:
                if process_age < timedelta(minutes=threshold_minutes):
                    proc.terminate()
                    proc.wait()
                    self.log_event(f"Closed {proc.info['name']} (PID: {proc.info['pid']})", "warning")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

    def close_program(self, process_name: str) -> None:
        for proc in psutil.process_iter(["pid", "name"]):
            if proc.info.get("name") == process_name:
                proc.terminate()
                break

    def run_once(self) -> None:
        self.current_state = "running"
        self.config = self.read_config()
        self.update_config_file()
        self.account_names = self.steam_account_changer.get_steam_login_user_names()
        self.last_run_at = datetime.now()
        self.log_event("Starting scheduled run")

        if self.config.get("switch_steam_accounts") and self.account_names:
            for account in self.account_names:
                self.log_event(f"Switching to account: {account}")
                switched = self.steam_account_changer.switch_account(account)
                if not switched:
                    self.log_event(f"Skipping launches for account {account} due to switch failure.", "warning")
                    continue
                self.open_games(self.config.get("time_to_wait", 60))
                self.game_open_count += 1
        else:
            self.open_games(self.config.get("time_to_wait", 60))
            self.game_open_count += 1

        self.schedule_next_run()
        self.current_state = "waiting"

    # ------------------------------------------------------------
    # Scheduler
    # ------------------------------------------------------------
    def start(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            return
        self.stop_event = threading.Event()
        self.paused = False
        self.schedule_next_run()
        self.worker_thread = threading.Thread(target=self._runner_loop, daemon=True)
        self.worker_thread.start()
        self.current_state = "waiting"
        self.log_event("Scheduler started")

    def _runner_loop(self) -> None:
        while not self.stop_event.is_set():
            if self.paused:
                time.sleep(0.5)
                continue
            if self.manual_trigger.is_set():
                self.manual_trigger.clear()
                self.run_once()
                continue

            if self.next_run_at and datetime.now() >= self.next_run_at:
                self.run_once()
                continue

            time.sleep(1)

    def schedule_next_run(self, respect_existing: bool = False) -> None:
        interval = max(1, int(self.config.get("run_interval_seconds", 10800)))
        if respect_existing and self.next_run_at:
            return
        self.next_run_at = datetime.now() + timedelta(seconds=interval)
        self.current_state = "waiting"

    def trigger_manual_run(self) -> None:
        self.ensure_worker()
        self.manual_trigger.set()

    def stop(self) -> None:
        self.stop_event.set()
        if self.worker_thread:
            self.worker_thread.join(timeout=3)
        self.release_lock()
        self.current_state = "stopped"
        self.log_event("Scheduler stopped", "warning")

    def pause_scheduler(self) -> None:
        self.paused = True
        self.stop_event.set()
        if self.worker_thread:
            self.worker_thread.join(timeout=3)
        self.worker_thread = None
        self.current_state = "stopped"
        self.log_event("Scheduler paused", "warning")

    def ensure_worker(self) -> None:
        if not self.worker_thread or not self.worker_thread.is_alive():
            self.start()

    # ------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------
    def status_payload(self) -> Dict:
        # Refresh account list for accurate count in UI
        self.account_names = self.steam_account_changer.get_steam_login_user_names()
        return {
            "config": self.config,
            "next_run_at": iso_or_none(self.next_run_at),
            "last_run_at": iso_or_none(self.last_run_at),
            "game_open_count": self.game_open_count,
            "accounts": self.account_names,
            "accounts_count": len(self.account_names),
            "themes": self.available_themes,
            "ui_url": self.ui_url,
            "running": self.worker_thread.is_alive() if self.worker_thread else False,
            "state": self.current_state,
            "interval_seconds": self.config.get("run_interval_seconds", 10800),
        }

    def open_ui(self) -> None:
        try:
            webbrowser.open(self.ui_url)
        except Exception:
            pass

    def start_tray_icon(self) -> None:
        if not self.is_windows:
            return
        try:
            import pystray
            from PIL import Image, ImageDraw
        except Exception:
            self.log_event("pystray or Pillow not installed; tray icon disabled", "warning")
            return

        def load_icon():
            if ICON_PATH.exists():
                try:
                    return Image.open(ICON_PATH).convert("RGBA")
                except Exception:
                    pass
            # Fallback simple icon
            image = Image.new("RGBA", (64, 64), color=(30, 30, 40, 255))
            draw = ImageDraw.Draw(image)
            draw.rectangle([14, 20, 50, 44], fill=(255, 199, 44, 255))
            draw.rectangle([26, 14, 38, 50], fill=(245, 166, 35, 255))
            return image

        def on_open(icon, _item):
            self.open_ui()

        def on_quit(icon, _item):
            self.stop()
            icon.stop()

        menu = pystray.Menu(
            pystray.MenuItem("Open UI", on_open),
            pystray.MenuItem("Quit", on_quit),
        )

        icon_image = load_icon()
        icon = pystray.Icon("autobanana", icon_image, "AutoBanana", menu)
        threading.Thread(target=icon.run, daemon=True).start()
        self.log_event("Tray icon started")


service: Optional[AutoBananaService] = None
app = Flask(__name__, static_folder="web/static", template_folder="web/templates")


@app.route("/")
def index():
    if not service:
        return "Service not ready", 503
    return render_template("index.html", theme=service.config.get("theme", "fire"))


@app.route("/settings")
def settings():
    if not service:
        return "Service not ready", 503
    return render_template("settings.html", theme=service.config.get("theme", "fire"))


@app.route("/api/ping")
def api_ping():
    return jsonify({"ok": True})


@app.route("/api/status")
def api_status():
    if not service:
        return jsonify({"error": "Service not ready"}), 503
    return jsonify(service.status_payload())


@app.route("/api/logs")
def api_logs():
    if not service:
        return jsonify({"error": "Service not ready"}), 503
    since = float(request.args.get("since", 0))
    events = [event for event in service.events if event["timestamp"] > since]
    return jsonify({"events": events, "latest": events[-1]["timestamp"] if events else since})


@app.route("/api/run", methods=["POST"])
def api_run():
    if not service:
        return jsonify({"error": "Service not ready"}), 503
    service.trigger_manual_run()
    return jsonify({"status": "queued"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    if not service:
        return jsonify({"error": "Service not ready"}), 503
    service.pause_scheduler()
    return jsonify({"status": "stopped"})


@app.route("/api/config", methods=["POST"])
def api_config():
    if not service:
        return jsonify({"error": "Service not ready"}), 503
    payload = request.get_json(force=True, silent=True) or {}
    service.update_config_from_payload(payload)
    return jsonify(service.status_payload())


@app.route("/static/<path:path>")
def send_static(path):
    return send_from_directory(app.static_folder, path)


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(str(APP_DIR), "banana.ico")


def start_flask():
    app.run(host=UI_HOST, port=UI_PORT, debug=False, use_reloader=False)


def existing_instance_running() -> bool:
    try:
        requests.get(f"http://{UI_HOST}:{UI_PORT}/api/ping", timeout=1)
        return True
    except Exception:
        return False


def main():
    global service

    if existing_instance_running():
        webbrowser.open(f"http://{UI_HOST}:{UI_PORT}")
        print("Another AutoBanana instance is already running. Opening the UI instead.")
        return

    svc = AutoBananaService()
    if not svc.acquire_lock():
        webbrowser.open(f"http://{UI_HOST}:{UI_PORT}")
        print("AutoBanana is already running. Opening the existing UI.")
        return

    service = svc
    service.start()

    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    service.start_tray_icon()
    service.open_ui()

    try:
        while flask_thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        service.stop()


if __name__ == "__main__":
    main()

    def download_file_if_not_exists(self, file_name, directory):
        '''The function `download_file_if_not_exists` downloads a file from a URL to a specified directory
        if the file does not already exist in that directory.

        Parameters
        ----------
        file_name
            The `file_name` parameter in the `download_file_if_not_exists` function represents the name of
        the file that you want to download. It is the name of the file that will be used both in the URL
        to download the file and as the name of the file when saved in the specified directory
        directory
            The `directory` parameter in the `download_file_if_not_exists` function refers to the directory
        where the file will be saved or checked for existence. If the directory does not exist, the
        function will create it before proceeding with downloading or checking the file.

        '''
        # Create the directory if it doesn't exist
        if not os.path.exists(directory):
            os.makedirs(directory)

        file_path = os.path.join(directory, file_name)

        # Check if the file exists
        if not os.path.exists(file_path):
            # Construct the full URL
            file_url = os.path.join(self.base_url, file_name)

            # Download the file
            response = requests.get(file_url)
            response.raise_for_status()  # Raise an error if the request failed

            # Save the file
            with open(file_path, 'w', encoding="utf-8") as file:
                file.write(response.text)

            logging.info(f"{file_name} has been downloaded to {directory}.")
        else:
            logging.info(f"{file_name} already exists in {directory}.")

    def read_config(self):
        '''The `read_config` function reads a configuration file, downloads it from a repository if it
        doesn't exist, and returns specific settings from the configuration.

        Returns
        -------
            The `read_config` method returns a dictionary containing the following configuration settings:
            `run_on_startup`: bool
            `games`: list
            `time_to_wait`: int

        '''
        config = configparser.ConfigParser()
        self.download_file_if_not_exists("config.ini", ".")

        config.read('config.ini')
        return {
            'run_on_startup': config['Settings'].getboolean('run_on_startup', fallback=False),
            'games': [game.strip() for game in config['Settings'].get('games', '').split(',') if game.strip()],
            'time_to_wait': config['Settings'].getint('time_to_wait', fallback=20),
            'batch_size': config['Settings'].getint('batch_size', fallback=5),
            'theme': config['Settings'].get('theme', fallback='default'),
            'switch_steam_accounts': config['Settings'].getboolean('switch_steam_accounts', fallback=False)
        }

    def add_to_startup(self):
        '''This Python function adds the script to the Windows startup registry to run automatically on
        system boot.

        '''
        if not self.is_windows or reg is None:
            logging.info("Startup registration is only supported on Windows; skipping.")
            return
        script_path = os.path.abspath(sys.argv[0])
        key_value = r'Software\Microsoft\Windows\CurrentVersion\Run'
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, key_value, 0, reg.KEY_ALL_ACCESS) as open_key:
                existing_value, _ = reg.QueryValueEx(open_key, 'OpenBanana')
                if existing_value != script_path:
                    reg.SetValueEx(open_key, 'OpenBanana', 0, reg.REG_SZ, script_path)
                    logging.info("Successfully added to startup")
                else:
                    print(f"{self.colorama_color}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Already on startup")
        except FileNotFoundError:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, key_value, 0, reg.KEY_ALL_ACCESS) as open_key:
                reg.SetValueEx(open_key, 'OpenBanana', 0, reg.REG_SZ, script_path)
                logging.info("Successfully added to startup")
        except Exception as e:
            logging.error(f"Failed to add to startup: {e}")

    def remove_from_startup(self):
        '''The function removes a specific entry from the Windows startup registry key if it exists.

        '''
        if not self.is_windows or reg is None:
            return
        key_value = r'Software\Microsoft\Windows\CurrentVersion\Run'
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, key_value, 0, reg.KEY_ALL_ACCESS) as open_key:
                reg.DeleteValue(open_key, 'OpenBanana')
                logging.info("Successfully removed from startup")
        except FileNotFoundError:
            logging.error("Startup entry not found, nothing to remove")
        except Exception as e:
            logging.error(f"Failed to remove from startup: {e}")

    def get_steam_install_location(self):
        '''Locate the Steam installation path across supported platforms.'''
        # Windows: use registry when available
        if self.is_windows and reg is not None:
            try:
                steam_key = reg.OpenKey(
                    reg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Wow6432Node\Valve\Steam",
                )
                steam_install_location = reg.QueryValueEx(steam_key, "InstallPath")[0]
                reg.CloseKey(steam_key)
                return steam_install_location
            except FileNotFoundError:
                logging.error("Steam registry key not found; falling back to default locations.")
            except Exception as exc:  # pragma: no cover - defensive
                logging.error(f"Failed to read Steam path from registry: {exc}")

        # Linux/macOS: check common install locations and env override
        candidates = [
            os.environ.get("STEAM_PATH"),
            os.path.expanduser("~/.local/share/Steam"),
            os.path.expanduser("~/.steam/steam"),
            os.path.expanduser("~/.steam/root"),
        ]

        for path in candidates:
            if path and os.path.exists(path):
                return path

        logging.warning("Steam installation not found. Set STEAM_PATH to override.")
        return None

    def get_game_install_path(self, app_id):
        '''
        Searches for the installation path of a game using the provided app ID in Steam directories.

        Parameters
        ----------
        app_id : str
            The Steam application ID of the game.

        Returns
        -------
        str or None
            The installation path of the game if found, otherwise None.
        '''
        if not self.steam_install_location:
            logging.warning("Steam install location is unknown; cannot resolve game paths.")
            return None
        steam_apps_path = os.path.join(self.steam_install_location, "steamapps")

        # Check the main steamapps directory first
        install_path = self._check_app_manifest(steam_apps_path, app_id)
        if install_path:
            return install_path

        # Check the library folders
        library_folders_file = os.path.join(steam_apps_path, "libraryfolders.vdf")
        if os.path.exists(library_folders_file):
            with open(library_folders_file, "r") as f:
                library_folders = vdf.load(f)["libraryfolders"]

            for key, library in library_folders.items():
                if key == "0":
                    continue

                library_path = os.path.join(library["path"], "steamapps")
                install_path = self._check_app_manifest(library_path, app_id)
                if install_path:
                    return install_path

        return None

    def _check_app_manifest(self, steam_apps_path, app_id):
        """
        Helper method to check for the app manifest and return the installation path if found.

        Parameters
        ----------
        steam_apps_path : str
            Path to the steamapps directory.
        app_id : str
            The Steam application ID of the game.

        Returns
        -------
        str or None
            The installation path of the game if found, otherwise None.
        """
        manifest_file = os.path.join(steam_apps_path, f"appmanifest_{app_id}.acf")
        if os.path.exists(manifest_file):
            with open(manifest_file, "r") as f:
                manifest = vdf.load(f)
                install_location = os.path.join(
                    steam_apps_path, "common", manifest["AppState"]["installdir"]
                )
                if os.path.exists(install_location):
                    return install_location
        return None

    def get_steam_games(self):
        '''The function `get_steam_games` retrieves a dictionary of Steam games and their installation
        paths based on the provided game IDs.

        Returns
        -------
            A dictionary containing the names of Steam games (as keys) and their corresponding installation
        paths (as values) is being returned.

        '''
        games = {}

        if not self.steam_install_location:
            logging.warning("Steam install location is unknown; skipping installed games discovery.")
            return games

        for game_id in self.config['games']:
            install_path = self.get_game_install_path(game_id)
            if install_path:
                for _, _, files in os.walk(install_path):
                    for file in files:
                        if file.endswith(".exe") and file != "UnityCrashHandler64.exe" and file != "UnityCrashHandler32.exe":
                            games[file] = install_path

        return games

    def update_config_file(self):
        '''This function updates a configuration file by removing any games that are not installed from the
        list of games, while preserving comments.
        '''
        if not self.steam_install_location:
            logging.warning("Steam path not found; skipping config cleanup.")
            return
        # Read the current config file into memory
        with open("config.ini", "r") as configfile:
            lines = configfile.readlines()

        # Update the games list
        self.config = self.read_config()
        games = self.config['games']
        installed_games = []
        removed_games = []

        for game in games:
            if self.get_game_install_path(game.strip()):
                installed_games.append(game)
            else:
                removed_games.append(game)

        new_games_line = f"games = {','.join(installed_games)}\n"

        # Write the updated config back to the file, preserving comments
        with open("config.ini", "w") as configfile:
            for line in lines:
                if line.startswith("games ="):
                    configfile.write(new_games_line)
                else:
                    configfile.write(line)

        if removed_games:
            message = "Removed non-installed game IDs from config: " + ", ".join(removed_games)
            logging.warning(message)
            self.log_event(message, "warning")

    def open_games(self, time_to_wait):
        '''The `open_games` function in Python opens Steam games, logs the action, and checks for running
        game processes.

        Parameters
        ----------
        time_to_wait

            The `time_to_wait` parameter in the `open_games` method represents the amount of time (in
        seconds) that the program should wait after opening the games before checking for running
        processes and closing them. This parameter allows for a delay before the program proceeds to the
        next steps, giving the games some

        '''
        all_games = self.get_steam_games()

        def find_running_steam_games(steam_games):
            '''The function `find_running_steam_games` takes a list of Steam game names and returns
            information about the currently running processes for those games.

            Parameters
            ----------
            steam_games
                A list of names of Steam games that you want to check for running processes.

            Returns
            -------
                The function `find_running_steam_games` returns a list of tuples, where each tuple contains
            information about a running Steam game process. The tuple includes the process object, the
            start time of the process, and the age of the process calculated as the difference between
            the current time and the start time.

            '''
            running_games = []
            for proc in psutil.process_iter(['pid', 'name', 'create_time']):
                if proc.info['name'] in steam_games:
                    start_time = datetime.fromtimestamp(proc.info['create_time'])
                    current_time = datetime.now()
                    process_age = current_time - start_time
                    running_games.append((proc, start_time, process_age))
            return running_games

        def open_single_game(game_id):
            '''The function `open_single_game` opens a game using its ID on Steam and logs the action.

            Parameters
            ----------
            game_id
                The `open_single_game` function takes a `game_id` as a parameter. This `game_id` is used to
            construct a Steam run URL (`steam://rungameid/{game_id}`) to open a specific game on Steam.
            If an exception occurs during the process of opening the

            '''
            try:
                steam_run_url = f"steam://rungameid/{game_id}"
                webbrowser.open(steam_run_url)
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                logging.info(f"{timestamp} - Opened {steam_run_url}")
                self.log_event(f"Opened {steam_run_url}", "success")
                return True
            except Exception as e:
                logging.error(f"Failed to open the game: {e}")
                self.log_event(f"Failed to open the game: {e}", "error")
                return False

        def batch(iterable, n=1):
            it = iter(iterable)
            while True:
                chunk = list(itertools.islice(it, n))
                if not chunk:
                    break
                yield chunk

        try:
            self.render_banner(self.logo)

            games = self.config['games']
            if not games:
                self.log_event("No games configured to launch.", "warning")
                return

            self.log_event(f"Launching {len(games)} game(s) in batches of {self.config['batch_size']}.")

            for game_batch in batch(games, self.config['batch_size']):
                for game_id in game_batch:
                    open_single_game(game_id)
                    time.sleep(1)

                if game_batch:
                    self.log_event(f"Waiting {time_to_wait}s before closing newly started games.")
                    # Use animated wait instead of plain sleep
                    self.animated_wait(time_to_wait, "Games running", show_progress=True)

                running_games = find_running_steam_games(all_games)
                self.close_games(running_games)
        except Exception as e:
            logging.error(f"Failed to open or close the game: {e}")

    def close_games(self, running_games):
        '''The `close_games` function terminates running games that have been active for less than 1.5
        minutes and logs the closure.

        Parameters
        ----------
        running_games
            The `running_games` parameter in the `close_games` method seems to be a list of tuples
        containing information about running game processes. Each tuple appears to contain three
        elements: `proc` (presumably a process object), `start_time` (the start time of the process), and
        `process
        '''
        threshold_minutes = 1.5

        for proc, start_time, process_age in running_games:
            try:
                if process_age < timedelta(minutes=threshold_minutes):
                    proc.terminate()
                    proc.wait()
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    logging.info(f"{timestamp} - Closed {proc.info['name']} (PID: {proc.info['pid']})")
                    self.log_event(f"Closed {proc.info['name']} (PID: {proc.info['pid']})", "warning")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

    def close_program(self, process_name):
        '''The function `close_program` terminates a process with a specified name using the psutil library
        in Python.

        Parameters
        ----------
        process_name
            The `process_name` parameter in the `close_program` method is a string that represents the name
        of the process that you want to terminate. The method uses the `psutil` library to iterate
        through all running processes and terminates the one with the specified name.
        '''
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] == process_name:
                proc.terminate()
                break

    def clear_console(self):
        '''The function `clear_console` clears the console screen based on the operating system.

        '''
        if os.name == 'nt':
            os.system('cls')
        else:
            os.system('clear')

    def countdown(self, seconds):
        """
        Displays an animated countdown timer with progress bar and status information.
        Adapts to terminal size changes in real-time.

        Parameters
        ----------
        seconds : int
            The total number of seconds for which the countdown will run.
        """
        total_seconds = seconds
        last_width = 0
        start_time = time.time()
        
        while True:
            # Calculate remaining time
            elapsed = time.time() - start_time
            remaining = total_seconds - elapsed
            
            if remaining <= 0:
                break
            
            # Check for terminal resize
            current_width, _ = self.get_terminal_size()
            if current_width != last_width:
                last_width = current_width
                # Clear line on resize
                sys.stdout.write('\r' + ' ' * (current_width - 1) + '\r')
            
            uptime = datetime.now() - self.start_time
            account_count = len(self.account_names) if self.config['switch_steam_accounts'] else 1
            status_line = self.compose_status_line(int(remaining), uptime, account_count, total_seconds)
            
            # Ensure line fits terminal width
            max_len = current_width - 2
            sys.stdout.write('\r' + status_line[:max_len].ljust(max_len))
            sys.stdout.flush()
            
            # Sleep for smooth animation (~10 FPS)
            time.sleep(0.1)
        
        # Animation completion effect
        self.show_completion_animation()
        print()

    def show_completion_animation(self):
        """Show a brief completion animation with theme colors."""
        term_width, _ = self.get_terminal_size()
        completion_text = " ✓ Ready for next run! "
        
        # Get base theme colors for flash effect
        base_r, base_g, base_b = self.get_theme_colors(animated=False)
        
        # Flash effect with theme colors
        for i in range(3):
            brightness = 1.0 if i % 2 == 0 else 0.6
            r = int(base_r * brightness)
            g = int(base_g * brightness)
            b = int(base_b * brightness)
            colored_text = f"\033[38;2;{r};{g};{b}m{completion_text}\033[0m"
            sys.stdout.write('\r' + colored_text.center(term_width - 10))
            sys.stdout.flush()
            time.sleep(0.15)
        
        sys.stdout.write('\r' + ' ' * (term_width - 1) + '\r')
        sys.stdout.flush()

    def register(self):
        '''The `register` function checks for a user ID file, generates a new ID if not found, logs user
        usage via a web app, and handles logging success or failure.

        '''
        try:
            with open(self.user_id_file, 'r') as file:
                user_id = file.read()
        except FileNotFoundError:
            user_id = str(uuid.uuid4())
            with open(self.user_id_file, 'w') as file:
                file.write(user_id)

        if not os.path.exists(self.usage_logged_file):
            web_app_url = 'https://script.google.com/macros/s/AKfycbxKQlXPVPq38RxqaqtOwGWTgpmNQIZyu2q2aAH5mSsvxlCiRe9jToIzv7yBA8kZECZ0/exec'
            response = requests.post(web_app_url, data={'user_id': user_id})
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if response.status_code == 200:
                with open(self.usage_logged_file, 'w') as file:
                    file.write('logged')
                print(f"{self.colorama_color}{timestamp} - {Fore.GREEN}Usage logged successfully.")
            else:
                logging.error(f"{timestamp} - Failed to log usage.")
        else:
            print(f"{self.colorama_color}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {Fore.GREEN}Usage already logged.")

    def set_terminal_size(self, width, height):
        if self.is_windows:
            os.system(f"mode con: cols={width} lines={height}")
        # On non-Windows consoles, changing size is terminal-dependent; skip to avoid side effects.

    def string_width(self, multiline_string):
        lines = multiline_string.split('\n')
        max_length = max(len(line) for line in lines)
        return max_length

    def apply_theme(self):
        '''The function `apply_theme` sets the theme and color scheme based on the configuration provided.
        Supports animated themes: fire, ice, pinkneon, rainbow, matrix, sunset.
        '''
        theme = self.config['theme'].lower()
        match theme:
            case 'fire':
                self.theme_function = self.themes.fire
                self.colorama_color = Fore.YELLOW
            case 'ice':
                self.theme_function = self.themes.ice
                self.colorama_color = Fore.LIGHTBLUE_EX
            case 'pinkneon':
                self.theme_function = self.themes.pinkneon
                self.colorama_color = Fore.LIGHTMAGENTA_EX
            case 'rainbow':
                self.theme_function = self.themes.rainbow
                self.colorama_color = Fore.LIGHTCYAN_EX
            case 'matrix':
                self.theme_function = self.themes.matrix
                self.colorama_color = Fore.LIGHTGREEN_EX
            case 'sunset':
                self.theme_function = self.themes.sunset
                self.colorama_color = Fore.LIGHTYELLOW_EX
            case 'default' | _:
                self.theme_function = self.themes.default_theme
                self.colorama_color = Fore.LIGHTWHITE_EX

    def is_running_as_exe(self):
        '''The function `is_running_as_exe` checks if the Python script is running as an executable or as a .py.

        Returns
        -------
            The function `is_running_as_exe` is checking if the Python script is running as a standalone
        executable (`.exe` file) using PyInstaller or similar tools. It returns `True` if the script is
        frozen (compiled into an executable) and has the `_MEIPASS` attribute in the `sys` module,
        otherwise it returns `False`.

        '''
        return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')

    def show_loading_animation(self, message="Loading", duration=1.5):
        """Show a brief loading animation with theme colors."""
        term_width, _ = self.get_terminal_size()
        frames = duration * 10  # 10 FPS
        
        for i in range(int(frames)):
            spinner = self.get_spinner(i)
            dots = "." * ((i % 4))
            text = f" {spinner} {message}{dots.ljust(3)} "
            
            # Color based on selected theme
            color_code = self.get_theme_color_code(animated=True)
            colored = f"{color_code}{text}\033[0m"
            
            sys.stdout.write('\r' + colored)
            sys.stdout.flush()
            time.sleep(0.1)
        
        sys.stdout.write('\r' + ' ' * 30 + '\r')
        sys.stdout.flush()

    def main(self):
        # Show animated startup with theme animation preview
        self.show_loading_animation("Initializing AutoBanana", 1.0)
        self.clear_console()
        # Show animated banner for 2 seconds to preview theme
        print(self.theme_function(self.startup_logo, animate=True))
        self.animated_wait(2, "Loading theme", show_progress=True)
        self.render_banner(self.startup_logo)
        # Keep the startup menu visible briefly before continuing
        time.sleep(1.5)
        self.register()
        if self.config['run_on_startup']:
            self.add_to_startup()
        else:
            self.remove_from_startup()
        self.account_names = self.steam_account_changer.get_steam_login_user_names()
        self.print_config_overview()
        self.print_account_overview(self.account_names)
        while True:
            # Check for terminal resize and refresh banner if needed
            new_width, _ = self.get_terminal_size()
            if abs(new_width - self.console_width) > 10:
                self.console_width = new_width
                self.render_banner(self.logo)
            
            self.account_names = self.steam_account_changer.get_steam_login_user_names()

            if self.config['switch_steam_accounts'] and not self.account_names:
                self.log_event("Switching is enabled but no Steam accounts with 'Remember password' were found.", "warning")

            if self.config['switch_steam_accounts'] and self.account_names:
                for account in self.account_names:
                    self.log_event(f"Switching to account: {account}")
                    switched = self.steam_account_changer.switch_account(account)
                    if not switched:
                        self.log_event(f"Skipping launches for account {account} due to switch failure.", "warning")
                        continue
                    # Animated wait while Steam switches accounts
                    self.animated_account_switch(account, 10)
                    self.open_games(self.config['time_to_wait'])
                    self.game_open_count += 1
                self.countdown(3 * 60 * 60)
            else:
                self.open_games(self.config['time_to_wait'])
                self.game_open_count += 1
                self.countdown(3 * 60 * 60)

            self.config = self.read_config()
            self.apply_theme()
            self.print_config_overview()


if __name__ == "__main__":
    auto_banana = None
    try:
        auto_banana = AutoBanana()
        if auto_banana.is_windows:
            os.system("title AutoBanana v2.3 - Animated Edition")
            # Set initial terminal size, will adapt dynamically afterwards
            auto_banana.set_terminal_size(auto_banana.console_width, 32)
        auto_banana.main()
    except KeyboardInterrupt:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if auto_banana:
            auto_banana.stop_animation_thread()
            print(f"\n\n{auto_banana.colorama_color}{timestamp} - {Fore.LIGHTGREEN_EX}Program exited gracefully.")
        else:
            print(f"\n\n{timestamp} - Program exited gracefully.")
    finally:
        if auto_banana:
            auto_banana.stop_animation_thread()
