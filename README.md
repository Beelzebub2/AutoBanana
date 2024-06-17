# AutoBanana

AutoBanana is an automated script designed to manage the opening and closing of a specific game through Steam. The primary features of AutoBanana include:

### Features
- **Automatic Startup:** Configure the script to run on system startup, ensuring the game is managed without user intervention.
- **Timed Execution:** Opens the game using the Steam URL (`steam://rungameid/2923300`) and waits for a specified duration before closing it. This cycle repeats every three hours.
- **Steam Installation Trigger:** Triggers the installation of the game via Steam if it's not already installed.
- **Logging:** Logs all actions, including game opening, closing, and startup configurations, for easy monitoring and debugging.
- **Startup Management:** Easily add or remove AutoBanana from the Windows startup sequence.
- **Customizable Configurations:** Customize settings like program path, time to wait, and installation trigger through a `config.ini` file.

AutoBanana simplifies the repetitive task of managing game sessions, making it ideal for users who want to automate their gaming routines.
