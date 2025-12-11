import copy
import logging
import os
import shutil
import subprocess
import time
from typing import Callable, Dict, Optional

try:  # winreg is Windows-only
    import winreg as reg
except ImportError:
    reg = None
import vdf

logger = logging.getLogger("main")


class SteamAccountChanger:
    def __init__(self):
        """Manage Steam account switching across Windows and Linux."""
        self.is_windows = os.name == "nt"
        self.steam_path = self.get_steam_install_location()
        self.loginusers_path = self._build_loginusers_path()
        self.steam_exe = self._detect_steam_binary()
        self._last_backup: Optional[Dict] = None

    def _detect_steam_binary(self) -> Optional[str]:
        if not self.steam_path:
            return None
        if self.is_windows:
            candidate = os.path.join(self.steam_path, "steam.exe")
            return candidate if os.path.exists(candidate) else None
        for candidate in (
            os.path.join(self.steam_path, "steam.sh"),
            os.path.join(self.steam_path, "steam"),
            "/usr/bin/steam",
        ):
            if os.path.exists(candidate):
                return candidate
        return None

    def get_steam_install_location(self) -> Optional[str]:
        """Locate the Steam install directory on Windows or Linux."""
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
                logger.error("Steam is not installed or registry key is missing.")
            except Exception as exc:
                logger.error(f"Failed to read Steam path: {exc}")

        for path in (
            os.environ.get("STEAM_PATH"),
            os.path.expanduser("~/.local/share/Steam"),
            os.path.expanduser("~/.steam/steam"),
            os.path.expanduser("~/.steam/root"),
        ):
            if path and os.path.exists(path):
                return path

        logger.error("Steam path not found; set STEAM_PATH if installed in a custom location.")
        return None

    def _build_loginusers_path(self) -> Optional[str]:
        if not self.steam_path:
            return None
        return os.path.join(self.steam_path, "config", "loginusers.vdf")

    def _load_loginusers(self) -> Dict:
        if not self.loginusers_path:
            return {}

        try:
            with open(self.loginusers_path, "r", encoding="utf-8") as vdf_file:
                return vdf.load(vdf_file)
        except FileNotFoundError:
            logger.error(f"Unable to locate loginusers.vdf in {self.loginusers_path}")
            return {}
        except Exception as exc:
            logger.error(f"An error occurred while loading the loginusers.vdf file: {exc}")
            return {}

    def _write_loginusers(self, loginusers: Dict) -> bool:
        if not self.loginusers_path:
            return False

        try:
            with open(self.loginusers_path, "w", encoding="utf-8") as vdf_file:
                vdf.dump(loginusers, vdf_file)
            return True
        except Exception as exc:
            logger.error(f"Unable to write loginusers.vdf: {exc}")
            return False

    def _backup_loginusers(self, loginusers: Dict):
        """Keep an in-memory copy and refresh the on-disk .bak for restores."""
        self._last_backup = copy.deepcopy(loginusers) if loginusers else None
        if self.loginusers_path and os.path.exists(self.loginusers_path):
            try:
                shutil.copy(self.loginusers_path, self.loginusers_path + ".bak")
            except Exception as exc:
                logger.warning(f"Unable to snapshot loginusers.vdf: {exc}")

    def _write_single_user_loginusers(self, target_user_id: str, user_data: Dict) -> bool:
        """Temporarily write loginusers with only the target user to skip the account picker."""
        minimal = {"users": {target_user_id: user_data}}
        return self._write_loginusers(minimal)

    def _restore_loginusers_backup(self):
        if self._last_backup:
            if self._write_loginusers(self._last_backup):
                self._last_backup = None
                return
        bak_path = f"{self.loginusers_path}.bak" if self.loginusers_path else None
        if bak_path and os.path.exists(bak_path):
            try:
                shutil.copy(bak_path, self.loginusers_path)
                self._last_backup = None
            except Exception as exc:
                logger.error(f"Unable to restore Steam account list backup: {exc}")

    def _notify_progress(self, progress_hook: Optional[Callable[[int, int, str], None]], step: int, total: int, message: str) -> None:
        if not progress_hook:
            return
        try:
            progress_hook(step, total, message)
        except Exception:
            pass

    def _set_autologin_registry(self, username: str) -> bool:
        if not self.is_windows or reg is None:
            return True
        reg_path = r"Software\\Valve\\Steam"
        try:
            key = reg.OpenKey(reg.HKEY_CURRENT_USER, reg_path, 0, reg.KEY_WRITE)
            reg.SetValueEx(key, "AutoLoginUser", 0, reg.REG_SZ, username)
            reg.CloseKey(key)
            return True
        except Exception as exc:
            logger.error(f"Failed setting AutoLoginUser registry key: {exc}")
            return False

    def get_steam_login_user_names(self):
        """Return saved Steam account names."""
        loginusers_vdf = self._load_loginusers()
        if not loginusers_vdf:
            return []

        try:
            return [user.get("AccountName", "") for user in loginusers_vdf.get("users", {}).values() if user.get("AccountName")]
        except Exception as exc:
            logger.error(f"An error occurred while parsing loginusers.vdf: {exc}")
            return []

    def kill_steam(self):
        """Terminate Steam processes."""
        if self.is_windows:
            for proc_name in ("steam.exe", "steamwebhelper.exe"):
                subprocess.run(["taskkill.exe", "/F", "/IM", proc_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
        else:
            subprocess.run(["pkill", "-f", "steam"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.5)

    def open_steam(self):
        """Start Steam and wait briefly for it to come up."""
        max_attempts = 3
        for attempt in range(max_attempts):
            if self.steam_exe and os.path.exists(self.steam_exe):
                if self.is_windows:
                    launch_cmd = f'start "" "{self.steam_exe}" -silent -noreactlogin'
                    subprocess.call(launch_cmd, creationflags=subprocess.DETACHED_PROCESS, shell=True)
                else:
                    subprocess.Popen([self.steam_exe, "-silent", "-noreactlogin"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                if self.is_windows:
                    launch_cmd = "start steam://open/main"
                    subprocess.call(launch_cmd, creationflags=subprocess.DETACHED_PROCESS, shell=True)
                else:
                    subprocess.Popen(["steam", "-silent", "-noreactlogin"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            time.sleep(8)
            if self.is_steam_running():
                logger.info("Steam opened successfully.")
                return True

            logger.info(f"Attempt {attempt + 1} failed to open Steam. Retrying...")

        logger.error("Failed to open Steam after multiple attempts.")
        return False

    def is_steam_running(self):
        """Check if Steam process is alive."""
        try:
            if self.is_windows:
                output = subprocess.check_output("tasklist", shell=True)
                return b"steam.exe" in output
            result = subprocess.run(["pgrep", "-f", "steam"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return result.returncode == 0
        except subprocess.CalledProcessError:
            return False

    def switch_account(self, username, progress_hook: Optional[Callable[[int, int, str], None]] = None):
        """Switch Steam account by adjusting loginusers and restarting Steam."""
        if not username:
            logger.error("No username provided to switch_account.")
            return False

        total_steps = 6
        self._notify_progress(progress_hook, 1, total_steps, f"Locating account '{username}'")
        loginusers_vdf = self._load_loginusers()
        users = loginusers_vdf.get("users", {}) if loginusers_vdf else {}

        self._backup_loginusers(loginusers_vdf)

        target_user_id = None
        for user_id, user_data in users.items():
            if user_data.get("AccountName", "").lower() == username.lower():
                target_user_id = user_id
                break

        if not target_user_id:
            logger.error(f"Account '{username}' not found in loginusers.vdf")
            return False

        self.kill_steam()
        self._notify_progress(progress_hook, 2, total_steps, "Stopping running Steam processes")

        for user_id, user_data in users.items():
            is_target = user_id == target_user_id
            user_data["MostRecent"] = "1" if is_target else "0"
            user_data["RememberPassword"] = "1"
            user_data["AllowAutoLogin"] = "1" if is_target else user_data.get("AllowAutoLogin", "1")

        target_user = users.get(target_user_id, {})
        users[target_user_id] = target_user

        single_user_written = False

        if not self._write_single_user_loginusers(target_user_id, target_user):
            self._restore_loginusers_backup()
            return False
        single_user_written = True
        self._notify_progress(progress_hook, 3, total_steps, f"Writing single-user login file for {username}")

        if not self._set_autologin_registry(username):
            if single_user_written:
                self._restore_loginusers_backup()
            return False
        self._notify_progress(progress_hook, 4, total_steps, "Updating auto-login registry")

        self.kill_steam()

        if not self.open_steam():
            logger.error("Failed to restart Steam. Please try manually.")
            if single_user_written:
                self._restore_loginusers_backup()
            return False
        self._notify_progress(progress_hook, 5, total_steps, "Restarting Steam client")

        self._restore_loginusers_backup()
        self._notify_progress(progress_hook, 6, total_steps, "Restoring full account roster")

        logger.info(f"Switched to Steam account: {username}")
        return True
