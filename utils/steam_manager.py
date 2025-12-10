import logging
import subprocess
import winreg as reg
import os
import vdf
import time
import shutil
from typing import Dict, Optional

logger = logging.getLogger('main')

class SteamAccountChanger:
    def __init__(self):
        """
        Initializes the SteamAccountChanger class.
        """
        self.steam_path = self.get_steam_install_location()
        self.loginusers_path = self._build_loginusers_path()
        self.steam_exe = os.path.join(self.steam_path, "steam.exe") if self.steam_path else None
        self._last_backup: Optional[Dict] = None

    def get_steam_install_location(self):
        """
        Retrieves the installation location of Steam from the Windows registry.

        Returns:
            str: The installation path of Steam.
        """
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
            return None

    def _build_loginusers_path(self) -> Optional[str]:
        if not self.steam_path:
            return None
        return os.path.join(self.steam_path, 'config', 'loginusers.vdf')

    def _load_loginusers(self) -> Dict:
        if not self.loginusers_path:
            return {}

        try:
            with open(self.loginusers_path, 'r', encoding='utf-8') as vdf_file:
                return vdf.load(vdf_file)
        except FileNotFoundError:
            logger.error(f"Unable to locate loginusers.vdf in {self.loginusers_path}")
            return {}
        except Exception as e:
            logger.error(f"An error occurred while loading the loginusers.vdf file: {e}")
            return {}

    def _write_loginusers(self, loginusers: Dict) -> bool:
        if not self.loginusers_path:
            return False

        try:
            with open(self.loginusers_path, 'w', encoding='utf-8') as vdf_file:
                vdf.dump(loginusers, vdf_file)
            return True
        except Exception as e:
            logger.error(f"Unable to write loginusers.vdf: {e}")
            return False

    def _write_single_user_loginusers(self, target_user_id: str, user_data: Dict) -> bool:
        """Temporarily write loginusers with only the target user to skip the account picker."""
        minimal = {
            "users": {
                target_user_id: user_data
            }
        }
        return self._write_loginusers(minimal)

    def _restore_loginusers_backup(self):
        if self._last_backup is None:
            return
        self._write_loginusers(self._last_backup)
        self._last_backup = None

    def _set_autologin_registry(self, username: str) -> bool:
        reg_path = r"Software\\Valve\\Steam"
        try:
            key = reg.OpenKey(reg.HKEY_CURRENT_USER, reg_path, 0, reg.KEY_WRITE)
            reg.SetValueEx(key, "AutoLoginUser", 0, reg.REG_SZ, username)
            reg.CloseKey(key)
            return True
        except Exception as e:
            logger.error(f"Failed setting AutoLoginUser registry key: {e}")
            return False

    def get_steam_login_user_names(self):
        """
        Loads the loginusers.vdf file from the Steam installation directory and retrieves a list of Steam account names.

        Returns:
            list: A list of account names.
        """
        loginusers_vdf = self._load_loginusers()
        if not loginusers_vdf:
            return []

        try:
            return [user.get('AccountName', '') for user in loginusers_vdf.get('users', {}).values() if user.get('AccountName')]
        except Exception as e:
            logger.error(f"An error occurred while parsing loginusers.vdf: {e}")
            return []

    def kill_steam(self):
        """
        Terminates the Steam process if it is running.
        """
        for proc_name in ("steam.exe", "steamwebhelper.exe"):
            subprocess.run(["taskkill.exe", "/F", "/IM", proc_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
        time.sleep(1.5)

    def open_steam(self):
        """
        Attempts to open Steam and verifies if it opened successfully.
        Retries up to 3 times if Steam does not open.
        """
        max_attempts = 3
        for attempt in range(max_attempts):
            launch_cmd = None
            if self.steam_exe and os.path.exists(self.steam_exe):
                # -silent keeps UI minimal, -noreactlogin skips the account chooser React dialog
                launch_cmd = f'start "" "{self.steam_exe}" -silent -noreactlogin'
            else:
                launch_cmd = "start steam://open/main"

            subprocess.call(launch_cmd, creationflags=subprocess.DETACHED_PROCESS, shell=True)
            time.sleep(8)  # Give Steam a bit more time to initialize past the chooser
            if self.is_steam_running():
                logger.info("Steam opened successfully.")
                return True
            else:
                logger.info(f"Attempt {attempt + 1} failed to open Steam. Retrying...")
        logger.error("Failed to open Steam after multiple attempts.")
        return False

    def is_steam_running(self):
        """
        Checks if the Steam process is currently running.

        Returns:
            bool: True if Steam is running, False otherwise.
        """
        try:
            output = subprocess.check_output("tasklist", shell=True)
            return b"steam.exe" in output
        except subprocess.CalledProcessError:
            return False

    def switch_account(self, username):
        """
        Switches the Steam account by setting the AutoLoginUser in the registry and restarting Steam.

        Args:
            username (str): The username to switch to.
        """
        if not username:
            logger.error("No username provided to switch_account.")
            return False

        loginusers_vdf = self._load_loginusers()
        users = loginusers_vdf.get('users', {}) if loginusers_vdf else {}

        # Backup full loginusers in-memory and on disk once per switch
        self._last_backup = loginusers_vdf

        target_user_id = None
        for user_id, user_data in users.items():
            if user_data.get('AccountName', '').lower() == username.lower():
                target_user_id = user_id
                break

        if not target_user_id:
            logger.error(f"Account '{username}' not found in loginusers.vdf")
            return False

        self.kill_steam()

        # Persist all accounts but temporarily write single-user file to skip picker
        for user_id, user_data in users.items():
            is_target = user_id == target_user_id
            user_data['MostRecent'] = "1" if is_target else "0"
            user_data['RememberPassword'] = "1"
            user_data['AllowAutoLogin'] = "1" if is_target else user_data.get('AllowAutoLogin', "1")

        target_user = users.get(target_user_id, {})
        users[target_user_id] = target_user

        # Backup full loginusers in-memory and on disk once per switch
        try:
            if self.loginusers_path and os.path.exists(self.loginusers_path):
                shutil.copy(self.loginusers_path, self.loginusers_path + ".bak")
        except Exception:
            pass

        # Write single-user file to bypass chooser
        if not self._write_single_user_loginusers(target_user_id, target_user):
            return False

        if not self._set_autologin_registry(username):
            return False

        # Clear any previously running Steam to avoid being stuck at account chooser
        self.kill_steam()

        if not self.open_steam():
            logger.error("Failed to restart Steam. Please try manually.")
            return False

        # Restore full loginusers so other accounts remain available after launch
        self._restore_loginusers_backup()

        logger.info(f"Switched to Steam account: {username}")
        return True
