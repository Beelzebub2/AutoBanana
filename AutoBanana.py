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
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple
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
        self.wait_progress: Optional[Dict] = None  # {elapsed, total, label}
        self.switch_progress: Optional[Dict] = None  # {total, completed, phase, current_account, message}
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
        timestamp = datetime.now(UTC).timestamp()
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
            if self.stop_event.is_set():
                self.log_event("Stop requested; skipping new launches.", "warning")
                return

            for game_batch in batch(games, self.config["batch_size"]):
                if self.stop_event.is_set():
                    self.log_event("Stop requested; aborting remaining batches.", "warning")
                    break
                for game_id in game_batch:
                    if self.stop_event.is_set():
                        break
                    open_single_game(game_id)
                    time.sleep(1)

                if self.stop_event.is_set():
                    break

                if game_batch:
                    self.log_event(f"Waiting {time_to_wait}s before closing newly started games.")
                    self.wait_with_progress(time_to_wait, "Waiting before closing games")

                running_games = find_running_steam_games(all_games)
                self.close_games(running_games)
                if self.stop_event.is_set():
                    break
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

    def wait_with_progress(self, duration: int, label: str = "Waiting") -> None:
        duration = max(0, int(duration))
        start = time.time()
        self.wait_progress = {"elapsed": 0, "total": duration, "label": label}
        interrupted = False
        try:
            while True:
                if self.stop_event.is_set():
                    interrupted = True
                    break
                elapsed = time.time() - start
                self.wait_progress = {"elapsed": int(elapsed), "total": duration, "label": label}
                if elapsed >= duration:
                    break
                time.sleep(0.2)
        finally:
            self.wait_progress = None
            if interrupted:
                self.log_event(f"Stop requested during '{label}'. Exiting early.", "warning")

    def run_once(self) -> None:
        self.current_state = "running"
        self.config = self.read_config()
        self.update_config_file()
        self.account_names = self.steam_account_changer.get_steam_login_user_names()
        self.last_run_at = datetime.now()
        self.log_event("Starting scheduled run")
        self.switch_progress = None

        if self.config.get("switch_steam_accounts") and self.account_names:
            total_accounts = len(self.account_names)
            self.switch_progress = {
                "total": total_accounts,
                "completed": 0,
                "phase": "queued",
                "current_account": None,
                "message": "Preparing account rotation",
                "detail": "Gathering Steam accounts",
                "step": 0,
                "step_total": 0,
            }
            for index, account in enumerate(self.account_names, start=1):
                if self.stop_event.is_set():
                    self.switch_progress = {
                        "total": total_accounts,
                        "completed": index - 1,
                        "phase": "aborted",
                        "current_account": account,
                        "message": "Stop requested",
                        "detail": "Stop requested",
                        "step": self.switch_progress.get("step", 0),
                        "step_total": self.switch_progress.get("step_total", 0),
                    }
                    break

                self.log_event(f"Switching to account: {account}")
                self.switch_progress = {
                    "total": total_accounts,
                    "completed": index - 1,
                    "phase": "switching",
                    "current_account": account,
                    "message": f"Switching to {account}",
                    "detail": "Preparing switch",
                    "step": 0,
                    "step_total": 0,
                }
                switched = self.steam_account_changer.switch_account(account, self._switch_step_hook(account))
                if not switched:
                    self.log_event(f"Skipping launches for account {account} due to switch failure.", "warning")
                    self.switch_progress = {
                        "total": total_accounts,
                        "completed": index - 1,
                        "phase": "failed",
                        "current_account": account,
                        "message": f"Switch failed for {account}",
                        "detail": "Switch failed",
                    }
                    continue

                self.switch_progress = {
                    "total": total_accounts,
                    "completed": index - 1,
                    "phase": "launching",
                    "current_account": account,
                    "message": f"Launching games for {account}",
                    "detail": "Launching configured games",
                }
                self.open_games(self.config.get("time_to_wait", 60))
                self.game_open_count += 1
                self.switch_progress = {
                    "total": total_accounts,
                    "completed": index,
                    "phase": "complete",
                    "current_account": account,
                    "message": f"Finished {account}",
                    "detail": "Switch complete",
                    "step": self.switch_progress.get("step_total", 0),
                    "step_total": self.switch_progress.get("step_total", 0),
                }
            self.switch_progress = None
        else:
            if not self.stop_event.is_set():
                self.open_games(self.config.get("time_to_wait", 60))
                self.game_open_count += 1

        if self.stop_event.is_set():
            try:
                self.steam_account_changer._restore_loginusers_backup()
            except Exception:
                pass
            self.current_state = "stopped"
            return

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
        self.switch_progress = None
        self.current_state = "stopped"
        self.log_event("Scheduler stopped", "warning")
        try:
            self.steam_account_changer._restore_loginusers_backup()
        except Exception:
            pass

    def pause_scheduler(self) -> None:
        self.paused = True
        self.stop_event.set()
        if self.worker_thread:
            self.worker_thread.join(timeout=3)
        self.worker_thread = None
        self.wait_progress = None
        self.switch_progress = None
        self.current_state = "stopped"
        self.log_event("Scheduler paused", "warning")
        # Force close any running games
        self._force_close_games()
        try:
            self.steam_account_changer._restore_loginusers_backup()
        except Exception:
            pass

    def _force_close_games(self) -> None:
        """Terminate all currently running games that were opened by AutoBanana."""
        all_games = self.get_steam_games()
        if not all_games:
            return
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if proc.info.get("name") in all_games:
                    proc.terminate()
                    self.log_event(f"Force closed {proc.info['name']} (PID: {proc.info['pid']})", "warning")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

    def _switch_step_hook(self, account_name: str):
        def hook(step_idx: int, total_steps: int, detail: str) -> None:
            self._update_switch_step(account_name, step_idx, total_steps, detail)

        return hook

    def _update_switch_step(self, account_name: str, step_idx: int, total_steps: int, detail: str) -> None:
        if not self.switch_progress:
            self.switch_progress = {}
        self.switch_progress.setdefault("phase", "switching")
        self.switch_progress["current_account"] = account_name
        self.switch_progress["detail"] = detail
        self.switch_progress["step"] = int(step_idx)
        self.switch_progress["step_total"] = max(1, int(total_steps))

    def manual_switch_account(self, account_name: Optional[str]) -> Tuple[bool, str]:
        if not account_name:
            return False, "Account name is required."

        if self.current_state != "waiting":
            return False, "Manual switching is only allowed while the scheduler is waiting."

        self.account_names = self.steam_account_changer.get_steam_login_user_names()
        match = next((name for name in self.account_names if name.lower() == account_name.lower()), None)
        if not match:
            return False, f"Account '{account_name}' is not in the remembered list."

        self.log_event(f"Manual switch requested for account: {match}")
        previous_state = self.current_state
        self.current_state = "switching"
        self.switch_progress = {
            "total": len(self.account_names),
            "completed": 0,
            "phase": "manual",
            "current_account": match,
            "message": f"Switching to {match}",
            "detail": "Preparing manual switch",
            "step": 0,
            "step_total": 0,
        }

        try:
            switched = self.steam_account_changer.switch_account(match, self._switch_step_hook(match))
        finally:
            self.current_state = previous_state
            try:
                # Ensure loginusers.vdf is restored even if SteamAccountChanger bails early
                self.steam_account_changer._restore_loginusers_backup()
            except Exception:
                self.log_event("Failed to restore Steam account roster after manual switch", "warning")

        if switched:
            self.switch_progress = None
            self.log_event(f"Manually switched to {match}", "success")
            return True, f"Switched to {match}."

        self.switch_progress = None
        self.log_event(f"Failed manual switch for {match}", "error")
        return False, f"Failed to switch to {match}."

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
            "wait_progress": self.wait_progress,
            "switch_progress": self.switch_progress,
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
            self.log_event("Quit requested from tray", "warning")
            self.stop()
            icon.visible = False
            icon.stop()
            os._exit(0)

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


@app.route("/api/switch-account", methods=["POST"])
def api_switch_account():
    if not service:
        return jsonify({"error": "Service not ready"}), 503
    payload = request.get_json(force=True, silent=True) or {}
    account = payload.get("account") if isinstance(payload, dict) else None
    ok, message = service.manual_switch_account(account)
    if ok:
        return jsonify({"status": "ok", "message": message})
    return jsonify({"error": message}), 400


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
