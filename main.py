import discord
import os
import random
import shelve
import trueskill as ts
import logging

# set up logging
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# global userid lists
ADMINS = [335828416412778496, 263745246821744640]

# discord py client
intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)

# dicts for guild-local variables
guild_to_start_msg = {}
guild_to_teams = {}

# TrueSkill Rating Settings
env = ts.TrueSkill(draw_probability=0.05)
env.make_as_global()

# TrueSkill DB cache
ratings_cache = {}

# TrueSkill DB helper functions
def clear_db(guildid):
    with shelve.open(str(guildid)) as db:
        for id in db.keys():
            del db[id]

def db_string(guildid):
    output = []
    with shelve.open(str(guildid)) as db:
        for id in db.keys():
            output.append(id)
            output.append(str(db[id]))
    return ' '.join(output)

def get_skill(userid, guildid):
    '''
    Returns the TrueSkill rating of a discord user.
    Will initialize skill if none is found.
    :param userid: Discord userid to find
    :return: stored TrueSkill rating object of userid
    '''
    userid = str(userid)
    guildid = str(guildid)

    # check cache first
    if guildid not in ratings_cache:
            ratings_cache[guildid] = {}
    if userid in ratings_cache[guildid]:
        return ratings_cache[guildid][userid]
    
    print(f'Cache Miss: guildid = {guildid} userid = {userid}')

    with shelve.open(str(guildid), writeback=True) as db:
        if 'ratings' not in db:
            db['ratings'] = {}
        ratings = db['ratings']
        if userid in ratings:
            mu, sigma = ratings[userid]
            return ts.Rating(float(mu), float(sigma))
        new_rating = ts.Rating()
        ratings_cache[guildid][userid] = new_rating
        ratings[userid] = new_rating.mu, new_rating.sigma
        db['ratings'][userid] = new_rating.mu, new_rating.sigma
        return new_rating

def record_result(winning_team, losing_team, guildid):
    '''
    Updates the TrueSkill ratings given a result.
    :param winning_team: list of userids of players on the winning team
    :param losing_team: list of userids of players on the losing team
    :return: old winning team ratings, old losing team ratings, new winning team ratings, new losing team ratings
    '''
    winning_team_ratings = {id : get_skill(id, guildid) for id in winning_team}
    losing_team_ratings = {id : get_skill(id, guildid) for id in losing_team}
    winning_team_ratings_new, losing_team_ratings_new = ts.rate([winning_team_ratings, losing_team_ratings], [0,1])
    with shelve.open(str(guildid), writeback=True) as db:
        ratings = db['ratings']
        for id in winning_team_ratings:
            ratings_cache[str(guildid)][str(id)] = winning_team_ratings_new[id]
            ratings[str(id)] = winning_team_ratings_new[id].mu, winning_team_ratings_new[id].sigma
        for id in losing_team_ratings:
            ratings_cache[str(guildid)][str(id)] = losing_team_ratings_new[id]
            ratings[str(id)] = losing_team_ratings_new[id].mu, losing_team_ratings_new[id].sigma
        return winning_team_ratings, losing_team_ratings, winning_team_ratings_new, losing_team_ratings_new

def make_teams(players, guildid, pool=10):
    '''
    Make teams based on rating.
    :param players: list of userid of participating players
    :param pool: number of matches to generate from which the best is chosen
    :return: t (list of userids), ct (list of userids), predicted quality of match
    '''
    player_ratings = {id : get_skill(id, guildid) for id in players}
    t = ct = []
    best_quality = 0.0
    for i in range(pool):
        random.shuffle(players)
        team_size = len(players) // 2
        t1 = {id : player_ratings[id] for id in players[:team_size]}
        t2 = {id : player_ratings[id] for id in players[team_size:]}
        quality = ts.quality([t1, t2])
        if quality > best_quality:
            t = list(t1.keys())
            ct = list(t2.keys())
            best_quality = quality
    return t, ct, best_quality

def get_leaderboard(guildid):
    '''
    Gets list of userids and TrueSkill ratings, sorted by current rating
    :return: list of (userid, TrueSkill.Rating) tuples, sorted by rating
    '''
    with shelve.open(str(guildid), writeback=True) as db:
        if 'ratings' in db:
            ratings = {id : ts.TrueSkill(db['ratings'][id][0], db['ratings'][id][1]) for id in db['ratings']}
            #ratings = {id : get_skill(id, guildid) for id in db['ratings'].keys()}
            return sorted(ratings.items(), key=lambda x: (x[1].mu, -x[1].sigma), reverse=True)
        return None

@client.event
async def on_ready():
    # ratings_cache = {id : get_skill(id) for id in db.keys()}
    print('Logged in as {0.user}'.format(client))

@client.event
async def on_raw_reaction_add(payload):
    # update start message with reactors
    if payload.guild_id in guild_to_start_msg and payload.message_id == guild_to_start_msg[payload.guild_id].id:
        channel = client.get_channel(payload.channel_id)
        start_msg = await channel.fetch_message(guild_to_start_msg[payload.guild_id].id)
        players = set()
        for reaction in start_msg.reactions:
            users = await reaction.users().flatten()
            players.update((user.id for user in users))
        output_message = "React to this message if you're playing" + f' ({len(players)})' + ''.join([f'\t<@!{member}>' for member in players] )
        await start_msg.edit(content=output_message)

@client.event
async def on_raw_reaction_remove(payload):
    # update start message with reactors
    if payload.guild_id in guild_to_start_msg and payload.message_id == guild_to_start_msg[payload.guild_id].id:
        channel = client.get_channel(payload.channel_id)
        start_msg = await channel.fetch_message(guild_to_start_msg[payload.guild_id].id)
        players = set()
        for reaction in start_msg.reactions:
            users = await reaction.users().flatten()
            players.update((user.id for user in users))
        output_message = "React to this message if you're playing" + f' ({len(players)})' + ''.join([f'\t<@!{member}>' for member in players])
        await start_msg.edit(content=output_message)

@client.event
async def on_voice_state_update(member, before, after):
    '''
    Clean up created voice channels if they're empty.
    (could be less janky if we kept track of the created voice channels explicitly)
    '''
    if before.channel == None or before.channel.category == None or before.channel.category.name.lower() != 'csgo':
        return
    guild = before.channel.guild
    t_vc = ct_vc = None
    # find channels
    for vc in guild.voice_channels:
        if vc.category == None or vc.category.name.lower() != 'csgo':
            continue
        if vc.name.lower() == 't':
            t_vc = vc
        elif vc.name.lower() == 'ct':
            ct_vc = vc
    # delete CSGO channels if they're empty
    if t_vc is not None and ct_vc is not None:
        if len(t_vc.members) == len(ct_vc.members) == 0:
            await t_vc.delete()
            await ct_vc.delete()
            for category in guild.categories:
                if category.name.lower() == 'csgo':
                    await category.delete()

@client.event
async def on_message(message):
    
    # ignore your own messages
    if message.author == client:
        return

    if message.content.startswith('$help'):
        print(db_string(message.guild.id))
        output_string = "**Available Commands:**\n"
        output_string += "\t**$start** - start matchmaking process, bot sends message for players to react to\n"
        output_string += "\t\t**$unrated** - create random teams from reactions to $start message\n"
        output_string += "\t\t**$rated** - create teams based on MMR\n"
        output_string += "\t\t\t**$t** - record a win for the T\n"
        output_string += "\t\t\t**$ct** - record a win for the CT\n"
        output_string += "\t\t**$move** - move players to generated teams' voice channels\n"
        output_string += "\t\t**$back** - move all players into attacker voice channel\n"
        output_string += "\t**$rating** - get your current rating\n"
        output_string += "\t**$leaderboard** - get players sorted by rating\n"
        output_string += "\t**$clean** - reset players and remove created voice channels\n"
        output_string += "\t**$help** - list available commands"
        await message.channel.send(output_string)

    if message.content.startswith('$start'):
        start_msg = await message.channel.send("React to this message if you're playing :)")
        guild_to_start_msg[message.guild.id] = start_msg
        # guild_to_teams[message.guild.id] = {'t':[], 'ct':[]}

    if message.content.startswith('$unrated'):
        # read reacts and make teams randomly without ranks
        if message.guild.id not in guild_to_start_msg or guild_to_start_msg[message.guild.id] is None:
            await message.channel.send('use $start before $unrated')
        else:
            # read reacts
            guild_to_teams[message.guild.id] = {'t':[], 'ct':[]}
            start_msg = await message.channel.fetch_message(guild_to_start_msg[message.guild.id].id)
            players = set()
            for reaction in start_msg.reactions:
                users = await reaction.users().flatten()
                players.update((user.id for user in users))
            # create teams
            players = list(players)
            random.shuffle(players)
            team_size = len(players) // 2
            t = players[:team_size]
            ct = players[team_size:]
            # create output
            output_string += "\T:\n"
            for member in t:
                output_string += f'\t<@!{member}>'
            output_string += "\n\CT:\n"
            for member in ct:
                output_string += f'\t<@!{member}>'
            # store teams
            guild_to_teams[message.guild.id]['t'] = t
            guild_to_teams[message.guild.id]['ct'] = ct
            # send output
            await message.channel.send(output_string)
    
    if message.content.startswith('$rated'):
        if message.guild.id not in guild_to_start_msg or guild_to_start_msg[message.guild.id] is None:
            await message.channel.send('use *$start* before *$rated*')
        else:
            # read reacts
            guild_to_teams[message.guild.id] = {'t':[], 'ct':[]}
            start_msg = await message.channel.fetch_message(guild_to_start_msg[message.guild.id].id)
            players = set()
            for reaction in start_msg.reactions:
                users = await reaction.users().flatten()
                players.update((user.id for user in users))
            # must have at least one member on each team
            if len(players) < 2:
                await message.channel.send('must have **at least 2 players** for rated game')
                return
            # create teams
            t, ct, quality = make_teams(list(players), message.guild.id)
            # create output
            output_string = f'Predicted Quality: {round(quality*200, 2)}\n'
            output_string += "\nT:\n"
            for member in t:
                output_string += f'\t<@!{member}>({round(get_skill(member, message.guild.id).mu, 2)}) '
            output_string += "\n\nCT:\n"
            for member in ct:
                output_string += f'\t<@!{member}>({round(get_skill(member, message.guild.id).mu, 2)}) '
            # store teams
            guild_to_teams[message.guild.id]['t'] = t
            guild_to_teams[message.guild.id]['ct'] = ct
            # send output
            await message.channel.send(output_string)
    
    if message.content.startswith('$t'):
        if not guild_to_teams[message.guild.id]['t']:
            await message.channel.send('use *$make* or *$rated* before recording a result')
        else:
            t, ct, t_new, ct_new = record_result(guild_to_teams[message.guild.id]['t'], guild_to_teams[message.guild.id]['ct'], message.guild.id)
            output_string = '**Win for** ***T*** **recorded.**\n'
            output_string += "\n**T:**\n"
            for member in t:
                output_string += f'\t<@!{member}> ({round(t[member].mu, 2)} -> {round(t_new[member].mu, 2)})\n'
            output_string += "\n\n**CT:**\n"
            for member in ct:
                output_string += f'\t<@!{member}> ({round(ct[member].mu, 2)} -> {round(ct_new[member].mu, 2)})\n'
            # send output
            await message.channel.send(output_string)
    
    if message.content.startswith('$ct'):
        if not guild_to_teams[message.guild.id]['ct']:
            await message.channel.send('use *$make* or *$rated* before recording a result')
        else:
            ct, t, ct_new, t_new = record_result(guild_to_teams[message.guild.id]['ct'], guild_to_teams[message.guild.id]['t'], message.guild.id)
            output_string = '**Win for** ***CT*** **recorded.**\n'
            output_string += "\n**T:**\n"
            for member in t:
                output_string += f'\t<@!{member}> ({round(t[member].mu, 2)} -> {round(t_new[member].mu, 2)})\n'
            output_string += "\n\n**CT:**\n"
            for member in ct:
                output_string += f'\t<@!{member}> ({round(ct[member].mu, 2)} -> {round(ct_new[member].mu, 2)})\n'
            # send output
            await message.channel.send(output_string)

    if message.content.startswith('$leaderboard'):
        leaderboard = get_leaderboard(message.guild.id)
        if not leaderboard:
            await message.channel.send('No Ranked Players.')
            return
        output_string = ''
        rank = 0
        last = 0, 0, 0    # mu, sigma, rank
        for item in leaderboard:
            member = message.guild.get_member(int(item[0]))
            if member:
                rank += 1
                if (item[1].mu, item[1].sigma) == last[:2]:
                    output_string += f'**{last[2]}**. ***{member.name}*** - {round(item[1].mu, 4)} ± {round(item[1].sigma, 2)}\n'
                else:
                    output_string += f'**{rank}**. ***{member.name}*** - {round(item[1].mu, 4)} ± {round(item[1].sigma, 2)}\n'
                last = item[1].mu, item[1].sigma, rank
        await message.channel.send(output_string)
    
    if message.content.startswith('$move'):
        if message.guild.id not in guild_to_teams:
            await message.channel.send("Use $start to begin matchmaking.")
            return
        guild = message.guild
        # find attacker and defender voice channels
        attacker_channel, defender_channel = None, None
        # check if Valorant channel category exists
        csgo_category = None
        for category in guild.categories:
            if category.name.lower() == 'csgo':
                csgo_category = category
        if csgo_category is None:
            # make it
            csgo_category = await guild.create_category_channel('CSGO')
            # await message.channel.send("CSGO category created.")
        for vc in guild.voice_channels:
            # ignore voice channels outside of CSGO
            if vc.category != csgo_category:
                continue
            if vc.name.lower() == 't':
                attacker_channel = vc
            elif vc.name.lower() == 'ct':
                defender_channel = vc
        # create vc if necessary
        if attacker_channel is None:
            attacker_channel = await guild.create_voice_channel('t', category=csgo_category)
        if defender_channel is None:
            defender_channel = await guild.create_voice_channel('ct', category=csgo_category)
        # move members to right channel
        t = guild_to_teams[guild.id]['t']
        ct = guild_to_teams[guild.id]['ct']
        count = 0
        for attacker in t:
            member = guild.get_member(attacker)
            if member.voice is not None:
                count += 1
                await member.move_to(attacker_channel)
        for defender in ct:
            member = guild.get_member(defender)
            if member.voice is not None:
                count += 1
                await member.move_to(defender_channel)
        await message.channel.send(f"{count} player{'s' if count > 1 else ''} moved.")
    
    if message.content.startswith('$back'):
        # find CSGO voice channels
        guild = message.guild
        for vc in guild.voice_channels:
            # ignore voice channels outside of CSGO
            if vc.category is not None and vc.category.name.lower() != 'csgo':
                continue
            elif vc.name.lower() == 'ct':
                for vc2 in guild.voice_channels:
                    if vc2.name.lower() == 't':
                        for defender in vc.members:
                            await defender.move_to(vc2)
                        await message.channel.send('✅')

    if message.content.startswith('$rating'):
        if message.raw_mentions:
            for id in message.raw_mentions:
                skill = get_skill(id, message.guild.id)
                await message.channel.send(f'\t<@!{id}> - {round(skill.mu, 4)} ± {round(skill.sigma, 2)}\n')
        else:
            authorid = message.author.id
            skill = get_skill(authorid, message.guild.id)
            await message.channel.send(f'\t<@!{authorid}> - {round(skill.mu, 4)} ± {round(skill.sigma, 2)}')

    # remove csgo category and voice channels
    if message.content.startswith('$clean'):
        # find CSGO voice channels
        guild = message.guild
        for vc in guild.voice_channels:
            # ignore voice channels outside of CSGO
            if vc.category is not None and vc.category.name.lower() != 'csgo':
                continue
            if vc.name.lower() == 't':
                await vc.delete()
                await message.channel.send('Attacker voice channel deleted.')
            elif vc.name.lower() == 'ct':
                await vc.delete()
                await message.channel.send('Defender voice channel deleted.')
        # delete CSGO category
        for category in guild.categories:
            if category.name.lower() == 'csgo':
                await category.delete()
                await message.channel.send('CSGO category deleted.')
        guild_to_teams[message.guild.id] = {'t':[], 'ct':[]}
        await message.channel.send('Players emptied.')
    
    # admin-only clearing of repl db
    if message.content.startswith('$cleardb'):
        if message.author.id in ADMINS:
            clear_db(message.guild.id)
            await message.channel.send('Database cleared.')
        else:
            await message.channel.send('Permission denied.')

client.run(os.getenv('TOKEN'))