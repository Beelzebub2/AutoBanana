import configparser
import itertools
import logging
import os
import sys
import time
import uuid
import webbrowser
import winreg as reg
from datetime import datetime, timedelta

import psutil
import requests
import vdf  # type: ignore
from colorama import Fore, init
import utils
import utils.steam_manager
import utils.theme_manager

init(autoreset=True)


class AutoBanana:

    def __init__(self):
        self.base_url = "https://raw.githubusercontent.com/Beelzebub2/AutoBanana/main/"

        self.download_file_if_not_exists("logo.txt", ".")
        self.download_file_if_not_exists("startup.txt", ".")
        self.logo_file = "logo.txt"
        self.startup_logo_file = "startup.txt"
        self.user_id_file = "user_id.txt"
        self.usage_logged_file = "usage_logged.txt"

        logging.basicConfig(filename="AutoBanana.log", level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        logging.getLogger("main")
        with open(self.logo_file, 'r', encoding='utf-8') as file:
            self.logo = file.read()
            file.close()
        with open(self.startup_logo_file, 'r', encoding='utf-8') as file:
            self.startup_logo = file.read()
            file.close()
        self.config = self.read_config()
        self.start_time = datetime.now()
        self.game_open_count = 0
        self.steam_install_location = self.get_steam_install_location()
        self.theme_function = None
        self.colorama_color = Fore.LIGHTWHITE_EX
        # Update config to remove games not installed
        self.update_config_file()
        self.config = self.read_config()
        self.themes = utils.theme_manager
        self.steam_account_changer = utils.steam_manager.SteamAccountChanger()
        self.apply_theme()

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
            'games': [game.strip() for game in config['Settings'].get('games', '').split(',')],
            'time_to_wait': config['Settings'].getint('time_to_wait', fallback=20),
            'batch_size': config['Settings'].getint('batch_size', fallback=5),
            'theme': config['Settings'].get('theme', fallback='default'),
            'switch_steam_accounts': config['Settings'].getboolean('switch_steam_accounts', fallback=False)
        }

    def add_to_startup(self):
        '''This Python function adds the script to the Windows startup registry to run automatically on
        system boot.

        '''
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
        '''The function `get_steam_install_location` retrieves the installation location of Steam from the
        Windows registry.

        Returns
        -------
            The function `get_steam_install_location` returns the installation location of Steam as a
        string.

        '''
        steam_key = reg.OpenKey(
            reg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Wow6432Node\Valve\Steam",
        )

        steam_install_location = reg.QueryValueEx(steam_key, "InstallPath")[0]

        reg.CloseKey(steam_key)

        return steam_install_location

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
        # Read the current config file into memory
        with open("config.ini", "r") as configfile:
            lines = configfile.readlines()

        # Update the games list
        self.config = self.read_config()
        games = self.config['games']
        installed_games = [game for game in games if self.get_game_install_path(game.strip())]
        new_games_line = f"games = {','.join(installed_games)}\n"

        # Write the updated config back to the file, preserving comments
        with open("config.ini", "w") as configfile:
            for line in lines:
                if line.startswith("games ="):
                    configfile.write(new_games_line)
                else:
                    configfile.write(line)

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
                print(f"{self.colorama_color}{timestamp} - {Fore.GREEN}Opened {steam_run_url}")
            except Exception as e:
                logging.error(f"Failed to open the game: {e}")

        def batch(iterable, n=1):
            it = iter(iterable)
            while True:
                chunk = list(itertools.islice(it, n))
                if not chunk:
                    break
                yield chunk

        try:
            self.clear_console()
            print(self.theme_function(self.logo))

            games = self.config['games']

            for game_batch in batch(games, self.config['batch_size']):
                for game_id in game_batch:
                    open_single_game(game_id)
                    time.sleep(1)

                time.sleep(time_to_wait)

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
                    print(f"{self.colorama_color}{timestamp} - {Fore.RED}Closed {proc.info['name']} (PID: {proc.info['pid']})")
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
        Displays a countdown timer with additional status information until the specified number of seconds elapse.

        Parameters
        ----------
        seconds : int
            The total number of seconds for which the countdown will run.
            The countdown timer decrements by 1 second each time until it reaches 0,
            displaying the current time and additional status information.
        """
        while seconds:
            # Calculate the uptime
            uptime = datetime.now() - self.start_time

            # Calculate hours, minutes, and seconds remaining
            hours, remainder = divmod(seconds, 3600)
            minutes, seconds_remaining = divmod(remainder, 60)

            # Construct the time left message
            time_left = (
                f"{self.colorama_color}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - "
                f"Time until next run: {Fore.CYAN}{hours:02}:{minutes:02}:{seconds_remaining:02}{Fore.RESET}"
            )

            # Construct the status message
            status = (
                f" | {Fore.MAGENTA}Total games: {Fore.RED}{len(self.config['games'])} {Fore.RESET}"
                f"| {Fore.MAGENTA}Total accounts: {Fore.RED}{len(self.steam_account_changer.get_steam_login_user_names())} {Fore.RESET}"
                f"| {Fore.MAGENTA}Game opened: {Fore.RED}{self.game_open_count} {Fore.RESET}"
                f"{'times' if self.game_open_count > 1 else 'time'} "
                f"| {Fore.MAGENTA}Uptime: {Fore.RED}{str(uptime).split('.')[0]}{Fore.RESET}"
            )

            # Output the countdown and status information
            sys.stdout.write('\r' + time_left + status)
            sys.stdout.flush()

            # Wait for a second and decrement the countdown
            time.sleep(1)
            seconds -= 1

        # Print a new line after the countdown completes
        print()

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
        os.system(f"mode con: cols={width} lines={height}")

    def string_width(self, multiline_string):
        lines = multiline_string.split('\n')
        max_length = max(len(line) for line in lines)
        return max_length

    def apply_theme(self):
        '''The function `apply_theme` sets the theme and color scheme based on the configuration provided.

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
            case 'default':
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

    def main(self):
        self.clear_console()
        print(self.theme_function(self.startup_logo))
        self.register()
        if self.config['run_on_startup']:
            self.add_to_startup()
        else:
            self.remove_from_startup()
        self.account_names = self.steam_account_changer.get_steam_login_user_names()
        while True:
            if self.config['switch_steam_accounts']:
                for account in self.account_names:
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    print(f"{self.colorama_color}{timestamp} - {Fore.LIGHTWHITE_EX}Switching to account: {account}")
                    self.steam_account_changer.switch_account(account)
                    time.sleep(10)
                    self.open_games(self.config['time_to_wait'])
                self.game_open_count += 1
                self.countdown(3 * 60 * 60)
                self.config = self.read_config()
            else:
                self.open_games(self.config['time_to_wait'])
                self.game_open_count += 1
                self.countdown(3 * 60 * 60)
            # Update the games list before the next iteration
            self.config = self.read_config()


if __name__ == "__main__":
    try:
        os.system("title AutoBanana v2.2")
        auto_banana = AutoBanana()
        auto_banana.set_terminal_size(auto_banana.string_width(auto_banana.logo) + 20, 30)
        auto_banana.main()
    except KeyboardInterrupt:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n\n{auto_banana.colorama_color}{timestamp} - {Fore.LIGHTGREEN_EX}Program exited gracefully.")
