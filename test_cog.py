from main import record_result
import random
from discord.ext import commands
from discord_slash import cog_ext, SlashContext

GUILDS = [825900837083676732]

class Test(commands.Cog):
    def __init__(self, bot):
        """Generate test matches."""
        self.bot = bot
    
    @cog_ext.cog_slash(name='test', guild_ids=GUILDS, description='generate 10 random 1v1 results')
    async def _test(self, ctx: SlashContext):
        members = [member.id for member in ctx.guild.members]
        for _ in range(10):
            players = random.sample(members, 2)
            attacker, defender = players[0], players[1]
            attacker_score = random.choice((13, random.randint(0, 11)))
            defender_score = random.randint(0, 11) if attacker_score == 13 else 13
            record_result([attacker], [defender], attacker_score, defender_score, ctx.guild.id)
        await ctx.send("✅")

def setup(bot):
    bot.add_cog(Test(bot))