import time
import random

import discord
from discord.ext import commands
from discord_slash import cog_ext, SlashContext

from main import clear_db, db_string, get_skill, set_rating, record_result, make_teams, get_leaderboard

# global discord id lists
GUILDS = [825900837083676732]
ADMINS = [335828416412778496, 263745246821744640]

# VALORANT MAPS
VALORANT_MAP_POOL = ['Bind', 'Haven', 'Split', 'Ascent', 'Icebox', 'Breeze']

# dicts for guild-local variables
guild_to_start_msg = {}
guild_to_teams = {}

class Valorant(commands.Cog):
    def __init__(self, bot):
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
        '''
        Clean up created voice channels if they're empty.
        '''
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

    # @cog_ext.cog_slash(name='help')
    # async def help(self, ctx):
    #     print(db_string(ctx.guild.id))
    #     output = []
    #     output += "**Available Commands:**\n"
    #     output += "\t**$start** - start matchmaking process, bot sends message for players to react to\n"
    #     output += "\t\t**$unrated** - create random teams from reactions to $start message\n"
    #     output += "\t\t**$rated** - create teams based on MMR\n"
    #     output += "\t\t\t**$attackers** - record a win for the Attackers\n"
    #     output += "\t\t\t**$defenders** - record a win for the Defenders\n"
    #     output += "\t\t**$move** - move players to generated teams' voice channels\n"
    #     output += "\t\t**$back** - move all players into attacker voice channel\n"
    #     output += "\t**$rating** - get your current rating\n"
    #     output += "\t**$leaderboard** - get players sorted by rating\n"
    #     output += "\t**$clean** - reset players and remove created voice channels\n"
    #     output += "\t**$help** - list available commands"
    #     await ctx.send(''.join(output))
    
    @cog_ext.cog_slash(name='start', guild_ids=GUILDS, description='start matchmaking process, bot sends message for players to react to')
    async def _start(self, ctx: SlashContext):
        start_msg = await ctx.send("React to this message if you're playing :)")
        guild_to_start_msg[ctx.guild.id] = start_msg
    
    @cog_ext.cog_slash(name='unrated', guild_ids=GUILDS)
    async def _unrated(self, ctx: SlashContext):
        # read reacts and make teams randomly without ranks
        if ctx.guild.id not in guild_to_start_msg or guild_to_start_msg[ctx.guild.id] is None:
            await ctx.send('use $start before $unrated')
        else:
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
            output += "\Attackers:\n"
            for member in attackers:
                output += f'\t<@!{member}>'
            output += "\n\Defenders:\n"
            for member in defenders:
                output += f'\t<@!{member}>'
            # store teams
            guild_to_teams[ctx.guild.id]['attackers'] = attackers
            guild_to_teams[ctx.guild.id]['defenders'] = defenders
            # send output
            print(f'[{ctx.guild.id}]: Unrated Game created in {round(time.time()-start_time, 4)}s')
            await ctx.send(''.join(output))

    @cog_ext.cog_slash(name='rated', guild_ids=GUILDS)
    async def _rated(self, ctx: SlashContext):
        if ctx.guild.id not in guild_to_start_msg or guild_to_start_msg[ctx.guild.id] is None:
            await ctx.send('use *$start* before *$rated*')
        else:
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
            output_string = f'Predicted Quality: {round(quality*200, 2)}\n'
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

    @cog_ext.cog_slash(name='attackers', guild_ids=GUILDS)
    async def _attackers(self, ctx: SlashContext):
        if ctx.author.id not in ADMINS:
            await ctx.send('Permission Denied ❌. Blame Djaenk')
            return
        if not guild_to_teams[ctx.guild.id]['attackers']:
            await ctx.send('use *$make* or *$rated* before recording a result')
        else:
            attackers, defenders, attackers_new, defenders_new = record_result(guild_to_teams[ctx.guild.id]['attackers'], guild_to_teams[ctx.guild.id]['defenders'], ctx.guild.id)
            output = []
            output = '**Win for** ***Attackers*** **recorded.**\n'
            output += "\n**Attackers:**\n"
            for member in attackers:
                output += f'\t<@!{member}> ({round(attackers[member].mu, 2)} -> {round(attackers_new[member].mu, 2)})\n'
            output += "\n\n**Defenders:**\n"
            for member in defenders:
                output += f'\t<@!{member}> ({round(defenders[member].mu, 2)} -> {round(defenders_new[member].mu, 2)})\n'
            # send output
            await ctx.send(''.join(output))
    
    @cog_ext.cog_slash(name='defenders', guild_ids=GUILDS)
    async def _defenders(self, ctx: SlashContext):
        if ctx.author.id not in ADMINS:
            await ctx.send('Permission Denied ❌. Blame Djaenk')
            return
        if not guild_to_teams[ctx.guild.id]['defenders']:
            await ctx.send('use *$make* or *$rated* before recording a result')
        else:
            defenders, attackers, defenders_new, attackers_new = record_result(guild_to_teams[ctx.guild.id]['defenders'], guild_to_teams[ctx.guild.id]['attackers'], ctx.guild.id)
            output = []
            output = '**Win for** ***Defenders*** **recorded.**\n'
            output += "\n**Attackers:**\n"
            for member in attackers:
                output += f'\t<@!{member}> ({round(attackers[member].mu, 2)} -> {round(attackers_new[member].mu, 2)})\n'
            output += "\n\n**Defenders:**\n"
            for member in defenders:
                output += f'\t<@!{member}> ({round(defenders[member].mu, 2)} -> {round(defenders_new[member].mu, 2)})\n'
            # send output
            await ctx.send(''.join(output))
    
    @cog_ext.cog_slash(name='leaderboard', guild_ids=GUILDS)
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
                rank += 1
                if (item[1].mu, item[1].sigma) == last[:2]:
                    output += f'**{last[2]}**. ***{member.name}*** - {round(item[1].mu, 4)} ± {round(item[1].sigma, 2)}\n'
                else:
                    output += f'**{rank}**. ***{member.name}*** - {round(item[1].mu, 4)} ± {round(item[1].sigma, 2)}\n'
                last = item[1].mu, item[1].sigma, rank
        print(f'[{ctx.guild.id}]: Leaderboard fetched in {round(time.time()-start_time, 4)}s')
        await ctx.send(''.join(output))

    @cog_ext.cog_slash(name='move', guild_ids=GUILDS)
    async def _move(self, ctx: SlashContext):
        if ctx.guild.id not in guild_to_teams:
            await ctx.send("Use $start to begin matchmaking.")
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

    @cog_ext.cog_slash(name='back', guild_ids=GUILDS)
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

    @cog_ext.cog_slash(name='rating', guild_ids=GUILDS)
    async def _rating(self, ctx: SlashContext):
        if ctx.message.raw_mentions:
            for id in ctx.message.raw_mentions:
                skill = get_skill(id, ctx.guild.id)
                await ctx.send(f'\t<@!{id}> - {round(skill.mu, 4)} ± {round(skill.sigma, 2)}\n')
        else:
            authorid = ctx.author.id
            skill = get_skill(authorid, ctx.guild.id)
            await ctx.send(f'\t<@!{authorid}> - {round(skill.mu, 4)} ± {round(skill.sigma, 2)}')

    @cog_ext.cog_slash(name='clean', guild_ids=GUILDS)
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