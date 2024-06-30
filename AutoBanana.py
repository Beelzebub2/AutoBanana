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


logging.basicConfig(filename='AutoBanana.log', level=logging.INFO,format='%(asctime)s - %(levelname)s - %(message)s')
init(autoreset=True)

class AutoBanana:
    def __init__(self):
        self.config = self.read_config()
        self.start_time = datetime.now()
        self.game_open_count = 0
        self.steam_install_location = self.get_steam_install_location()

    def read_config(self):
        config = configparser.ConfigParser()

        # Check if the config file exists, if not download it from the repository
        if not os.path.exists("config.ini"):
            config_url = "https://raw.githubusercontent.com/Beelzebub2/AutoBanana/main/config.ini"
            response = requests.get(config_url)
            with open("config.ini", 'w') as file:
                file.write(response.text)

        config.read('config.ini')
        return {
            'run_on_startup': config['Settings'].getboolean('run_on_startup', fallback=False),
            'games': [game.strip() for game in config['Settings'].get('games', '').split(',')],
            'time_to_wait': config['Settings'].getint('time_to_wait', fallback=20),
        }



    def add_to_startup(self):
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
        steam_key = reg.OpenKey(
            reg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Wow6432Node\Valve\Steam",
        )

        steam_install_location = reg.QueryValueEx(steam_key, "InstallPath")[0]

        reg.CloseKey(steam_key)

        return steam_install_location

    # Return the install path of the game
    def get_game_install_path(self, app_id):
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
        games = {}

        for game_id in self.config['games']:
            install_path = self.get_game_install_path(game_id)
            if install_path:
                for _, _, files in os.walk(install_path):
                    for file in files:
                        if file.endswith(".exe") and file != "UnityCrashHandler64.exe" and file != "UnityCrashHandler32.exe":
                            games[file] = install_path

        return games


    def open_games(self, time_to_wait):
        all_games = self.get_steam_games()

        def find_running_steam_games(steam_games):
            running_games = []
            for proc in psutil.process_iter(['pid', 'name', 'create_time']):
                if proc.info['name'] in steam_games:
                    start_time = datetime.fromtimestamp(proc.info['create_time'])
                    current_time = datetime.now()
                    process_age = current_time - start_time
                    running_games.append((proc, start_time, process_age))
            return running_games

        def open_single_game(game_id):
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
            # If the logo file is not found, download it from the repository
            if not os.path.exists("logo.txt"):
                logo_url = "https://raw.githubusercontent.com/Beelzebub2/AutoBanana/main/logo.txt"
                response = requests.get(logo_url)
                with open("logo.txt", 'w', encoding='utf-8') as file:
                    file.write(response.text)

            with open("logo.txt", 'r', encoding='utf-8') as file:
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
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] == process_name:
                proc.terminate()
                break

    def clear_console(self):
        if os.name == 'nt':
            os.system('cls')
        else:
            os.system('clear')

    def fire(self, text):
        fade = ""
        green = 250
        for line in text.splitlines():
            fade += f"\033[38;2;255;{green};0m{line}\033[0m\n"
            green = max(0, green - 25)
        return fade

    def countdown(self, seconds):
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
        try:
            with open('user_id.txt', 'r') as file:
                user_id = file.read()
        except FileNotFoundError:
            user_id = str(uuid.uuid4())
            with open('user_id.txt', 'w') as file:
                file.write(user_id)

        if not os.path.exists('usage_logged.txt'):
            web_app_url = 'https://script.google.com/macros/s/AKfycbxKQlXPVPq38RxqaqtOwGWTgpmNQIZyu2q2aAH5mSsvxlCiRe9jToIzv7yBA8kZECZ0/exec'
            response = requests.post(web_app_url, data={'user_id': user_id})
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            if response.status_code == 200:
                with open('usage_logged.txt', 'w') as file:
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
    auto_banana = AutoBanana()
    auto_banana.main()
    input(Fore.CYAN + "\nPress Enter to exit..." + Style.RESET_ALL)
