import logging
import os

import discord
import dotenv
import trueskill as ts
from discord.ext import commands
from discord_slash import SlashCommand

# load env
if os.path.isfile('.env'):
    dotenv.load_dotenv('.env')

# set up logging
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# discord py client
bot = commands.Bot(command_prefix='.', intents=discord.Intents.all())
slash = SlashCommand(bot, sync_commands=True, sync_on_cog_reload=True)

# TrueSkill Rating Settings
env = ts.TrueSkill(draw_probability=0.01)
env.make_as_global()

@bot.event
async def on_ready():
    print('Logged in as {0.user}'.format(bot))

bot.load_extension('test_cog')
bot.load_extension('valorant_cog')
bot.run(os.getenv('TOKEN'))
