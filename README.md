![Static Badge](https://img.shields.io/badge/Version-v2.2-8ebff1?style=for-the-badge&logo=v)
![Static Badge](https://img.shields.io/badge/Language-python-3776ab?style=for-the-badge&logo=python)
![User Count](https://img.shields.io/badge/Total%20Users-355-green?style=for-the-badge)
[![GitHub issues](https://img.shields.io/github/issues/Beelzebub2/AutoBanana.svg?style=for-the-badge)](https://github.com/Beelzebub2/AutoBanana/issues)
[![GitHub forks](https://img.shields.io/github/forks/Beelzebub2/AutoBanana.svg?style=for-the-badge)](https://github.com/Beelzebub2/AutoBanana/network/members)
[![GitHub stars](https://img.shields.io/github/stars/Beelzebub2/AutoBanana.svg?style=for-the-badge)](https://github.com/Beelzebub2/AutoBanana/stargazers)
[![GitHub contributors](https://img.shields.io/github/contributors/Beelzebub2/AutoBanana.svg?style=for-the-badge)](https://github.com/Beelzebub2/AutoBanana/graphs/contributors)
![GitHub Actions Build Status](https://img.shields.io/github/actions/workflow/status/Beelzebub2/AutoBanana/build.yml?style=for-the-badge&label=Build)



# AutoBanana
### Now supports multiple games!

AutoBanana is an automated script designed to manage the opening and closing of games through Steam. The primary features of AutoBanana include:

### Features
- **Automatic Startup:** Configure the script to run on system startup, ensuring the game is managed without user intervention.
- **Timed Execution:** Opens the game using the Steam URL (`steam://rungameid/2923300`) and waits for a specified duration before closing it. This cycle repeats every three hours.
- **Logging:** Logs all actions, including game opening, closing, and startup configurations, for easy monitoring and debugging. This file can be found in `%appdata%/AutoBanana/AutoBanana.log`.
- **Startup Management:** Easily add or remove AutoBanana from the Windows startup sequence.
- **Customizable Configurations:** Customize settings like program path, time to wait, and installation trigger through a `config.ini` file.

### Installation

You can find the latest releases [here](https://github.com/Beelzebub2/AutoBanana/releases).

Simply download and run `AutoBanana-win64.exe`
#### I am aware of the false positive on the windows defender and working on a solution

### Manual Installation

- **Download the repository:** [here](https://github.com/Beelzebub2/AutoBanana/archive/refs/heads/main.zip)
- **Extract the contents of the zip file**
- **Install python**  Make sure to add python to PATH it's an option when installing!
- **Run setup.bat**
- **Insert game ID's into the config file separated by a comma ','** (you can find the ids on the game properties under the updates page on library or steam shop link)

### Development

- **Clone the repository:** `git clone https://github.com/Beelzebub2/AutoBanana/`
- **Navigate to the project directory:** `cd AutoBanana`
- **Install dependencies:**
```
pip install -r requirements.txt
pip install -r requirements-dev.txt
```
- **Run the script:** `python AutoBanana.py`

### Manually Building

- **Navigate to the project directory:** `cd AutoBanana`
- **Build with pyinstaller:** `pyinstaller -F -n AutoBanana-win64 -i banana.ico AutoBanana.py`

### Releasing

- Push a tag with the version number starting with `v` and GitHub Actions will automatically build the release and upload it to the releases page.

### Release Notes

```diff
Pending Features:
!   Add option to trigger game install thourgh steam://install/gameid with a Xseconds delay
!   Fix executable false positive on antivirus
!   Add UI using customtkinter to mess with config file

v2.2 28/07/24

+   Added flake file for developers. Use "pip install flake8" then in project file "flake8 AutoBanana.py"
!   Started working on the Autoupdater
+   Added more themes (configurable in config)
+   Changes console title
+   Overall optimizations thanks to @SavageCore

v2.1 10/07/24

+   Fixed Logo not showing correctly, thanks to @SavageCore

v2.0 09/07/24

+   Fixed check steam games location a bit more optimized
+   Fixed logo.txt missing
+   Fixed error with moving files across drives (by removing the necessity to do that)

v1.9 04/07/24

+   Added function to download missing files
+   Automatically removes games that are not installed from config.ini
+   Now detects Keyboard interrupt

v1.8 03/07/24

!   Started looking for ways to fix false positive on executable
+   Removed a duplicate function
+   Added documentation to functions (generated with Mintlify Doc Writer)

v1.7 02/07/24

+  Now Downloads the config.ini if it's missing
+  Executable version available
+  Now adds icon to executable

v1.6 27/06/24 Thank you guys :)

+  Actually opens all games, thanks to @SavageCore
+  Improved get_steam_games, thanks to @SavageCore
+  Fixed startup error, thanks to @SavageCore
+  More games like banana in the config thanks to @Gesugao-san

v1.5 24/06/24

+   Actually closes the other games now

v1.4 20/06/24

+   Added total games count to UI
+   Added multiple games support
-   Removed install verification

v1.3 19/06/24

+   Now checks if game was installed correctly
+   Code rework

v1.2 17/06/24

+   Added statistics tracker
+   Fixed bug with UI

v1.1 17/06/24

+   Improved UI
+   Organized the code
+   Added time until next open
+   Added start on startup


```
