import logging
import os
import random
import shelve
from datetime import datetime
import time

import discord
import dotenv
import trueskill as ts
from discord.ext import commands
from discord_slash import SlashCommand

from CustomTrueSkill import rate_with_round_score

# load env
if os.path.isfile('.env'):
    dotenv.load_dotenv('.env')

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
def delete_db(guildid):
    os.remove(f'{guildid}.db')
    if guildid in ratings_cache:
        del ratings_cache[guildid]

def db_string(guildid):
    output = []
    with shelve.open(str(guildid)) as db:
        for key in db.keys():
            output.append(key)
            output.append(str(db[key]))
    return ' '.join(output)

def get_skill(userid, guildid):
    """Returns the TrueSkill rating of a discord user. Will initialize skill if none is found."""
    start = time.time()
    userid = str(userid)
    guildid = str(guildid)

    # check cache first
    if guildid not in ratings_cache:
            ratings_cache[guildid] = {}
    if userid in ratings_cache[guildid]:
        print(f'[{guildid}]: get_skill for {userid} in {round(1000*(time.time()-start), 2)}ms')
        return ratings_cache[guildid][userid]
    
    print(f'Cache Miss: guildid = {guildid} userid = {userid}')

    # check db
    with shelve.open(str(guildid), writeback=True) as db:
        if 'ratings' not in db:
            db['ratings'] = {}
        ratings = db['ratings']
        if userid in ratings:
            mu, sigma = ratings[userid]
            print(f'[{guildid}]: get_skill for {userid} in {round(1000*(time.time()-start), 2)}ms')
            return ts.Rating(float(mu), float(sigma))
        new_rating = ts.Rating()
        # write to cache and db
        ratings_cache[guildid][userid] = new_rating
        ratings[userid] = new_rating.mu, new_rating.sigma
    
    print(f'[{guildid}]: get_skill for {userid} in {round(1000*(time.time()-start), 2)}ms')
    return new_rating

def set_rating(userid, rating, guildid):
    """Set the rating of a user."""
    start = time.time()
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
    print(f'[{guildid}]: set_skill for {userid} in {round(1000*(time.time()-start), 2)}ms')

def record_result(attackers, defenders, attacker_score, defender_score, guildid):
    """Updates the TrueSkill ratings given a result."""
    start = time.time()
    attacker_ratings = {str(uid) : get_skill(str(uid), guildid) for uid in attackers}
    defender_ratings = {str(uid) : get_skill(str(uid), guildid) for uid in defenders}
    if attacker_score > defender_score:
        attackers_new, defenders_new = rate_with_round_score(attacker_ratings, defender_ratings, attacker_score, defender_score)
    else:
        defenders_new, attackers_new = rate_with_round_score(defender_ratings, attacker_ratings, defender_score, attacker_score)
    with shelve.open(str(guildid), writeback=True) as db:
        ratings = db['ratings']
        for uid in attackers:
            ratings_cache[str(guildid)][str(uid)] = attackers_new[str(uid)]
            ratings[str(uid)] = attackers_new[str(uid)].mu, attackers_new[str(uid)].sigma
        for uid in defenders:
            ratings_cache[str(guildid)][str(uid)] = defenders_new[str(uid)]
            ratings[str(uid)] = defenders_new[str(uid)].mu, defenders_new[str(uid)].sigma
        # record in match history
        if 'history' not in db:
            db['history'] = []
        history = db['history']
        history.append({'attackers': attackers_new, 'defenders': defenders_new, 'attacker_score': attacker_score, 'defender_score': defender_score, 'time': datetime.now(), 'old_ratings': {**attacker_ratings, **defender_ratings}})
    print(f'[{guildid}]: record_result in {round(1000*(time.time()-start), 2)}ms')
    return attacker_ratings, defender_ratings, attackers_new, defenders_new

def make_teams(players, guildid, pool=10):
    """Make teams based on rating."""
    start = time.time()
    player_ratings = {str(uid) : get_skill(str(uid), guildid) for uid in players}
    t = ct = []
    best_quality = 0.0
    for _ in range(pool):
        random.shuffle(players)
        team_size = len(players) // 2
        t1 = {str(uid) : player_ratings[str(uid)] for uid in players[:team_size]}
        t2 = {str(uid) : player_ratings[str(uid)] for uid in players[team_size:]}
        quality = ts.quality([t1, t2])
        if quality > best_quality:
            t = list(t1.keys())
            ct = list(t2.keys())
            best_quality = quality
    print(f'[{guildid}]: make_teams for in {round(1000*(time.time()-start), 2)}ms')
    return t, ct, best_quality

def get_win_loss(userid, guildid):
    """Get win/loss counts for a user."""
    start = time.time()
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
    print(f'[{guildid}]: get_win_loss for {userid} in {round(1000*(time.time()-start), 2)}ms')
    return wins, losses

def get_past_ratings(userid, guildid, pad=False):
    """Get a list of past ratings(mu) for a user."""
    start = time.time()
    past_ratings = []
    with shelve.open(str(guildid)) as db:
        if 'history' in db:
            if pad:
                history = db['history']
            else:
                history = list(filter(lambda x: (userid) in x['attackers'] or (userid) in x['defenders'], db['history']))
            for match in history:
                if userid in match['old_ratings']:
                    past_ratings.append(match['old_ratings'][userid].mu)
                else:
                    if past_ratings:
                        past_ratings.append(past_ratings[-1])
                    else:
                        past_ratings.append(ts.global_env().mu)
            past_ratings.append(get_skill(userid, guildid).mu)
    print(f'[{guildid}]: get_past_ratings for {userid} in {round(1000*(time.time()-start), 2)}ms')
    return past_ratings

def get_leaderboard(guildid):
    """Gets list of userids and TrueSkill ratings, sorted by current rating."""
    start = time.time()
    with shelve.open(str(guildid)) as db:
        if 'ratings' in db:
            ratings = {str(id) : get_skill(str(id), guildid) for id in db['ratings'].keys()}
            print(f'[{guildid}]: get_leaderboard in {round(1000*(time.time()-start), 2)}ms')
            return sorted(ratings.items(), key=lambda x: (x[1].mu, -x[1].sigma), reverse=True)
        print(f'[{guildid}]: get_leaderboard in {round(1000*(time.time()-start), 2)}ms')
        return None

def get_leaderboard_by_exposure(guildid):
    """Get leaderboard sorted by exposure (see trueskill.org for more info)."""
    start = time.time()
    with shelve.open(str(guildid)) as db:
        if 'ratings' in db:
            ratings = {str(id) : get_skill(str(id), guildid) for id in db['ratings'].keys()}
            print(f'[{guildid}]: get_leaderboard_by_exposure in {round(1000*(time.time()-start), 2)}ms')
            return sorted(ratings.items(), key=lambda x: ts.expose(x[1]), reverse=True)
        print(f'[{guildid}]: get_leaderboard_by_exposure in {round(1000*(time.time()-start), 2)}ms')
        return None

@bot.event
async def on_ready():
    print('Logged in as {0.user}'.format(bot))

bot.load_extension('test_cog')
bot.load_extension('valorant_cog')
bot.run(os.getenv('TOKEN'))
