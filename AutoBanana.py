import os
import sys
import webbrowser
import time
import logging
import configparser
import uuid
import requests
from datetime import datetime, timedelta
import winreg as reg
import psutil
from colorama import init, Fore, Style
import vdf  # type: ignore

init(autoreset=True)

class AutoBanana:
    def __init__(self):
        self.appdata_path = os.path.join(os.getenv("APPDATA"), "AutoBanana")
        self.base_url = "https://raw.githubusercontent.com/Beelzebub2/AutoBanana/main/"
        if not os.path.exists(self.appdata_path):
            os.makedirs(self.appdata_path)

        self.download_file_if_not_exists("logo.txt", ".")
        if os.path.exists("logo.txt") and os.path.exists(self.appdata_path):
            os.replace("logo.txt", os.path.join(self.appdata_path, "logo.txt"))

        self.logo_file = os.path.join(self.appdata_path, "logo.txt")
        self.user_id_file = os.path.join(self.appdata_path, "user_id.txt")
        self.usage_logged_file = os.path.join(self.appdata_path, "usage_logged.txt")

        logging.basicConfig(filename=os.path.join(self.appdata_path, "AutoBanana.log"), level=logging.INFO,format='%(asctime)s - %(levelname)s - %(message)s')
        
        self.config = self.read_config()
        self.start_time = datetime.now()
        self.game_open_count = 0
        self.steam_install_location = self.get_steam_install_location()
        # Update config to remove games not installed
        self.update_config_file()
        self.config = self.read_config()

        

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
                    print(f"{Fore.YELLOW}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Already on startup")
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
        '''This Python function searches for the installation path of a game using the provided app ID in
        Steam directories.
        
        Parameters
        ----------
        app_id
            The `get_game_install_path` function you provided is a method that helps retrieve the
        installation path of a game based on its `app_id`. The function first checks if the game is
        installed in the Steam directory and then searches through the library folders if it's not found
        in the default location.
        
        Returns
        -------
            The `get_game_install_path` function returns the installation path of a game with the specified
        app ID. If the game is installed in Steam, it will search for the game in the Steam library
        folders and return the installation path if found. If the game is not found in the Steam library
        folders, it will return `None`.
        
        '''

        # Check if the game is installed in Steam
        steam_apps_path = os.path.join(self.steam_install_location, "steamapps")

        for root, dirs, files in os.walk(steam_apps_path):
            for file in files:
                if file == "appmanifest_" + app_id + ".acf":
                    with open(os.path.join(root, file), "r") as f:
                        manifest = vdf.load(f)

                        install_location = os.path.join(
                            steam_apps_path, "common", manifest["AppState"]["installdir"]
                        )

                    # Check if install location exists
                    if os.path.exists(install_location):
                        return install_location

        # If not, check the library folders
        library_folders = os.path.join(
            self.steam_install_location, "steamapps", "libraryfolders.vdf"
        )

        # Find app id in library folders
        with open(library_folders, "r") as f:
            library = vdf.load(f)

            for key in library["libraryfolders"]:
                if key == "0":
                    continue

                library_path = library["libraryfolders"][key]["path"]
                apps = library["libraryfolders"][key]["apps"]

                if app_id in apps:
                    for root, dirs, files in os.walk(
                        os.path.join(library_path, "steamapps")
                    ):
                        for file in files:
                            if file == "appmanifest_" + app_id + ".acf":
                                with open(os.path.join(root, file), "r") as f:
                                    manifest = vdf.load(f)

                                    install_location = os.path.join(
                                        library_path,
                                        "steamapps",
                                        "common",
                                        manifest["AppState"]["installdir"],
                                    )

                                    # Check if install location exists
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
        '''The function updates a configuration file by removing any games that are not installed from the
        list of games.
        '''
        self.config = self.read_config()
        games = self.config['games']
        installed_games = [game for game in games if self.get_game_install_path(game.strip())]

        config_parser = configparser.ConfigParser()
        config_parser.read("config.ini")
        config_parser.set("Settings", "games", ",".join(installed_games))

        with open("config.ini", "w") as configfile:
            config_parser.write(configfile)

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
                print(f"{Fore.YELLOW}{timestamp} - {Fore.GREEN}Opened {steam_run_url}")
            except Exception as e:
                logging.error(f"Failed to open the game: {e}")

        try:
            self.clear_console()
            with open(self.logo_file, 'r', encoding='utf-8') as file:
                logo = file.read()
            print(self.fire(logo))

            for game_id in self.config['games']:
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
                    print(f"{Fore.YELLOW}{timestamp} - {Fore.RED}Closed {proc.info['name']} (PID: {proc.info['pid']})")
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

    def fire(self, text):
        '''The function `fire` takes a text input and applies a color fade effect to each line,
        transitioning from green to black.
        
        Parameters
        ----------
        text
            The `fire` method takes a `text` input, which is a string containing one or more lines of text.
        The method then processes each line of text to create a "fire effect" by changing the color of
        the text from green to red gradually. The method returns the processed text with the
        
        Returns
        -------
            The `fire` method takes a text input, splits it into lines, and then generates a colored output
        where each line has a fading green color effect. The color starts as bright green (RGB 255, 250,
        0) and gradually fades to darker green as the lines progress. The method returns the formatted
        text with the fading green effect applied.
        
        '''
        fade = ""
        green = 250
        for line in text.splitlines():
            fade += f"\033[38;2;255;{green};0m{line}\033[0m\n"
            green = max(0, green - 25)
        return fade

    def countdown(self, seconds):
        '''The `countdown` function in Python displays a countdown timer with additional status information
        until a specified number of seconds elapse.
        
        Parameters
        ----------
        seconds
            The `seconds` parameter in the `countdown` function represents the total number of seconds for
        which the countdown will run. The function will display a countdown timer that decrements by 1
        second each time until it reaches 0. During this countdown, it will also display the current
        time, time
        
        '''
        while seconds:
            uptime = datetime.now() - self.start_time
            hours, remainder = divmod(seconds, 3600)
            minutes, seconds_remaining = divmod(remainder, 60)
            time_left = f"{Fore.YELLOW}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Time until next game open: {Fore.CYAN}{hours:02}:{minutes:02}:{seconds_remaining:02}{Fore.RESET}"
            status = f" | {Fore.MAGENTA}Total games: {Fore.RED}{len(self.config['games'])} {Fore.RESET}| {Fore.MAGENTA}Game opened: {Fore.RED}{self.game_open_count}{Fore.RESET} times | {Fore.MAGENTA}Uptime: {Fore.RED}{str(uptime).split('.')[0]}{Fore.RESET}"
            print(time_left + status, end='\r')
            time.sleep(1)
            seconds -= 1

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
                print(f"{Fore.YELLOW}{timestamp} - {Fore.GREEN}Usage logged successfully.")
            else:
                logging.error(f"{timestamp} - Failed to log usage.")
        else:
            print(f"{Fore.YELLOW}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {Fore.GREEN}Usage already logged.")


    def main(self):
        self.register()
        if self.config['run_on_startup']:
            self.add_to_startup()
        else:
            self.remove_from_startup()

        while True:
            self.open_games(self.config['time_to_wait'])
            self.game_open_count += 1
            self.countdown(3 * 60 * 60)


if __name__ == "__main__":
    try:
        auto_banana = AutoBanana()
        auto_banana.main()
    except KeyboardInterrupt:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n\n{Fore.YELLOW}{timestamp} - {Fore.LIGHTGREEN_EX}Program exited gracefully.")