import time
import webbrowser
import psutil
from datetime import datetime
import configparser
import os
import sys
import winreg as reg
import logging

logging.basicConfig(filename='AutoBanana.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


def read_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    settings = {
        'run_on_startup': config['Settings'].getboolean('run_on_startup', fallback=False),
        'program_path': config['Settings'].get('program_path', ''),
        'time_to_wait': config['Settings'].getint('time_to_wait', fallback=20),
        'install_game': config['Settings'].getboolean('install_game', fallback=False)
    }
    return settings


def add_to_startup():
    script_path = os.path.abspath(sys.argv[0])
    key = reg.HKEY_CURRENT_USER
    key_value = r'Software\Microsoft\Windows\CurrentVersion\Run'
    try:
        open_key = reg.OpenKey(key, key_value, 0, reg.KEY_ALL_ACCESS)
        existing_value, _ = reg.QueryValueEx(open_key, 'OpenBanana')

        if existing_value == script_path:
            print("Already added to startup")
        else:
            reg.SetValueEx(open_key, 'OpenBanana', 0, reg.REG_SZ, script_path)
            logging.info("Successfully added to startup")
        reg.CloseKey(open_key)
    except FileNotFoundError:
        open_key = reg.OpenKey(key, key_value, 0, reg.KEY_ALL_ACCESS)
        reg.SetValueEx(open_key, 'OpenBanana', 0, reg.REG_SZ, script_path)
        reg.CloseKey(open_key)
        logging.info("Successfully added to startup")
    except Exception as e:
        logging.error(f"Failed to add to startup: {e}")


def remove_from_startup():
    key = reg.HKEY_CURRENT_USER
    key_value = r'Software\Microsoft\Windows\CurrentVersion\Run'
    try:
        open_key = reg.OpenKey(key, key_value, 0, reg.KEY_ALL_ACCESS)
        reg.DeleteValue(open_key, 'OpenBanana')
        reg.CloseKey(open_key)
        logging.info("Successfully removed from startup")
    except FileNotFoundError:
        print("Startup entry not found, nothing to remove")
    except Exception as e:
        logging.error(f"Failed to remove from startup: {e}")


def open_program(program_path, time_to_wait):
    try:
        steam_run_url = "steam://rungameid/2923300"
        webbrowser.open(steam_run_url)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"{timestamp} - Opened {steam_run_url}\n"
        logging.info(log_message.strip())
        time.sleep(time_to_wait)
        close_program("Banana.exe")
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"{timestamp} - Closed {steam_run_url}\n"
        logging.info(log_message.strip())
    except Exception as e:
        logging.error(f"Failed to open or close the game: {e}")


def close_program(process_name):
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] == process_name:
                try:
                    proc.terminate()
                    print(f"Terminated {process_name} with PID {
                          proc.info['pid']}")
                except psutil.NoSuchProcess:
                    pass
        end_time = time.time() + 10
        while time.time() < end_time:
            time.sleep(1)
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.info['name'] == process_name:
                    try:
                        proc.terminate()
                        print(f"Terminated {process_name} with PID {
                              proc.info['pid']}")
                    except psutil.NoSuchProcess:
                        pass
    except Exception as e:
        logging.error(f"Failed to terminate {process_name}: {e}")


def install_game():
    steam_install_url = "steam://install/2923300"

    try:
        webbrowser.open(steam_install_url)
        logging.info(f"Triggered installation of game from Steam: {
                     steam_install_url}")
        print(f"Installation of game triggered. Check your Steam client for progress.")

        config = configparser.ConfigParser()
        config.read('config.ini')
        config.set('Settings', 'install_game', 'False')
        with open('config.ini', 'w') as configfile:
            config.write(configfile)
            logging.info(
                "Updated install_game parameter in config.ini to False after installation.")
    except Exception as e:
        logging.error(f"Failed to trigger game installation: {e}")


def clear_console():
    if os.name == 'posix':
        _ = os.system('clear')
    elif os.name == 'nt':
        _ = os.system('cls')


def fire(text):
    os.system("")
    fade = ""
    green = 250
    for line in text.splitlines():
        fade += f"\033[38;2;255;{green};0m{line}\033[0m\n"
        if not green == 0:
            green -= 25
            if green < 0:
                green = 0
    return fade


def main():
    clear_console()
    with open("logo.txt", 'r', encoding='utf-8') as file:
        logo = file.read()
    print(fire(logo))
    config = read_config()
    if config['run_on_startup']:
        add_to_startup()
    else:
        remove_from_startup()

    if config['install_game']:
        install_game()

    while True:
        open_program(config['program_path'], config['time_to_wait'])
        time.sleep(3 * 60 * 60)


if __name__ == "__main__":
    main()
