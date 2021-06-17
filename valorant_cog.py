import random
import time
from math import ceil, isclose

import trueskill as ts
from asciichartpy import plot
from discord.ext import commands
from discord_slash import SlashContext, cog_ext
from discord_slash.model import SlashCommandPermissionType
from discord_slash.utils.manage_commands import (create_choice, create_option,
                                                 create_permission)
from pytz import timezone
from tabulate import tabulate

from backend import (get_history, get_leaderboard, get_leaderboard_by_exposure,
                     get_past_ratings, get_playerlist, get_ranks, get_rating,
                     get_win_loss, make_teams, record_result, undo_last_match)

# local time zone
central = timezone('US/Central')
time_format = '%a %b %-d %-I:%M %p'

# global discord id lists
GUILDS = [825900837083676732, 813149413782061057]
ADMINS = [335828416412778496, 263745246821744640]

# VALORANT MAPS
VALORANT_MAP_POOL = ['Bind', 'Haven', 'Split', 'Ascent', 'Icebox', 'Breeze']
VALORANT_SLASH_CHOICES = [create_choice(name=map_name, value=map_name) for map_name in VALORANT_MAP_POOL]


# dicts for guild-local variables
guild_to_start_msg = {} # message id of start message
guild_to_custom_msg = {} # custom matchmaking message
guild_to_teams = {} # {'attackers': [list of uids], 'defenders': [list of uids]}
guild_to_last_result_time = {} # time of last recorded result (for record cooldown)
guild_to_remaining_maps = {} # list of remaining maps in veto process
guild_to_next_team_to_veto = {} # 'attackers' or 'defenders' next to veto

class Valorant(commands.Cog):
    def __init__(self, bot):
        """VALORANT commands for matchmaking Discord bot."""
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        # update start message with reactors
        if payload.guild_id in guild_to_start_msg and payload.message_id == guild_to_start_msg[payload.guild_id].id:
            await self.update_start_message(payload)
        # update custom message
        elif payload.guild_id in guild_to_custom_msg and payload.message_id == guild_to_custom_msg[payload.guild_id].id:
            await self.update_custom_message(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        # update start message with reactors
        if payload.guild_id in guild_to_start_msg and payload.message_id == guild_to_start_msg[payload.guild_id].id:
            await self.update_start_message(payload)
        # update custom message
        elif payload.guild_id in guild_to_custom_msg and payload.message_id == guild_to_custom_msg[payload.guild_id].id:
            await self.update_custom_message(payload)

    async def update_start_message(self, payload):
        """Update the start message with list of reactors."""
        channel = self.bot.get_channel(payload.channel_id)
        start_msg = await channel.fetch_message(guild_to_start_msg[payload.guild_id].id)
        players = set()
        for reaction in start_msg.reactions:
            users = await reaction.users().flatten()
            players.update((user.id for user in users))
        output_message = "React to this message if you're playing" + f' ({len(players)})' + ''.join([f'\t<@!{member}>' for member in players] )
        await start_msg.edit(content=output_message)

    async def update_custom_message(self, payload):
        """Update the custom message with teams."""
        channel = self.bot.get_channel(payload.channel_id)
        start_msg = await channel.fetch_message(guild_to_custom_msg[payload.guild_id].id)
        attackers = defenders = []
        # read reactions
        for reaction in start_msg.reactions:
            if reaction.emoji == '🟥':
                attackers = await reaction.users().flatten()
                attackers = [str(user.id) for user in attackers if user.id != self.bot.user.id]
            elif reaction.emoji == '🟦':
                defenders = await reaction.users().flatten()
                defenders = [str(user.id) for user in defenders if user.id != self.bot.user.id and str(user.id) not in attackers]
        output = ['React with 🟥 to join Attackers or 🟦 to join Defenders\n']
        # evaluate teams
        if attackers and defenders:
            attacker_ratings = {str(uid) : get_rating(uid, payload.guild_id) for uid in attackers}
            defender_ratings = {str(uid) : get_rating(uid, payload.guild_id) for uid in defenders}
            quality = ts.quality([attacker_ratings, defender_ratings])
            output.append(f'\n**Predicted Quality: {quality*100: .2f}%**\n\n')
            output.append('**Attackers**: ' + ' '.join([f'<@!{member}>' for member in attackers]) + '\n')
            output.append('**Defenders**: ' + ' '.join([f'<@!{member}>' for member in defenders]))
            guild_to_teams[payload.guild_id] = {'attackers': attackers, 'defenders': defenders}
        await guild_to_custom_msg[payload.guild_id].edit(content=''.join(output))

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Clean up created voice channels if they're empty."""
        if before.channel == None or before.channel.category == None or before.channel.category.name.lower() != 'valorant':
            return
        prev_guild = before.channel.guild
        t_vc = ct_vc = None
        # find channels
        for vc in prev_guild.voice_channels:
            if vc.category == None or vc.category.name.lower() != 'valorant':
                continue
            if vc.name.lower() == 'attackers':
                t_vc = vc
            elif vc.name.lower() == 'defenders':
                ct_vc = vc
        # delete VALORANT channels if they're empty
        if t_vc is not None and ct_vc is not None:
            if len(t_vc.members) == len(ct_vc.members) == 0:
                await t_vc.delete()
                await ct_vc.delete()
                for category in prev_guild.categories:
                    if category.name.lower() == 'valorant':
                        await category.delete()

    @cog_ext.cog_slash(name='start', guild_ids=GUILDS, description='start matchmaking process, bot sends message for players to react to')
    async def _start(self, ctx: SlashContext):
        start_msg = await ctx.send("React to this message if you're playing :)")
        guild_to_start_msg[ctx.guild.id] = start_msg

    @cog_ext.cog_slash(name='make', guild_ids=GUILDS, options=[
        create_option(
            name='type',
            description='type of matchmaking',
            option_type=3,
            required=True,
            choices=[
                create_choice(
                    name='unrated',
                    value='unrated'
                ),
                create_choice(
                    name='rated',
                    value='rated'
                ),
                create_choice(
                    name='custom',
                    value='custom'
                )
            ]

        )
    ])
    async def _make(self, ctx: SlashContext, match_type: str, description='matchmake game from reacts to /start with option for MMR'):
        if match_type == 'custom':
            await self.custom(ctx)
        elif ctx.guild.id not in guild_to_start_msg or guild_to_start_msg[ctx.guild.id] is None:
            await ctx.send('use */start* before */make*')
            return
        if ctx.guild.id in guild_to_last_result_time:
            del guild_to_last_result_time[ctx.guild_id]
        if match_type == 'unrated':
            await self.unrated(ctx)
        elif match_type == 'rated':
            await self.rated(ctx)

    async def unrated(self, ctx: SlashContext):
        # read reacts and make teams randomly without ranks
        start_time = time.time()
        # read reacts
        guild_to_teams[ctx.guild.id] = {'attackers':[], 'defenders':[]}
        start_msg = await ctx.channel.fetch_message(guild_to_start_msg[ctx.guild.id].id)
        players = set()
        for reaction in start_msg.reactions:
            users = await reaction.users().flatten()
            players.update((user.id for user in users))
        # create teams
        players = list(players)
        random.shuffle(players)
        team_size = len(players) // 2
        attackers = players[:team_size]
        defenders = players[team_size:]
        # create output
        output = []
        output += "\nAttackers:\n"
        for member in attackers:
            output += f'\t<@!{member}>'
        output += "\n\nDefenders:\n"
        for member in defenders:
            output += f'\t<@!{member}>'
        # store teams
        guild_to_teams[ctx.guild.id]['attackers'] = attackers
        guild_to_teams[ctx.guild.id]['defenders'] = defenders
        # send output
        print(f'[{ctx.guild.id}]: Unrated Game created in {round(time.time()-start_time, 4)}s')
        await ctx.send(''.join(output))

    async def rated(self, ctx: SlashContext):
        start_time = time.time()
        # read reacts
        guild_to_teams[ctx.guild.id] = {'attackers':[], 'defenders':[]}
        start_msg = await ctx.channel.fetch_message(guild_to_start_msg[ctx.guild.id].id)
        players = set()
        for reaction in start_msg.reactions:
            users = await reaction.users().flatten()
            players.update((user.id for user in users))
        # must have at least one member on each team
        if len(players) < 2:
            await ctx.send('must have **at least 2 players** for rated game')
            return
        # create teams
        attackers, defenders, quality = make_teams(list(players), ctx.guild.id)
        # create output
        output_string = f'Predicted Quality: {quality*100: .2f}%\n'
        output_string += "\nAttackers:\n"
        for member in attackers:
            output_string += f'\t<@!{member}>({get_rating(member, ctx.guild.id).mu: .2f}) '
        output_string += "\n\nDefenders:\n"
        for member in defenders:
            output_string += f'\t<@!{member}>({get_rating(member, ctx.guild.id).mu: .2f}) '
        # store teams
        guild_to_teams[ctx.guild.id]['attackers'] = attackers
        guild_to_teams[ctx.guild.id]['defenders'] = defenders
        # send output
        print(f'[{ctx.guild.id}]: Rated Game created in {round(time.time()-start_time, 4)}s')
        await ctx.send(output_string)

    async def custom(self, ctx: SlashContext):
        start_time = time.time()
        # send custom matchmaking message
        guild_to_custom_msg[ctx.guild.id] = await ctx.send('React with 🟥 to join Attackers or 🟦 to join Defenders')
        await guild_to_custom_msg[ctx.guild.id].add_reaction('🟥')
        await guild_to_custom_msg[ctx.guild.id].add_reaction('🟦')

    @cog_ext.cog_slash(name='record', guild_ids=GUILDS, description='record match result and update player ratings', options=[
        create_option(
            name='winner',
            description='which side won the game',
            option_type=3,
            required=True,
            choices=[
                create_choice(
                    name='attackers',
                    value='attackers'
                ),
                create_choice(
                    name='defenders',
                    value='defenders'
                )
            ]

        ),
        create_option(
            name='winner_score',
            description='# of rounds won by winning team',
            option_type=4,
            required=True,
        ),
        create_option(
            name='loser_score',
            description='# of rounds won by losing team',
            option_type=4,
            required=True,
        ),
    ])
    async def _record(self, ctx: SlashContext, winner:str, winning_score:int, losing_score:int, description='matchmake game from reacts to /start with option for MMR'):
        if ctx.guild.id in guild_to_last_result_time and time.time() - guild_to_last_result_time[ctx.guild.id] < 60:
            await ctx.send(f'Result already recorded. Wait {round(60 - (time.time() - guild_to_last_result_time[ctx.guild.id]))}s before recording another result.')
            return
        if ctx.guild.id not in guild_to_teams or not guild_to_teams[ctx.guild.id]['attackers']:
            await ctx.send('use */make* before */record*')
            return
        if winning_score < losing_score:
            await ctx.send('ERROR: Winning team cannot have won less rounds than losing team.')
            return
        if winner == 'attackers':
            await self._attackers(winning_score, losing_score, ctx)
        elif winner == 'defenders':
            await self._defenders(winning_score, losing_score, ctx)
        guild_to_last_result_time[ctx.guild.id] = time.time()

    async def _attackers(self, winning_score, losing_score, ctx: SlashContext):
        if not guild_to_teams[ctx.guild.id]['attackers']:
            await ctx.send('use *$make* or *$rated* before recording a result')
        else:
            attacker, defender = guild_to_teams[ctx.guild.id]['attackers'], guild_to_teams[ctx.guild.id]['defenders']
            ranks_old = get_ranks(attacker+defender, ctx.guild.id)
            attackers_old, defenders_old, attackers_new, defenders_new = record_result(attacker, defender, winning_score, losing_score, ctx.guild.id)
            ranks_new = get_ranks(attacker+defender, ctx.guild.id)

            output = []
            output.append('**Win for Attackers Recorded.**\n\n')
            # charts
            headers = ['Attacker', 'ΔRating', 'ΔExposure', 'ΔRank']
            attacker_chart = []
            for attacker in attackers_new:
                member = ctx.guild.get_member(int(attacker))
                name = member.name
                delta_rating = f'{attackers_old[attacker].mu: .2f}->{attackers_new[attacker].mu: .2f}'
                delta_exposure = f'{ts.expose(attackers_old[attacker]): .2f}->{ts.expose(attackers_new[attacker]): .2f}'
                if ranks_old and attacker in ranks_old:
                    delta_rank = f'{ranks_old[attacker]}->{ranks_new[attacker]}'
                else:
                    delta_rank = f'{ranks_new[attacker]} (NEW!)'
                attacker_chart.append([name, delta_rating, delta_exposure, delta_rank])
            output.append(f"`Attackers - {winning_score}:\n{tabulate(attacker_chart, headers=headers, tablefmt='psql')}`\n\n")

            headers = ['Defender', 'ΔRating', 'ΔExposure', 'ΔRank']
            defender_chart = []
            for defender in defenders_new:
                member = ctx.guild.get_member(int(defender))
                name = member.name
                delta_rating = f'{defenders_old[defender].mu: .2f}->{defenders_new[defender].mu: .2f}'
                delta_exposure = f'{ts.expose(defenders_old[defender]): .2f}->{ts.expose(defenders_new[defender]): .2f}'
                if ranks_old and defender in ranks_old:
                    delta_rank = f'{ranks_old[defender]}->{ranks_new[defender]}'
                else:
                    delta_rank = f'{ranks_new[defender]} (NEW!)'
                defender_chart.append([name, delta_rating, delta_exposure, delta_rank])
            output.append(f"`Defenders - {losing_score}:\n{tabulate(defender_chart, headers=headers, tablefmt='psql')}`\n")
            # send output
            await ctx.send(''.join(output))

    async def _defenders(self, winning_score, losing_score, ctx: SlashContext):
        if not guild_to_teams[ctx.guild.id]['defenders']:
            await ctx.send('use *$make* or *$rated* before recording a result')
        else:
            attacker, defender = guild_to_teams[ctx.guild.id]['attackers'], guild_to_teams[ctx.guild.id]['defenders']
            ranks_old = get_ranks(attacker+defender, ctx.guild.id)
            attackers_old, defenders_old, attackers_new, defenders_new = record_result(attacker, defender, losing_score, winning_score, ctx.guild.id)
            ranks_new = get_ranks(attacker+defender, ctx.guild.id)

            output = []
            output.append('**Win for Defenders Recorded.**\n\n')
            # charts
            headers = ['Attacker', 'Δ Rating', 'Δ Exposure', 'Δ Rank']
            attacker_chart = []
            for attacker in attackers_new:
                member = ctx.guild.get_member(int(attacker))
                name = member.name
                delta_rating = f'{attackers_old[attacker].mu: .2f}->{attackers_new[attacker].mu: .2f}'
                delta_exposure = f'{ts.expose(attackers_old[attacker]): .2f}->{ts.expose(attackers_new[attacker]): .2f}'
                if ranks_old and attacker in ranks_old:
                    delta_rank = f'{ranks_old[attacker]}->{ranks_new[attacker]}'
                else:
                    delta_rank = f'{ranks_new[attacker]} (NEW!)'
                attacker_chart.append([name, delta_rating, delta_exposure, delta_rank])
            output.append(f"`Attackers - {losing_score}:\n{tabulate(attacker_chart, headers=headers, tablefmt='psql')}`\n\n")

            headers = ['Defender', 'Δ Rating', 'Δ Exposure', 'Δ Rank']
            defender_chart = []
            for defender in defenders_new:
                member = ctx.guild.get_member(int(defender))
                name = member.name
                delta_rating = f'{defenders_old[defender].mu: .2f}->{defenders_new[defender].mu: .2f}'
                delta_exposure = f'{ts.expose(defenders_old[defender]): .2f}->{ts.expose(defenders_new[defender]): .2f}'
                if ranks_old and defender in ranks_old:
                    delta_rank = f'{ranks_old[defender]}->{ranks_new[defender]}'
                else:
                    delta_rank = f'{ranks_new[defender]} (NEW!)'
                defender_chart.append([name, delta_rating, delta_exposure, delta_rank])
            output.append(f"`Defenders - {winning_score}:\n{tabulate(defender_chart, headers=headers, tablefmt='psql')}`\n")
            # send output
            await ctx.send(''.join(output))

    @cog_ext.cog_slash(name='map', description='choose a map randomly or through vetos', guild_ids=GUILDS, options=[
        create_option(
            name='method',
            description='method to choose a map',
            option_type=3,
            required=False,
            choices=[
                create_choice(
                    name='random',
                    value='random'
                ),
                create_choice(
                    name='veto',
                    value='veto'
                )
            ]
        )
    ])
    async def _map(self, ctx: SlashContext, method='random'):
        if method == 'random':
            map = random.choice(VALORANT_MAP_POOL)
            await ctx.send(f'**MAP: {map}**')
        elif method == 'veto':
            if ctx.guild.id not in guild_to_teams or not guild_to_teams[ctx.guild.id]:
                await ctx.send('use /make before veto')
                return
            guild_to_remaining_maps[ctx.guild.id] = VALORANT_MAP_POOL.copy()
            # next to veto
            a_total = sum([get_rating(a, ctx.guild.id).mu for a in guild_to_teams[ctx.guild.id]['attackers']])
            d_total = sum([get_rating(d, ctx.guild.id).mu for d in guild_to_teams[ctx.guild.id]['defenders']])
            if a_total > d_total:
                guild_to_next_team_to_veto[ctx.guild.id] = 'defenders'
            else:
                guild_to_next_team_to_veto[ctx.guild.id] = 'attackers'
            await ctx.send(f"**{guild_to_next_team_to_veto[ctx.guild.id].capitalize()}** turn to /veto")

    @cog_ext.cog_slash(name='veto', description='veto a map', guild_ids=GUILDS, options=[
        create_option(
            name='choice',
            description='map to veto',
            option_type=3,
            required=True,
            choices=VALORANT_SLASH_CHOICES
        )
    ])
    async def _veto(self, ctx: SlashContext, choice):
        if ctx.guild.id not in guild_to_teams or not guild_to_teams[ctx.guild.id]:
            await ctx.send('Use /make and /map veto before vetoing.')
            return
        if ctx.guild.id not in guild_to_remaining_maps or not guild_to_remaining_maps[ctx.guild.id]:
            await ctx.send('No maps to veto.')
            return
        if str(ctx.author.id) not in guild_to_teams[ctx.guild.id][guild_to_next_team_to_veto[ctx.guild.id]]:
            await ctx.send('Not your turn.')
            return
        if choice not in guild_to_remaining_maps[ctx.guild.id]:
            await ctx.send('Map already vetoed.')
            return

        output = []
        guild_to_remaining_maps[ctx.guild.id].remove(choice)
        output += (f'**{choice}** vetoed.\n')

        if len(guild_to_remaining_maps[ctx.guild.id]) == 1:
            output += f'**MAP: {guild_to_remaining_maps[ctx.guild.id][0]}**\n'
            await ctx.send(''.join(output))
            guild_to_remaining_maps[ctx.guild.id] = []
            return

        if guild_to_next_team_to_veto[ctx.guild.id] == 'attackers':
            guild_to_next_team_to_veto[ctx.guild.id] = 'defenders'
        else:
            guild_to_next_team_to_veto[ctx.guild.id] = 'attackers'

        output += f'Remaining Maps: **{", ".join(guild_to_remaining_maps[ctx.guild.id])}**\n'
        output += f"{guild_to_next_team_to_veto[ctx.guild.id].capitalize()} turn to /veto\n"
        await ctx.send(''.join(output))

    @cog_ext.cog_slash(name='leaderboard', description='get list of players on server sorted by rating', guild_ids=GUILDS, options=[
        create_option(
            name='metric',
            description='metric to sort leaderboard',
            option_type=3,
            required=False,
            choices=[
                create_choice(
                    name='mean',
                    value='mean'
                ),
                create_choice(
                    name='exposure',
                    value='exposure'
                )
            ]
        )
    ])
    async def _leaderboard(self, ctx: SlashContext, metric='exposure'):
        if metric == 'mean':
            leaderboard = get_leaderboard(ctx.guild.id)
        elif metric == 'exposure':
            leaderboard = get_leaderboard_by_exposure(ctx.guild.id)
        if not leaderboard:
            await ctx.send('No Ranked Players.')
            return
        output = []
        headers = ['Rank', 'Name', 'Rating', 'Exposure', 'Win/Loss']
        rank = 0
        last = None, 0    # rating, rank
        for item in leaderboard:
            member = ctx.guild.get_member(int(item[0]))
            if member:
                w, l = get_win_loss(item[0], ctx.guild.id)
                rank += 1
                if last[0] and ((metric == 'exposure' and isclose(ts.expose(item[1]), ts.expose(last[0]))) or (metric == 'mean' and isclose(item[1], last[0]))):
                    output.append([last[1], member.name, f'{item[1].mu: .4f} ± {item[1].sigma: .2f}', round(ts.expose(item[1]), 4), f'{w}W {l}L'])
                else:
                    output.append([rank, member.name, f'{item[1].mu: .4f} ± {item[1].sigma: .2f}', round(ts.expose(item[1]), 4), f'{w}W {l}L'])
                last = item[1], rank
        await ctx.send(f"`Leaderboard (by {metric}):\n{tabulate(output, headers=headers, tablefmt='psql', floatfmt='.4f')}`")

    @cog_ext.cog_slash(name='move', description='move players to team voice channels', guild_ids=GUILDS)
    async def _move(self, ctx: SlashContext):
        if ctx.guild.id not in guild_to_teams:
            await ctx.send("Use /start to begin matchmaking.")
            return
        gd = ctx.guild
        # find attacker and defender voice channels
        attacker_channel, defender_channel = None, None
        # check if Valorant channel category exists
        valorant_category = None
        for category in gd.categories:
            if category.name.lower() == 'valorant':
                valorant_category = category
        if valorant_category is None:
            # make it
            valorant_category = await gd.create_category_channel('VALORANT')
            # await ctx.send("VALORANT category created.")
        for vc in gd.voice_channels:
            # ignore voice channels outside of VALORANT
            if vc.category != valorant_category:
                continue
            if vc.name.lower() == 'attackers':
                attacker_channel = vc
            elif vc.name.lower() == 'defenders':
                defender_channel = vc
        # create vc if necessary
        if attacker_channel is None:
            attacker_channel = await gd.create_voice_channel('Attackers', category=valorant_category)
        if defender_channel is None:
            defender_channel = await gd.create_voice_channel('Defenders', category=valorant_category)
        # move members to right channel
        attackers = guild_to_teams[gd.id]['attackers']
        defenders = guild_to_teams[gd.id]['defenders']
        count = 0
        for attacker in attackers:
            member = gd.get_member(attacker)
            if member.voice is not None:
                count += 1
                await member.move_to(attacker_channel)
        for defender in defenders:
            member = gd.get_member(defender)
            if member.voice is not None:
                count += 1
                await member.move_to(defender_channel)
        await ctx.send(f"{count} player{'s' if count > 1 else ''} moved.")

    @cog_ext.cog_slash(name='back', description='move all players to same voice channel', guild_ids=GUILDS)
    async def _back(self, ctx: SlashContext):
        # find VALORANT voice channels
        guild = ctx.guild
        for vc in guild.voice_channels:
            # ignore voice channels outside of VALORANT
            if vc.category is not None and vc.category.name.lower() != 'valorant':
                continue
            elif vc.name.lower() == 'attackers':
                for vc2 in guild.voice_channels:
                    if vc2.name.lower() == 'defenders':
                        for defender in vc.members:
                            await defender.move_to(vc2)
                        await ctx.send('✅')


    @cog_ext.cog_slash(name='rating', guild_ids=GUILDS, description='find rating of specified player', options=[
        create_option(
            name='player',
            description='player to find rating for',
            option_type=6,
            required=False
        )
    ])
    async def _rating(self, ctx: SlashContext, player=None):
        if not player:
            players = [ctx.author.id]
        else:
            players = [player.id]
        headers = ['Name', 'Rank', 'Rating', 'Exposure', 'Win/Loss']
        rating_chart = []
        for p in players:
            p = str(p)
            member = ctx.guild.get_member(int(p))
            name = member.name
            rank = get_ranks((p,), ctx.guild.id)[p]
            rating = get_rating(p, ctx.guild.id)
            exposure = ts.expose(rating)
            w, l = get_win_loss(p, ctx.guild.id)
            rating_chart.append([name, rank, f'{rating.mu: .4f} ± {rating.sigma: .2f}', f'{exposure: .4f}', f'{w}W {l}L'])
        await ctx.send(f"`\n{tabulate(rating_chart, headers=headers, tablefmt='psql')}\n`")

    @cog_ext.cog_slash(name='undo', description='undo the last recorded result', guild_ids=GUILDS, permissions={
        825900837083676735: create_permission(263745246821744640, SlashCommandPermissionType.USER, True),
        342839495328137216: create_permission(263745246821744640, SlashCommandPermissionType.USER, True)
    })
    async def _undo(self, ctx: SlashContext):
        # reset the ratings
        match = undo_last_match(ctx.guild.id)
        if not match:
            await ctx.send('Error undoing match.')
            return
        # reset the record cooldown
        if ctx.guild.id in guild_to_last_result_time:
            del guild_to_last_result_time[ctx.guild.id]
        await ctx.send('Undo successful.')

    @cog_ext.cog_slash(name='history', description='view the last 10 matches', guild_ids=GUILDS, options=[
        create_option(
            name='user',
            description='user to find history for',
            option_type=6,
            required=False
            )
        ]
    )
    async def _history(self, ctx: SlashContext, user=None):
        output = []
        if user:
            userid = str(user.id)
            # per-user match history
            history = get_history(ctx.guild.id, userid=userid)
            if not history:
                await ctx.send('No recorded matches.')
                return
            
            # plot rating history
            past_ratings = get_past_ratings(userid, ctx.guild.id)
            # scaling
            if len(past_ratings) < 30:
                past_ratings = [val for val in past_ratings for _ in range(0, ceil(30/len(past_ratings)))]
            elif len(past_ratings) > 60:
                past_ratings = past_ratings[::len(past_ratings)//30]
            output.append('`Rating History:\n' + plot(past_ratings) + '`\n')

            # win/loss
            win, loss = get_win_loss(userid, ctx.guild.id)
            output.append(f'\n`Match History ({win}W {loss}L):`\n')

            # list of past matches
            if len(history) > 10:
                recent = history[:10]
            else:
                recent = history
            for match in recent:
                output.append(f"`{match['time'].strftime(time_format)}: ")
                output.append(', '.join([ctx.guild.get_member(int(uid)).name for uid in match['attackers']]))
                output.append(f" { match['attacker_score']} - {match['defender_score']} ")
                output.append(', '.join([ctx.guild.get_member(int(uid)).name for uid in match['defenders']]))
                if userid in match['attackers']:
                    output.append(f" ({match['old_ratings'][userid].mu: .2f} -> {match['attackers'][userid].mu: .2f})`\n")
                else:
                    output.append(f" ({match['old_ratings'][userid].mu: .2f} -> {match['defenders'][userid].mu: .2f})`\n")
            if len(history) > 10:
                output.append(f"`... and {len(history)-10} more`")
        else:
            # guild-wide match history
            history = get_history(ctx.guild.id)
            all_past_ratings = [get_past_ratings(playerid, ctx.guild.id, pad=True) for playerid in get_playerlist(ctx.guild.id)]

            # scaling
            if all_past_ratings and len(all_past_ratings[0]) < 30:
                all_past_ratings = [[val for val in past_ratings for _ in range(0, ceil(30/len(past_ratings)))] for past_ratings in all_past_ratings]
            if all_past_ratings and len(all_past_ratings[0]) > 60:
                all_past_ratings = [past_ratings[::len(past_ratings)//30] for past_ratings in all_past_ratings]
            output.append('`Rating History:\n' + plot(all_past_ratings) + '`\n\n')

            output.append('`Recent matches:`\n')
            for match in history[-10:]:
                # match info
                output.append(f"`{match['time'].strftime(time_format)}: ")
                output.append(', '.join([ctx.guild.get_member(int(uid)).name for uid in match['attackers']]))
                output.append(f" { match['attacker_score']} - {match['defender_score']} ")
                output.append(', '.join([ctx.guild.get_member(int(uid)).name for uid in match['defenders']]))
                output.append('`\n')
            if len(history) > 10:
                output.append(f"`... and {len(history)-10} more`")
        await ctx.send(''.join(output))

    @cog_ext.cog_slash(name='clean', description='reset teams and remove created voice channels', guild_ids=GUILDS)
    async def _clean(self, ctx: SlashContext):
        # find VALORANT voice channels
        guild = ctx.guild
        for vc in guild.voice_channels:
            # ignore voice channels outside of VALORANT
            if vc.category is not None and vc.category.name.lower() != 'valorant':
                continue
            if vc.name.lower() == 'attackers':
                await vc.delete()
                await ctx.send('Attacker voice channel deleted.')
            elif vc.name.lower() == 'defenders':
                await vc.delete()
                await ctx.send('Defender voice channel deleted.')
        # delete VALORANT category
        for category in guild.categories:
            if category.name.lower() == 'valorant':
                await category.delete()
                await ctx.send('VALORANT category deleted.')
        guild_to_teams[ctx.guild.id] = {'attackers':[], 'defenders':[]}
        await ctx.send('Players emptied.')

def setup(bot):
    bot.add_cog(Valorant(bot))
