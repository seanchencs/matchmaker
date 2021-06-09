import os
import random
import shelve
import logging

import discord
from discord.ext import commands
from discord_slash import SlashCommand

import trueskill as ts

from CustomTrueSkill import rate_with_round_score

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

def set_rating(userid, rating, guildid):
    userid = str(userid)
    guildid = str(guildid)
    # write to cache
    if guildid not in ratings_cache:
        ratings_cache[guildid] = {}
    ratings_cache[guildid][userid] = rating
    # write to shelve persistent db
    with shelve.open(str(guildid), writeback=True) as db:
        if 'ratings' not in db:
            db['ratings'] = {}
        db['ratings'][userid] = rating.mu, rating.sigma
        print(ratings_cache[guildid][userid], db['ratings'][userid])

def record_result(winning_team, losing_team, winning_score, losing_score, guildid):
    '''
    Updates the TrueSkill ratings given a result.
    :param winning_team: list of userids of players on the winning team
    :param losing_team: list of userids of players on the losing team
    :return: old winning team ratings, old losing team ratings, new winning team ratings, new losing team ratings
    '''
    winning_team_ratings = {str(id) : get_skill(str(id), guildid) for id in winning_team}
    losing_team_ratings = {str(id) : get_skill(str(id), guildid) for id in losing_team}
    winning_team_ratings_new, losing_team_ratings_new = rate_with_round_score(winning_team_ratings, losing_team_ratings, winning_score, losing_score)
    with shelve.open(str(guildid), writeback=True) as db:
        ratings = db['ratings']
        for id in winning_team_ratings:
            ratings_cache[str(guildid)][str(id)] = winning_team_ratings_new[str(id)]
            ratings[str(id)] = winning_team_ratings_new[id].mu, winning_team_ratings_new[str(id)].sigma
        for id in losing_team_ratings:
            ratings_cache[str(guildid)][str(id)] = losing_team_ratings_new[str(id)]
            ratings[str(id)] = losing_team_ratings_new[id].mu, losing_team_ratings_new[str(id)].sigma
        return winning_team_ratings, losing_team_ratings, winning_team_ratings_new, losing_team_ratings_new

def make_teams(players, guildid, pool=10):
    '''
    Make teams based on rating.
    :param players: list of userid of participating players
    :param pool: number of matches to generate from which the best is chosen
    :return: t (list of userids), ct (list of userids), predicted quality of match
    '''
    player_ratings = {str(id) : get_skill(str(id), guildid) for id in players}
    t = ct = []
    best_quality = 0.0
    for i in range(pool):
        random.shuffle(players)
        team_size = len(players) // 2
        t1 = {str(id) : player_ratings[str(id)] for id in players[:team_size]}
        t2 = {str(id) : player_ratings[str(id)] for id in players[team_size:]}
        quality = ts.quality([t1, t2])
        if quality > best_quality:
            t = list(t1.keys())
            ct = list(t2.keys())
            best_quality = quality
    return t, ct, best_quality

def get_win_loss(userid, guildid):
    userid = str(userid)
    wins, losses = 0, 0
    with shelve.open(str(guildid)) as db:
        if 'history' in db:
            for match in db['history']:
                if userid in match['attackers']:
                    if match['attacker_score'] > match['defender_score']:
                        wins += 1
                    else:
                        losses += 1
                elif userid in match['defenders']:
                    if match['defender_score'] > match['attacker_score']:
                        wins += 1
                    else:
                        losses += 1
    return wins, losses

def get_past_ratings(userid, guildid):
    past_ratings = []
    with shelve.open(str(guildid)) as db:
        if 'history' in db:
            history = list(filter(lambda x: (userid) in x['attackers'] or (userid) in x['defenders'], db['history']))
            history.reverse()
            rating_history = [match['old_ratings'][userid].mu for match in history]
            rating_history.append(get_skill(userid, guildid).mu)
    return past_ratings

def get_leaderboard(guildid):
    '''
    Gets list of userids and TrueSkill ratings, sorted by current rating
    :return: list of (userid, TrueSkill.Rating) tuples, sorted by rating
    '''
    with shelve.open(str(guildid)) as db:
        if 'ratings' in db:
            # ratings = {id : ts.TrueSkill(db['ratings'][id][0], db['ratings'][id][1]) for id in db['ratings']}
            ratings = {str(id) : get_skill(str(id), guildid) for id in db['ratings'].keys()}
            return sorted(ratings.items(), key=lambda x: (x[1].mu, -x[1].sigma), reverse=True)
        return None

@bot.event
async def on_ready():
    print('Logged in as {0.user}'.format(bot))

bot.load_extension("valorant_cog")
bot.run(os.getenv('TOKEN'))