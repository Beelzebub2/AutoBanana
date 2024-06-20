import os
import sys
import webbrowser
import time
import logging
import configparser
import uuid
import requests
from datetime import datetime
import winreg as reg
import psutil
from colorama import init, Fore, Style
import threading


logging.basicConfig(filename='AutoBanana.log', level=logging.INFO,format='%(asctime)s - %(levelname)s - %(message)s')
init(autoreset=True)

class AutoBanana:
    def __init__(self):
        self.config = self.read_config()
        self.start_time = datetime.now()
        self.game_open_count = 0

    def read_config(self):
        config = configparser.ConfigParser()
        config.read('config.ini')
        return {
            'run_on_startup': config['Settings'].getboolean('run_on_startup', fallback=False),
            'steam_path': config['Settings'].get('steam_path', ''),
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
                    print(f"{Fore.YELLOW}{datetime.now().strftime(
                        '%Y-%m-%d %H:%M:%S')} - Already on startup")
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

    def open_games(self, time_to_wait):
        def open_single_game(game_id):
            try:
                steam_run_url = f"steam://rungameid/{game_id}"
                webbrowser.open(steam_run_url)
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                logging.info(f"{timestamp} - Opened {steam_run_url}")
                print(f"{Fore.YELLOW}{timestamp} - {Fore.GREEN}Opened {steam_run_url}")
                time.sleep(time_to_wait)
                self.close_program("Banana.exe")
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                log_message = f"{timestamp} - Closed {steam_run_url}\n"
                logging.info(log_message.strip())
                print(f"{Fore.YELLOW}{timestamp} - {Fore.RED}Closed {steam_run_url}")
            except Exception as e:
                logging.error(f"Failed to open or close the game: {e}")

        try:
            self.clear_console()
            with open("logo.txt", 'r', encoding='utf-8') as file:
                logo = file.read()
            print(self.fire(logo))
            
            threads = []
            for game_id in self.config['games']:
                thread = threading.Thread(target=open_single_game, args=(game_id,))
                thread.start()
                threads.append(thread)
            
            for thread in threads:
                thread.join()
        except Exception as e:
            logging.error(f"Failed to open or close the game: {e}")



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
