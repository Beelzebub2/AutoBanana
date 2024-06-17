![Static Badge](https://img.shields.io/badge/Version-v1.1-8ebff1?style=for-the-badge&logo=v)
![Static Badge](https://img.shields.io/badge/Language-python-3776ab?style=for-the-badge&logo=python)
![Static Badge](https://img.shields.io/badge/Made%20by-Beelzebub2-851ebc?style=for-the-badge)
# AutoBanana

AutoBanana is an automated script designed to manage the opening and closing of a specific game through Steam. The primary features of AutoBanana include:

### Features
- **Automatic Startup:** Configure the script to run on system startup, ensuring the game is managed without user intervention.
- **Timed Execution:** Opens the game using the Steam URL (`steam://rungameid/2923300`) and waits for a specified duration before closing it. This cycle repeats every three hours.
- **Steam Installation Trigger:** Triggers the installation of the game via Steam if it's not already installed.
- **Logging:** Logs all actions, including game opening, closing, and startup configurations, for easy monitoring and debugging.
- **Startup Management:** Easily add or remove AutoBanana from the Windows startup sequence.
- **Customizable Configurations:** Customize settings like program path, time to wait, and installation trigger through a `config.ini` file.

### Installation

- **Install python**  
- **Run setup.bat**

```diff

v1.1 17/06/24

+   Improved UI
+   Organized the code
+   Added time until next open
+   Added start on startup


```
