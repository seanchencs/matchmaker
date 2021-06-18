# Matchmaker, a Discord matchmaking bot

[![Codacy Badge](https://api.codacy.com/project/badge/Grade/93e0557bd829414b99824b19c2cbf844)](https://app.codacy.com/gh/seanchencs/matchmaker?utm_source=github.com&utm_medium=referral&utm_content=seanchencs/matchmaker&utm_campaign=Badge_Grade_Settings)

Matchmake in-house teams with MMR through Discord.

Integration with Discord Slash Commands.

Modified TrueSkill algorithm with support for margin of victory, decay, and ad-hoc N v M matchmaking.

## How to Use

### Make a Game
Option 1: use ``` /start```, then ```/make rated``` for MMR-based teams or ```/make unrated``` for random teams  
Option 2: use ``` /make custom ``` to choose your own teams  

### Choose a Map (Optional)
Optionally choose a random map with ```/map random```.  
Start a map veto process with ```/map veto```.

### Record a Result
Use ```/record [winning_team] [winning_score] [losing_score]``` to record a result.  

### Create/Move Players to Voice Channels
Use ```/move``` to move players to their designated team voice channels.  
Use ```/back``` to bring everyone back to the same voice channel.  

### Show Statistics
Use ```/leaderboard``` to show the leaderboard.  
Use ```/history``` to show recent match history and graph of player ratings.  
Use ```/history [@player]``` to show a specific player's match history and rating graph.  
Use ```/rating``` to view your own rating. Use ```/rating [@player]``` to view a specific player's rating.  

## What's New
* Record Round Scores (Margin-of-Victory) with a modified TrueSkill algorithm
* Match History with ```/history```
* Rating Graphs with ```/history```
* Rating Decay (σ increases when not playing matches)
* Ad-hoc Custom Matchmaking with ```/make custom```
* Support for different games by modifying config.py
* SQLite3 Backend

## Create your own bot
1. Create a bot at https://discord.com/developers/

2. Clone the repository.
    ```
    git clone https://github.com/seanchencs/matchmaker.git
    ```
3. Install Poetry (https://python-poetry.org/docs/) and run poetry install to install dependencies.
    ```
    poetry install
    ```
4. Add your discord bot token as an environment variable (named TOKEN) or add it to .env
    ```
    export TOKEN=[your token here]
    ```
5. Edit setup.py with your target game's values and Discord ids.
6. Start the bot with poetry run.
    ```
    poetry run python main.py
    ``` 