import logging
import os

import discord
import dotenv
import trueskill as ts

from config import show_test_commands

# load env
if os.path.isfile(".env"):
    dotenv.load_dotenv(".env")

# set up logging
logger = logging.getLogger("discord")
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")
file_handler.setFormatter(
    logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
)
stdout_handler = logging.StreamHandler()
stdout_handler.setFormatter(
    logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
)
stdout_handler.setLevel(logging.DEBUG)
logger.addHandler(stdout_handler)
logger.addHandler(file_handler)

# discord py client
intents = discord.Intents.default()
intents.members = True
bot = discord.Bot(intents=intents)

# TrueSkill Rating Settings
env = ts.TrueSkill(draw_probability=0.01)
env.make_as_global()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

# load cogs
bot.load_extension("cogs.matchmaker")
bot.load_extension("cogs.music")
# bot.load_extension("cogs.gpt_cog")
if show_test_commands:
    bot.load_extension("cogs.test")

bot.run(os.getenv("TOKEN"))
