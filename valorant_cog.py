import time
from datetime import datetime
from pytz import timezone
import random
import shelve

from discord.ext import commands
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option, create_choice
from asciichartpy import plot

from main import get_past_ratings, get_win_loss, set_rating, get_skill, record_result, make_teams, get_leaderboard

# local time zone
central = timezone('US/Central')
time_format = '%a %b %-d %-I:%M %p'

# global discord id lists
GUILDS = [825900837083676732]
ADMINS = [335828416412778496, 263745246821744640]

# VALORANT MAPS
VALORANT_MAP_POOL = ['Bind', 'Haven', 'Split', 'Ascent', 'Icebox', 'Breeze']

# dicts for guild-local variables
guild_to_start_msg = {}
guild_to_teams = {}
guild_to_last_result_time = {}

class Valorant(commands.Cog):
    def __init__(self, bot):
        """VALORANT commands for matchmaking Discord bot."""
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        # update start message with reactors
        if payload.guild_id in guild_to_start_msg and payload.message_id == guild_to_start_msg[payload.guild_id].id:
            channel = self.bot.get_channel(payload.channel_id)
            start_msg = await channel.fetch_message(guild_to_start_msg[payload.guild_id].id)
            players = set()
            for reaction in start_msg.reactions:
                users = await reaction.users().flatten()
                players.update((user.id for user in users))
            output_message = "React to this message if you're playing" + f' ({len(players)})' + ''.join([f'\t<@!{member}>' for member in players] )
            await start_msg.edit(content=output_message)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        # update start message with reactors
        if payload.guild_id in guild_to_start_msg and payload.message_id == guild_to_start_msg[payload.guild_id].id:
            channel = self.bot.get_channel(payload.channel_id)
            start_msg = await channel.fetch_message(guild_to_start_msg[payload.guild_id].id)
            players = set()
            for reaction in start_msg.reactions:
                users = await reaction.users().flatten()
                players.update((user.id for user in users))
            output_message = "React to this message if you're playing" + f' ({len(players)})' + ''.join([f'\t<@!{member}>' for member in players])
            await start_msg.edit(content=output_message)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Clean up created voice channels if they're empty."""
        if before.channel == None or before.channel.category == None or before.channel.category.name.lower() != 'valorant':
            return
        guild = before.channel.guild
        t_vc = ct_vc = None
        # find channels
        for vc in guild.voice_channels:
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
                for category in guild.categories:
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
                )
            ]

        )
    ])
    async def _make(self, ctx: SlashContext, match_type: str, description='matchmake game from reacts to /start with option for MMR'):
        if ctx.guild.id not in guild_to_start_msg or guild_to_start_msg[ctx.guild.id] is None:
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
        output_string = f'Predicted Quality: {round(quality*10, 2)}\n'
        output_string += "\nAttackers:\n"
        for member in attackers:
            output_string += f'\t<@!{member}>({round(get_skill(member, ctx.guild.id).mu, 2)}) '
        output_string += "\n\nDefenders:\n"
        for member in defenders:
            output_string += f'\t<@!{member}>({round(get_skill(member, ctx.guild.id).mu, 2)}) '
        # store teams
        guild_to_teams[ctx.guild.id]['attackers'] = attackers
        guild_to_teams[ctx.guild.id]['defenders'] = defenders
        # send output
        print(f'[{ctx.guild.id}]: Rated Game created in {round(time.time()-start_time, 4)}s')
        await ctx.send(output_string)

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
        if ctx.guild.id not in guild_to_start_msg or guild_to_start_msg[ctx.guild.id] is None:
            await ctx.send('use */start* and */make* before */record*')
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
            attackers, defenders, attackers_new, defenders_new = record_result(guild_to_teams[ctx.guild.id]['attackers'], guild_to_teams[ctx.guild.id]['defenders'], winning_score, losing_score, ctx.guild.id)
            output = []
            output = '**Win for** ***Attackers*** **recorded.**\n'
            output += f"\n**Attackers - {winning_score}:**\n"
            for member in attackers:
                output += f'\t<@!{member}> ({round(attackers[member].mu, 2)} -> {round(attackers_new[member].mu, 2)})\n'
            output += f"\n\n**Defenders - {losing_score}:**\n"
            for member in defenders:
                output += f'\t<@!{member}> ({round(defenders[member].mu, 2)} -> {round(defenders_new[member].mu, 2)})\n'
            # send output
            await ctx.send(''.join(output))
    
    async def _defenders(self, winning_score, losing_score, ctx: SlashContext):
        if not guild_to_teams[ctx.guild.id]['defenders']:
            await ctx.send('use *$make* or *$rated* before recording a result')
        else:
            attackers, defenders, attackers_new, defenders_new = record_result(guild_to_teams[ctx.guild.id]['attackers'], guild_to_teams[ctx.guild.id]['defenders'], losing_score, winning_score, ctx.guild.id)
            output = []
            output = '**Win for** ***Defenders*** **recorded.**\n'
            output += f"\n**Attackers - {losing_score}:**\n"
            for member in attackers:
                output += f'\t<@!{member}> ({round(attackers[member].mu, 2)} -> {round(attackers_new[member].mu, 2)})\n'
            output += f"\n\n**Defenders - {winning_score}:**\n"
            for member in defenders:
                output += f'\t<@!{member}> ({round(defenders[member].mu, 2)} -> {round(defenders_new[member].mu, 2)})\n'
            # send output
            await ctx.send(''.join(output))
    
    @cog_ext.cog_slash(name='leaderboard', description='get list of players on server sorted by rating', guild_ids=GUILDS)
    async def _leaderboard(self, ctx: SlashContext):
        start_time = time.time()
        leaderboard = get_leaderboard(ctx.guild.id)
        if not leaderboard:
            await ctx.send('No Ranked Players.')
            return
        output = []
        rank = 0
        last = 0, 0, 0    # mu, sigma, rank
        for item in leaderboard:
            member = ctx.guild.get_member(int(item[0]))
            if member:
                w, l = get_win_loss(item[0], ctx.guild.id)
                rank += 1
                if (item[1].mu, item[1].sigma) == last[:2]:
                    output += f'**{last[2]}**. ***{member.name}*** - {round(item[1].mu, 4)} ± {round(item[1].sigma, 2)} ({w}W {l}L)\n'
                else:
                    output += f'**{rank}**. ***{member.name}*** - {round(item[1].mu, 4)} ± {round(item[1].sigma, 2)} ({w}W {l}L)\n'
                last = item[1].mu, item[1].sigma, rank
        print(f'[{ctx.guild.id}]: Leaderboard fetched in {round(time.time()-start_time, 4)}s')
        await ctx.send(''.join(output))

    @cog_ext.cog_slash(name='move', description='move players to team voice channels', guild_ids=GUILDS)
    async def _move(self, ctx: SlashContext):
        if ctx.guild.id not in guild_to_teams:
            await ctx.send("Use /start to begin matchmaking.")
            return
        guild = ctx.guild
        # find attacker and defender voice channels
        attacker_channel, defender_channel = None, None
        # check if Valorant channel category exists
        valorant_category = None
        for category in guild.categories:
            if category.name.lower() == 'valorant':
                valorant_category = category
        if valorant_category is None:
            # make it
            valorant_category = await guild.create_category_channel('VALORANT')
            # await ctx.send("VALORANT category created.")
        for vc in guild.voice_channels:
            # ignore voice channels outside of VALORANT
            if vc.category != valorant_category:
                continue
            if vc.name.lower() == 'attackers':
                attacker_channel = vc
            elif vc.name.lower() == 'defenders':
                defender_channel = vc
        # create vc if necessary
        if attacker_channel is None:
            attacker_channel = await guild.create_voice_channel('Attackers', category=valorant_category)
        if defender_channel is None:
            defender_channel = await guild.create_voice_channel('Defenders', category=valorant_category)
        # move members to right channel
        attackers = guild_to_teams[guild.id]['attackers']
        defenders = guild_to_teams[guild.id]['defenders']
        count = 0
        for attacker in attackers:
            member = guild.get_member(attacker)
            if member.voice is not None:
                count += 1
                await member.move_to(attacker_channel)
        for defender in defenders:
            member = guild.get_member(defender)
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


    @cog_ext.cog_slash(name='rating', guild_ids=GUILDS, description='find rating of specified user', options=[
        create_option(
            name='user',
            description='user to find rating for',
            option_type=6,
            required=True
        )
    ])
    async def _rating(self, ctx: SlashContext, user):
        skill = get_skill(user.id, ctx.guild.id)
        w, l = get_win_loss(user.id, ctx.guild.id)
        await ctx.send(f'\t<@!{user.id}> - {round(skill.mu, 4)} ± {round(skill.sigma, 2)}  ({w}W {l}L)\n')

    @cog_ext.cog_slash(name='undo', description='undo the last recorded result', guild_ids=GUILDS)
    async def _undo(self, ctx: SlashContext):
        # reset the ratings
        with shelve.open(str(ctx.guild.id), writeback=True) as db:
            if 'history' not in db or not db['history']:
                await ctx.send('No recorded matches.')
                return
            match = db['history'][-1]
            print('about to reset ratings')
            for player in match['attackers']:
                set_rating(str(player), match['old_ratings'][player], ctx.guild.id)
            for player in match['defenders']:
                set_rating(str(player), match['old_ratings'][player], ctx.guild.id)
            # delete from match history
            del db['history'][-1]
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
        with shelve.open(str(ctx.guild.id)) as db:
            if 'history' not in db or not db['history']:
                await ctx.send('No recorded matches.')
                return
            if user:
                userid = str(user.id)
                history = list(filter(lambda x: (userid) in x['attackers'] or (userid) in x['defenders'], db['history']))
                history.reverse()
                if not history:
                    await ctx.send('No recorded matches.')
                    return
                
                # plot rating history
                past_ratings = get_past_ratings(userid, ctx.guild.id)
                past_ratings = [val for val in past_ratings for _ in (0, 1)] # duplicate elements for scaling
                output.append('`' + plot(past_ratings) + '`\n')

                # list of past matches
                for match in history:
                    output.append(f"`{match['time'].strftime(time_format)}: ")
                    output.append(', '.join([ctx.guild.get_member(int(uid)).name for uid in match['attackers']]))
                    output.append(f" { match['attacker_score']} - {match['defender_score']} ")
                    output.append(','.join([ctx.guild.get_member(int(uid)).name for uid in match['defenders']]))
                    if userid in match['attackers']:
                        output.append(f" ({round(match['old_ratings'][userid].mu, 2)} -> {round(match['attackers'][userid].mu, 2)})`\n")
                    else:
                        output.append(f" ({round(match['old_ratings'][userid].mu, 2)} -> {round(match['defenders'][userid].mu, 2)})`\n")
            else:
                # list of past matches
                history = db['history'][-10:]
                history.reverse()
                all_past_ratings = [get_past_ratings(playerid, ctx.guild.id, pad=True) for playerid in db['ratings']]
                all_past_ratings = [[val for val in past_ratings for _ in (0, 1)] for past_ratings in all_past_ratings] # duplicate elements for scaling
                output.append('`' + plot(all_past_ratings) + '`\n')
                for match in history:
                    # match info
                    output.append(f"`{match['time'].strftime(time_format)}: ")
                    output.append(', '.join([ctx.guild.get_member(int(uid)).name for uid in match['attackers']]))
                    output.append(f" { match['attacker_score']} - {match['defender_score']} ")
                    output.append(','.join([ctx.guild.get_member(int(uid)).name for uid in match['defenders']]))
                    output.append('`\n')
                print(all_past_ratings)
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