import os
import random

from discord.ext import commands
from discord_slash import SlashContext, cog_ext
from discord_slash.model import SlashCommandPermissionType
from discord_slash.utils.manage_commands import (create_option,
                                                 create_permission)

from main import delete_db, record_result

GUILDS = [825900837083676732]

class Test(commands.Cog):
    def __init__(self, bot):
        """Generate test matches."""
        self.bot = bot
    
    @cog_ext.cog_slash(name='test', guild_ids=GUILDS, description='generate random 1v1 results', options=[
        create_option(
            name='count',
            description='# of results to generate',
            option_type=4,
            required=False,
        )
    ], permissions={
        825900837083676735: create_permission(263745246821744640, SlashCommandPermissionType.USER, True)
    })
    async def _test(self, ctx: SlashContext, count=5):
        members = [member.id for member in ctx.guild.members]
        for _ in range(count):
            players = random.sample(members, 2)
            attacker, defender = players[0], players[1]
            attacker_score = random.choice((13, random.randint(0, 11)))
            defender_score = random.randint(0, 11) if attacker_score == 13 else 13
            record_result([attacker], [defender], attacker_score, defender_score, ctx.guild.id)
        await ctx.send("✅")

    @cog_ext.cog_slash(name='delete', guild_ids=GUILDS, description='delete the database for this server', permissions={
        825900837083676735: create_permission(263745246821744640, SlashCommandPermissionType.USER, True)
    })
    async def _delete(self, ctx:SlashContext):
        delete_db(ctx.guild_id)
        await ctx.send("✅")

def setup(bot):
    bot.add_cog(Test(bot))
