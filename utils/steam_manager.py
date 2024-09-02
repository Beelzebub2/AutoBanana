import logging
import subprocess
import winreg as reg
import os
import vdf
import time

logger = logging.getLogger('main')

class SteamAccountChanger:
    def __init__(self):
        """
        Initializes the SteamAccountChanger class.
        """
        self.steam_path = self.get_steam_install_location()

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

    def get_steam_login_user_names(self):
        """
        Loads the loginusers.vdf file from the Steam installation directory and retrieves a list of Steam account names.

        Returns:
            list: A list of account names.
        """
        if not self.steam_path:
            return []
        
        vdf_path = os.path.join(self.steam_path, 'config', 'loginusers.vdf')
        try:
            with open(vdf_path, 'r', encoding='utf-8') as vdf_file:
                loginusers_vdf = vdf.load(vdf_file)
                account_names = [user['AccountName'] for user in loginusers_vdf['users'].values()]
                return account_names
        except FileNotFoundError:
            logger.error(f"Unable to locate loginusers.vdf in {vdf_path}")
            return []
        except Exception as e:
            logger.error(f"An error occurred while loading the loginusers.vdf file: {e}")
            return []

    def kill_steam(self):
        """
        Terminates the Steam process if it is running.
        """
        subprocess.run(["taskkill.exe", "/F", "/IM", "steam.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)

    def open_steam(self):
        """
        Attempts to open Steam and verifies if it opened successfully.
        Retries up to 3 times if Steam does not open.
        """
        max_attempts = 3
        for attempt in range(max_attempts):
            subprocess.call("start steam://open/main", creationflags=subprocess.DETACHED_PROCESS, shell=True)
            time.sleep(5)  # Wait a few seconds to check if Steam opens
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
        reg_path = r"Software\Valve\Steam"
        try:
            key = reg.OpenKey(reg.HKEY_CURRENT_USER, reg_path, 0, reg.KEY_WRITE)
            reg.SetValueEx(key, "AutoLoginUser", 0, reg.REG_SZ, username)
            reg.CloseKey(key)
            self.kill_steam()
            if not self.open_steam():
                logger.error("Failed to restart Steam. Please try manually.")
        except Exception as e:
            logger.error(f"Failed to switch account due to: {e}")
