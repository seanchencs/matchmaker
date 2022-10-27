from math import ceil
from typing import List
import discord
from discord.ext import commands, pages
from backend import get_history, get_match_summary, get_past_ratings, get_playerlist, get_ranks, get_rating, get_win_loss, record_result
from tabulate import tabulate
import trueskill as ts
from asciichartpy import plot
import random

from match import Match

guild_to_players = {}  # guild_id : set of players that have clicked Join
guild_to_match = {}  # guild_id : Match

time_format = '%a %b %d %I:%M %p'

class Matchmaker(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @discord.slash_command(name="test1", description="hello world")
    async def test(self, ctx):
        await ctx.send("Hi!")

    @discord.slash_command(name="start", description="Start a match.")
    async def start(self, ctx):
        def get_start_msg(guild_id):
            """Get updated start message with current list of players."""
            players = guild_to_players[guild_id]
            start_msg = (
                "Players"
                + f" ({len(players)}):"
                + "".join([f"\t<@!{member.id}>" for member in players])
            )
            return start_msg

        def get_match_embed(match: Match):
            team_a = [f"\t<@!{id}>" for id in match.team_a]
            team_b = [f"\t<@!{id}>" for id in match.team_b]

            embed = discord.Embed(title=match.get_title())
            embed.add_field(name="Team A", value="\n".join(team_a), inline=True)
            embed.add_field(name="Team B", value="\n".join(team_b), inline=True)

            return embed

        class JoinButton(discord.ui.View):
            @discord.ui.button(label="Join", style=discord.ButtonStyle.success)
            async def join_button_cb(self, button, interaction):
                guild_id = interaction.guild_id
                guild_to_players[guild_id].add(interaction.user)
                start_msg = get_start_msg(guild_id)
                await interaction.response.edit_message(
                    content=start_msg, view=JoinButton()
                )
                await interaction.followup.send(
                    content="", view=LeaveMakeButtons(interaction), ephemeral=True
                )

        class LeaveMakeButtons(discord.ui.View):
            def __init__(self, parent_interaction):
                super().__init__()
                self.parent_interaction = parent_interaction

            @discord.ui.button(label="Leave", style=discord.ButtonStyle.danger)
            async def leave_button_cb(self, button, interaction):
                guild_id = interaction.guild_id
                guild_to_players[guild_id].remove(interaction.user)
                start_msg = get_start_msg(guild_id)
                await self.parent_interaction.message.edit(
                    content=start_msg, view=JoinButton()
                )
                await interaction.response.edit_message(content="💔", view=None)

            @discord.ui.button(label="Start Game", style=discord.ButtonStyle.primary)
            async def make_button_cb(self, button, interaction):
                guild_id = interaction.guild_id
                players = guild_to_players[guild_id]
                if len(players) < 2:
                    await interaction.response.send_message(
                        "Requires 2+ players.", ephemeral=True, delete_after=3
                    )
                    return

                guild_to_match[guild_id] = Match(guild_to_players[guild_id], guild_id)

                await self.parent_interaction.message.edit(
                    content="",
                    embed=get_match_embed(guild_to_match[guild_id]),
                    view=MatchView(),
                )
                await interaction.response.edit_message(
                    content="✅", view=None, delete_after=3
                )

                guild_to_players[guild_id] = set()

        class MatchView(discord.ui.View):
            @discord.ui.button(label="Move🎤", style=discord.ButtonStyle.blurple)
            async def move_button_cb(self, button, interaction):
                if button.label == "Move🎤":
                    gd = interaction.guild
                    # find team voice channels
                    a_vc, b_vc = None, None
                    # check if category exists
                    game_category = None
                    for category in gd.categories:
                        if category.name == "beep boop":
                            game_category = category
                    if game_category is None:
                        # make it
                        game_category = await gd.create_category_channel("beep boop")
                    for vc in gd.voice_channels:
                        # ignore voice channels outside of category
                        if vc.category != game_category:
                            continue
                        if vc.name == "Team A":
                            a_vc = vc
                        elif vc.name == "Team B":
                            b_vc = vc
                    # create vc if necessary
                    if a_vc is None:
                        a_vc = await gd.create_voice_channel("Team A", category=game_category)
                    if b_vc is None:
                        b_vc = await gd.create_voice_channel("Team B", category=game_category)
                    # move members to right channel
                    team_a = guild_to_match[gd.id].team_a
                    team_b = guild_to_match[gd.id].team_b
                    count = 0
                    for a in team_a:
                        member = gd.get_member(int(a))
                        if member and member.voice is not None:
                            count += 1
                            await member.move_to(a_vc)
                    for b in team_b:
                        member = gd.get_member(int(b))
                        if member and member.voice is not None:
                            count += 1
                            await member.move_to(b_vc)
                    button.label = "Move Back 🎤"
                    await interaction.response.edit_message(view=self)

                    # await ctx.send(f"{count} player{'s' if count > 1 else ''} moved.", ephemeral=True, delete_after=3)

                    
                else:
                    # find voice channels
                    gd = interaction.guild
                    for vc in gd.voice_channels:
                        # ignore voice channels outside of game category
                        if vc.category is not None and vc.category.name != "beep boop":
                            continue
                        elif vc.name == "Team A":
                            for vc2 in gd.voice_channels:
                                if vc2.name == "Team B":
                                    for player in vc.members:
                                        await player.move_to(vc2)
                    button.label = "Move🎤"
                    await interaction.response.edit_message(view=self)

            @discord.ui.button(label="Record Result", style=discord.ButtonStyle.success)
            async def record_result_button_cb(self, button, interaction):
                match = guild_to_match[guild_id]
                await interaction.response.send_modal(
                    RecordModal(parent_interaction=interaction, title=match.get_title())
                )

            @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
            async def cancel_button_cb(self, button, interaction):
                guild_id = interaction.guild_id
                guild_to_match[guild_id] = None
                await interaction.response.edit_message(
                    content="Match cancelled.", view=None
                )

        class RecordModal(discord.ui.Modal):
            def __init__(self, parent_interaction, *args, **kwargs) -> None:
                super().__init__(*args, **kwargs)
                self.parent_interaction = parent_interaction
                self.add_item(
                    discord.ui.InputText(label="Team A Score", placeholder="0")
                )
                self.add_item(
                    discord.ui.InputText(label="Team B Score", placeholder="0")
                )

            async def callback(self, interaction: discord.Interaction):
                def get_post_match_embed(match: Match):
                    team_a_rating_delta = {
                        id: (match.team_a_new[id].mu - match.team_a_old[id].mu)
                        for id in match.team_a
                    }
                    team_b_rating_delta = {
                        id: (match.team_b_new[id].mu - match.team_b_old[id].mu)
                        for id in match.team_b
                    }

                    team_a = [
                        f"\t<@!{id}> ({team_a_rating_delta[id]:+.2f})"
                        for id in match.team_a
                    ]
                    team_b = [
                        f"\t<@!{id}> ({team_b_rating_delta[id]:+.2f})"
                        for id in match.team_b
                    ]

                    embed = discord.Embed(title=match.get_title())
                    embed.add_field(
                        name=f"Team A {'👑' if match.team_a_score > match.team_b_score else ''}",
                        value="\n".join(team_a),
                        inline=True,
                    )
                    embed.add_field(
                        name=f"Team B {'👑' if match.team_a_score < match.team_b_score else ''}",
                        value="\n".join(team_b),
                        inline=True,
                    )

                    return embed

                team_a_score = int(self.children[0].value)
                team_b_score = int(self.children[1].value)
                match = guild_to_match[guild_id]
                match.record_result(a_score=team_a_score, b_score=team_b_score)
                await self.parent_interaction.message.edit(
                    content="", embed=get_post_match_embed(match), view=None
                )

                await interaction.response.send_message(
                    content="✅", ephemeral=True, delete_after=3
                )

        # TODO: check if match is in progress?
        guild_id = ctx.guild_id
        guild_to_players[guild_id] = set()
        start_msg = get_start_msg(guild_id)

        await ctx.respond(start_msg, view=JoinButton())

    @discord.slash_command(name="leaderboard", description="Display the leaderboard.")
    async def leaderboard(self, ctx):
        ranks = get_ranks(get_playerlist(ctx.guild.id),
                          ctx.guild.id, metric='exposure')
        if not ranks:
            await ctx.send('No Ranked Players.')
            return
        leaderboard = sorted(ranks.keys(), key=lambda x: ranks[x])
        output = []
        headers = ['Rank', 'Name', 'Rating', 'Score', 'Win/Loss']
        for item in leaderboard:
            member = ctx.guild.get_member(int(item))
            if member:
                rank = ranks[item]
                name = member.name
                rating = get_rating(item, ctx.guild.id)
                exposure = ts.expose(rating)
                w, l = get_win_loss(item, ctx.guild.id)
                output.append([rank, name, f'{rating.mu: .4f} ± {rating.sigma: .2f}', round(
                    exposure, 4), f'{w}W {l}L'])
        await ctx.respond(f"`{tabulate(output, headers=headers, tablefmt='psql', floatfmt='.4f')}`")

    @discord.slash_command(name="history", description="Display match history")
    async def history(self, ctx):
        def get_pages(history):
            output = []
            for i in range(0, len(history), 10):
                chunk = history[i:i+10]
                content = '\n'.join([get_match_summary(match) for match in chunk])
                embed = discord.Embed()
                embed.add_field(name=f"Match History", value=content)
                output.append(pages.Page(title=f"History", embeds=[embed]))
            return output
        
        history = get_history(ctx.guild.id)
        if history:
            paginator = pages.Paginator(pages=get_pages(history))
            await paginator.respond(ctx.interaction)
        else:
            await ctx.respond("No Matches Found.")

    @discord.user_command(name="Rating and User History")
    async def user_rating_history(self, ctx, member: discord.Member):
        user_id = str(member.id)
        pfp = member.display_avatar
        rating = get_rating(user_id, ctx.guild.id)
        history = get_history(ctx.guild.id, user_id)
        win, loss = get_win_loss(user_id, ctx.guild.id)
        if history:
            rank = get_ranks(players=[user_id], guildid=ctx.guild.id)[user_id]
        else:
            rank = "N/A"
        past_ratings = get_past_ratings(user_id, ctx.guild.id)

        # plot rating history
        # scaling
        if len(past_ratings) < 30:
            past_ratings = [val for val in past_ratings for _ in range(
                0, ceil(30/len(past_ratings)))]
        elif len(past_ratings) > 60:
            past_ratings = past_ratings[::len(past_ratings)//30]
        rating_graph = plot(past_ratings)

        # match history
        if history:
            # match_history = '\n'.join([get_match_summary(match) for match in history[:10]])
            match_history = []
            for match in history[:10]:
                summary = get_match_summary(match)
                old = match['old_ratings'][user_id].mu
                if user_id in match['team_a']:
                    new = match['team_a'][user_id].mu
                    delta = new - old
                    match_history.append(f"{summary} ({delta:+.2f})")
                else:
                    new = match['team_b'][user_id].mu
                    delta = new - old
                    match_history.append(f"{summary} ({delta:+.2f})")
            match_history = '\n'.join(match_history)
        else:
            match_history = "No Matches Found."

        embed = discord.Embed(title=f"{member.name}")
        embed.set_thumbnail(url=pfp.url)
        embed.add_field(name="Rating", value=f"{rating.mu:.2f} ± {rating.sigma:.2f}", inline=True)
        embed.add_field(name="Score", value=f"{ts.expose(rating):.2f}", inline=True)
        embed.add_field(name="W/L", value=f"{win}W {loss}L", inline=True)
        embed.add_field(name="Rank", value=f"{rank}", inline=True)
        embed.add_field(name="History", value=match_history, inline=False)
        if history:
            embed.add_field(name="Graph", value=f"`{rating_graph}`", inline=False)
        await ctx.respond(embed=embed)

    @discord.slash_command(name="test", description="Generate 10 test matches.")
    async def test(self, ctx):
        count = 10
        members = {member for member in ctx.guild.members}
        print(len(members))
        for _ in range(count):
            players = random.sample(members, len(members)-len(members)%2)
            attacker_score = random.choice((13, random.randint(0, 11)))
            defender_score = random.randint(0, 11) if attacker_score == 13 else 13

            match = Match(guild_id = ctx.guild.id, players=players)
            match.record_result(attacker_score, defender_score)
            await ctx.send(match.get_summary())

def setup(bot):
    bot.add_cog(Matchmaker(bot))
