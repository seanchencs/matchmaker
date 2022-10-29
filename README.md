# Matchmaker, a Discord matchmaking bot

[![Codacy Badge](https://api.codacy.com/project/badge/Grade/93e0557bd829414b99824b19c2cbf844)](https://app.codacy.com/gh/seanchencs/matchmaker?utm_source=github.com&utm_medium=referral&utm_content=seanchencs/matchmaker&utm_campaign=Badge_Grade_Settings) ![Docker Build](https://github.com/seanchencs/matchmaker/actions/workflows/docker-image.yml/badge.svg)


Matchmake in-house teams with MMR through Discord.

Integration with Discord Slash Commands.

Modified TrueSkill algorithm with support for margin of victory, decay, and ad-hoc N v M matchmaking.

## How to Use

### Make a Game
Use ``` /start```.  

### Show Statistics
Use ```/leaderboard``` to show the leaderboard.  
Use ```/history``` to show recent match history and graph of player ratings.  
Right click a user and choose ```Rating and History``` under Apps to display a player's stats.

## What's New
* Slash Commands, Embeds, Buttons, and Views.
* Record Round Scores (Margin-of-Victory) with a modified TrueSkill algorithm
* Match History with ```/history```
* Rating Graphs with ```Rating and History```
* Rating Decay (σ increases when not playing matches)
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
5. Start the bot with poetry run.
    ```
    poetry run python main.py
    ``` 