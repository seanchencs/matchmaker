from main import record_result
from random import random
from discord.ext import commands
from discord_slash import cog_ext, SlashContext

GUILDS = [825900837083676732]

class Test(commands.Cog):
    def __init__(self, bot):
        """Generate test matches."""
        self.bot = bot
    
    @cog_ext.cog_slash(name='test', guild_ids=GUILDS, description='test')
    async def _test(self, ctx: SlashContext):
        members = ctx.guild.members
        for _ in range(100):
            players = random.sample(members, 2)
            attacker, defender = players[0], players[1]
            record_result([attacker], [defender], random.randint(0, 13), random.randint(0, 13), ctx.guild.id)

def setup(bot):
    bot.add_cog(Test(bot))