import configparser
import itertools
import logging
import math
import os
import shutil
import sys
import threading
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

# Enable ANSI escape codes on Windows
if os.name == 'nt':
    os.system('')  # Enable VT100 escape sequences


class AutoBanana:

    def __init__(self):
        self.base_url = "https://raw.githubusercontent.com/Beelzebub2/AutoBanana/main/"
        self.logo_file = "logo.txt"
        self.startup_logo_file = "startup.txt"
        self.download_file_if_not_exists(self.logo_file, ".")
        self.download_file_if_not_exists(self.startup_logo_file, ".")
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
        
        # Dynamic console sizing
        self.min_width = max(self.string_width(self.logo), self.string_width(self.startup_logo)) + 10
        self.console_width, self.console_height = self.get_terminal_size()
        
        self.config = self.read_config()
        self.start_time = datetime.now()
        self.game_open_count = 0
        self.account_names = []
        self.steam_install_location = self.get_steam_install_location()
        self.theme_function = None
        self.colorama_color = Fore.LIGHTWHITE_EX
        
        # Animation state
        self.animation_running = False
        self.animation_thread = None
        self.spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.progress_chars = ["░", "▒", "▓", "█"]
        
        # Update config to remove games not installed
        self.update_config_file()
        self.config = self.read_config()
        self.themes = utils.theme_manager
        self.steam_account_changer = utils.steam_manager.SteamAccountChanger()
        self.apply_theme()
        
        # Start animation frame updater
        self.start_animation_thread()

    def log_event(self, message, level="info"):
        color_map = {
            "info": self.colorama_color,
            "success": Fore.GREEN,
            "warning": Fore.YELLOW,
            "error": Fore.RED,
        }
        prefix_map = {
            "info": "[INFO]",
            "success": "[ OK ]",
            "warning": "[WARN]",
            "error": "[ERR]",
        }

        color = color_map.get(level, self.colorama_color)
        prefix = prefix_map.get(level, "[INFO]")
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # Animate the prefix with a brief color pulse
        print(f"{self.colorama_color}{timestamp} {color}{prefix}{Fore.RESET} {message}")

    def get_terminal_size(self):
        """Get current terminal size dynamically."""
        try:
            size = shutil.get_terminal_size()
            return max(size.columns, self.min_width), max(size.lines, 20)
        except:
            return 120, 32

    def start_animation_thread(self):
        """Start background thread for animation frame updates."""
        self.animation_running = True
        self.animation_thread = threading.Thread(target=self._animation_loop, daemon=True)
        self.animation_thread.start()

    def _animation_loop(self):
        """Background loop to update animation frames."""
        while self.animation_running:
            self.themes.advance_animation_frame()
            time.sleep(0.05)  # 20 FPS for smooth animations

    def stop_animation_thread(self):
        """Stop the animation thread."""
        self.animation_running = False
        if self.animation_thread:
            self.animation_thread.join(timeout=1)

    def get_spinner(self, frame=None):
        """Get current spinner character."""
        if frame is None:
            frame = self.themes.get_animation_frame()
        return self.spinner_chars[frame % len(self.spinner_chars)]

    def get_theme_colors(self, animated=True):
        """
        Get RGB colors based on current theme.
        Returns tuple of (r, g, b) values.
        """
        theme = self.config['theme'].lower()
        frame = self.themes.get_animation_frame() if animated else 0
        pulse = int(40 * math.sin(frame * 0.15))
        
        if theme == 'fire':
            return (255, 180 + pulse, 0)
        elif theme == 'ice':
            return (100 + pulse, 180 + pulse, 255)
        elif theme == 'pinkneon':
            return (255, 50 + pulse, 200 + pulse)
        elif theme == 'rainbow':
            return self.themes.hsv_to_rgb((frame * 2 % 360) / 360, 1.0, 1.0)
        elif theme == 'matrix':
            return (0, 200 + pulse, 0)
        elif theme == 'sunset':
            return (255, 150 + pulse, 50 + abs(pulse))
        else:  # default
            return (200 + pulse, 200 + pulse, 200 + pulse)

    def get_theme_color_code(self, animated=True):
        """
        Get ANSI color escape code based on current theme.
        """
        r, g, b = self.get_theme_colors(animated)
        return f"\033[38;2;{r};{g};{b}m"

    def create_progress_bar(self, progress, width=None):
        """Create an animated progress bar that adapts to terminal width."""
        if width is None:
            term_width, _ = self.get_terminal_size()
            width = min(40, term_width - 50)  # Leave room for other info
        
        filled = int(width * progress)
        empty = width - filled
        
        # Get theme-appropriate colors
        frame = self.themes.get_animation_frame()
        theme = self.config['theme'].lower()
        
        if theme == 'fire':
            start_color = (255, 200, 0)
            end_color = (255, 50, 0)
        elif theme == 'ice':
            start_color = (100, 200, 255)
            end_color = (0, 100, 255)
        elif theme == 'pinkneon':
            start_color = (255, 100, 200)
            end_color = (200, 0, 255)
        elif theme == 'rainbow':
            # Rainbow gradient based on animation frame
            h1 = (frame * 2) % 360
            h2 = (frame * 2 + 60) % 360
            start_color = self.themes.hsv_to_rgb(h1 / 360, 1.0, 1.0)
            end_color = self.themes.hsv_to_rgb(h2 / 360, 1.0, 1.0)
        elif theme == 'matrix':
            start_color = (0, 255, 0)
            end_color = (0, 150, 0)
        elif theme == 'sunset':
            start_color = (255, 180, 50)
            end_color = (255, 50, 150)
        else:
            start_color = (100, 255, 100)
            end_color = (0, 150, 255)
        
        bar = ""
        for i in range(filled):
            ratio = i / max(1, width)
            # Add subtle animation pulse
            pulse = int(30 * math.sin(frame * 0.1 + i * 0.3))
            r = max(0, min(255, int(start_color[0] + (end_color[0] - start_color[0]) * ratio) + pulse))
            g = max(0, min(255, int(start_color[1] + (end_color[1] - start_color[1]) * ratio) + pulse))
            b = max(0, min(255, int(start_color[2] + (end_color[2] - start_color[2]) * ratio) + pulse))
            bar += f"\033[38;2;{r};{g};{b}m█\033[0m"
        
        bar += f"\033[38;2;60;60;60m{'░' * empty}\033[0m"
        return bar

    def animated_text(self, text, color=None):
        """Apply subtle animation to text based on current frame."""
        if color is None:
            color = self.colorama_color
        frame = self.themes.get_animation_frame()
        
        # Subtle brightness pulse
        pulse = int(20 * math.sin(frame * 0.1))
        return f"{color}{text}{Fore.RESET}"

    def render_banner(self, text, animate=True):
        self.clear_console()
        self.console_width, self.console_height = self.get_terminal_size()
        if animate:
            print(self.theme_function(text, animate=True))
        else:
            print(self.theme_function(text, animate=False))

    def render_animated_banner(self, text, duration=3.0):
        """
        Render banner with continuous animation for a specified duration.
        Shows the theme animation effect in real-time.
        
        Parameters
        ----------
        text : str
            The banner text to display
        duration : float
            How long to animate in seconds
        """
        start_time = time.time()
        lines_count = len(text.splitlines()) + 2
        
        while time.time() - start_time < duration:
            # Move cursor to top
            sys.stdout.write(f'\033[{lines_count}A')
            sys.stdout.write('\033[J')  # Clear from cursor to end
            
            # Print animated banner
            print(self.theme_function(text, animate=True))
            
            time.sleep(0.1)  # ~10 FPS for smooth animation
        
        # Final render
        sys.stdout.write(f'\033[{lines_count}A')
        sys.stdout.write('\033[J')
        print(self.theme_function(text, animate=True))

    def animated_wait(self, seconds, message="Waiting", show_progress=True):
        """
        Animated waiting with progress bar and spinner.
        
        Parameters
        ----------
        seconds : int
            Number of seconds to wait
        message : str
            Message to display during wait
        show_progress : bool
            Whether to show progress bar
        """
        total = seconds
        start_time = time.time()
        
        while seconds > 0:
            elapsed = time.time() - start_time
            progress = elapsed / total if total > 0 else 0
            remaining = max(0, seconds)
            
            # Get terminal width for adaptive display
            term_width, _ = self.get_terminal_size()
            
            # Animated spinner
            spinner = self.get_spinner()
            
            # Time display with theme color
            mins, secs = divmod(int(remaining), 60)
            time_color = self.get_theme_color_code(animated=True)
            time_str = f"{time_color}{mins:02d}:{secs:02d}\033[0m"
            
            # Create progress bar
            if show_progress:
                bar_width = min(30, max(15, term_width - len(message) - 25))
                progress_bar = self.create_progress_bar(progress, bar_width)
                
                # Compose the line with theme color for text
                color_code = self.get_theme_color_code(animated=True)
                line = f" {color_code}{spinner}\033[0m {color_code}{message}\033[0m {progress_bar} {time_str} "
            else:
                # Animated dots
                dots = "." * (int(elapsed * 2) % 4)
                color_code = self.get_theme_color_code(animated=True)
                line = f" {color_code}{spinner} {message}{dots.ljust(3)}\033[0m {time_str} "
            
            # Write to console
            sys.stdout.write('\r' + line.ljust(term_width - 1))
            sys.stdout.flush()
            
            # Small sleep for smooth animation (10 updates per second)
            time.sleep(0.1)
            seconds = total - (time.time() - start_time)
        
        # Clear the line when done
        term_width, _ = self.get_terminal_size()
        sys.stdout.write('\r' + ' ' * (term_width - 1) + '\r')
        sys.stdout.flush()

    def animated_account_switch(self, account_name, duration=10):
        """
        Show animated display while switching Steam accounts.
        
        Parameters
        ----------
        account_name : str
            Name of the account being switched to
        duration : int
            How long to show the animation
        """
        message = f"Switching to {account_name}"
        self.animated_wait(duration, message, show_progress=True)
        self.log_event(f"Switched to account: {account_name}", "success")

    def print_config_overview(self):
        lines = [
            f"Run on startup: {'Yes' if self.config['run_on_startup'] else 'No'}",
            f"Games configured: {len(self.config['games'])}",
            f"Batch size: {self.config['batch_size']}",
            f"Wait between batches: {self.config['time_to_wait']}s",
            f"Theme: {self.config['theme']}",
            f"Switch accounts: {'Enabled' if self.config['switch_steam_accounts'] else 'Disabled'}",
        ]
        self.log_event("Configuration loaded:")
        for line in lines:
            print(f"{self.colorama_color}  - {line}")

    def print_account_overview(self, accounts):
        if not accounts:
            self.log_event("No Steam accounts detected with 'Remember password'.", "warning")
            return
        self.log_event(f"Detected {len(accounts)} Steam account(s):")
        for acc in accounts:
            print(f"{self.colorama_color}  - {acc}")

    def compose_status_line(self, seconds, uptime, account_count, total_seconds=None):
        """Compose an animated status line with progress bar."""
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds_remaining = divmod(remainder, 60)
        
        # Get current terminal width
        term_width, _ = self.get_terminal_size()
        
        # Animated spinner
        spinner = self.get_spinner()
        
        # Calculate progress for the bar
        if total_seconds:
            progress = 1 - (seconds / total_seconds)
        else:
            progress = 0
        
        # Create progress bar with adaptive width
        bar_width = min(25, max(10, term_width - 90))
        progress_bar = self.create_progress_bar(progress, bar_width)
        
        # Time display with theme-based pulsing effect
        time_color = self.get_theme_color_code(animated=True)
        
        time_left = f"{time_color}{hours:02}:{minutes:02}:{seconds_remaining:02}\033[0m"
        
        # Compact or full view based on terminal width
        if term_width < 100:
            # Compact view
            status = f" {spinner} {progress_bar} {time_left}"
        else:
            # Full view
            stats = (
                f"Games:{Fore.RED}{len(self.config['games'])}{Fore.RESET} "
                f"Acc:{Fore.RED}{account_count}{Fore.RESET} "
                f"Runs:{Fore.RED}{self.game_open_count}{Fore.RESET}"
            )
            status = f" {spinner} {progress_bar} {time_left} | {stats} | Uptime:{Fore.RED}{str(uptime).split('.')[0]}{Fore.RESET}"
        
        return status

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
        os.system(f"mode con: cols={width} lines={height}")

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
        os.system("title AutoBanana v2.3 - Animated Edition")
        auto_banana = AutoBanana()
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
