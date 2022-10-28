import random

import discord
from discord.ext import commands
from discord.commands import default_permissions
from match import Match
from .matchmaker import Matchmaker


class Test(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @discord.slash_command(name="test", description="Generate 10 test matches.")
    @default_permissions(manage_emojis=True)
    async def test(self, ctx, num_matches: discord.Option(int)):
        await ctx.defer()
        count = num_matches
        members = {member for member in ctx.guild.members}
        for _ in range(count):
            players = random.sample(members, min(10, len(members) - len(members) % 2))
            attacker_score = random.choice((13, random.randint(0, 11)))
            defender_score = random.randint(0, 11) if attacker_score == 13 else 13

            match = Match(guild_id=ctx.guild.id, players=players)
            match.record_result(attacker_score, defender_score)
            await ctx.send(
                embeds=[
                    Matchmaker.get_match_embed(match),
                    Matchmaker.get_post_match_embed(match),
                ]
            )
        await ctx.respond("✅", ephemeral=True)


def setup(bot):
    bot.add_cog(Test(bot))
