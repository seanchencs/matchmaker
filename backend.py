import os
import random
import time
from datetime import datetime
from math import isclose

import trueskill as ts
from sqlitedict import SqliteDict

from CustomTrueSkill import rate_with_round_score, win_probability

myid = 263745246821744640

# TrueSkill DB helper functions


def delete_db(guildid):
    guildid = str(guildid)
    os.remove(f'{guildid}.db')


def db_string(guildid):
    output = []
    guildid = str(guildid)
    with SqliteDict(str(guildid)+'.db') as db:
        for key in db.keys():
            output.append(key)
            output.append(str(db[key]))
    return ' '.join(output)


def get_playerlist(guildid):
    """Get list of all userids in guild with ratings."""
    players = []
    with SqliteDict(str(guildid)+'.db') as db:
        if 'ratings' not in db:
            db['ratings'] = {}
        players = [uid for uid in db['ratings']]
    return players


def get_rating(userid, guildid):
    """Returns the TrueSkill rating of a discord user. Will initialize skill if none is found."""
    start = time.time()
    userid = str(userid)
    guildid = str(guildid)
    rating = None

    # check db
    with SqliteDict(str(guildid)+'.db', autocommit=True) as db:
        if 'ratings' not in db:
            db['ratings'] = {}
        ratings = db['ratings']
        if userid in ratings:
            mu, sigma = ratings[userid]
            current_rating = ts.Rating(float(mu), float(sigma))
            rating = ts.Rating(current_rating.mu, min(
                current_rating.sigma + get_decay(userid, guildid), ts.global_env().sigma))
        else:
            rating = ts.Rating()
            ratings[userid] = rating.mu, rating.sigma

    print(
        f'[{guildid}]: get_skill for {userid} in {round(1000*(time.time()-start), 2)}ms')
    return rating


def get_ratings(users, guildid):
    """Returns dictionary of id to rating for users."""
    start = time.time()

    output = {}
    current_time = datetime.now()
    with SqliteDict(str(guildid)+'.db', autocommit=True) as db:
        if 'ratings' not in db:
            db['ratings'] = {}
        ratings = db['ratings']
        for userid in users:
            userid = str(userid)
            if userid in ratings:
                mu, sigma = ratings[userid]
                current_rating = ts.Rating(float(mu), float(sigma))
                rating = ts.Rating(current_rating.mu, min(current_rating.sigma + get_decay(
                    userid, guildid, current_time=current_time), ts.global_env().sigma))
                print(
                    f'[{guildid}]: get_skill for {userid} in {round(1000*(time.time()-start), 2)}ms')
                output[userid] = rating
            else:
                new_rating = ts.Rating()
                ratings[userid] = new_rating.mu, new_rating.sigma
                output[userid] = new_rating
    print(f'[{guildid}]: get_skills for {len(users)} users in {round(1000*(time.time()-start), 2)}ms')
    return output


def get_decay(userid, guildid, current_time=None):
    """Returns the amount of decay for a user, based on time since last match."""
    start = time.time()
    userid, guildid = str(userid), str(guildid)
    if not current_time:
        current_time = datetime.now()
    last_match = time_since_last_match(
        userid, guildid, current_time=current_time)
    if last_match:
        print(
            f'[{guildid}]: get_decay for {userid} in {round(1000*(time.time()-start), 2)}ms')
        return 0.001 * ((last_match/50000) ** 2)
    else:
        print(
            f'[{guildid}]: get_decay for {userid} in {round(1000*(time.time()-start), 2)}ms')
        return 0


def set_rating(userid, rating, guildid):
    """Set the rating of a user."""
    start = time.time()
    userid = str(userid)
    guildid = str(guildid)
    # write to shelve persistent db
    with SqliteDict(str(guildid)+'.db') as db:
        if 'ratings' not in db:
            db['ratings'] = {}
        ratings = db['ratings']
        ratings[userid] = rating.mu, rating.sigma
        db['ratings'] = ratings
        db.commit()
    print(f'[{guildid}]: set_rating for {userid} in {round(1000*(time.time()-start), 2)}ms')


def set_ratings(user_ratings, guildid):
    """Set the rating of multiple users."""
    start = time.time()
    guildid = str(guildid)
    with SqliteDict(str(guildid)+'.db') as db:
        if 'ratings' not in db:
            db['ratings'] = {}
        ratings = db['ratings']
        for userid in user_ratings:
            ratings[str(userid)
                    ] = user_ratings[userid].mu, user_ratings[userid].sigma
        db['ratings'] = ratings
        db.commit()
    print(f'[{guildid}]: set_ratings for {len(user_ratings)} users in {round(1000*(time.time()-start), 2)}ms')


def record_result(team_a, team_b, team_a_score, team_b_score, guildid):
    """Updates the TrueSkill ratings given a result."""
    start = time.time()
    team_a_ratings = get_ratings(team_a, guildid)
    team_b_ratings = get_ratings(team_b, guildid)
    if team_a_score > team_b_score:
        team_a_new, team_b_new = rate_with_round_score(
            team_a_ratings, team_b_ratings, team_a_score, team_b_score)
    else:
        team_b_new, team_a_new = rate_with_round_score(
            team_b_ratings, team_a_ratings, team_b_score, team_a_score)
    set_ratings(team_a_new, guildid)
    set_ratings(team_b_new, guildid)

    # record in match history
    with SqliteDict(str(guildid)+'.db') as db:
        if 'history' not in db:
            db['history'] = []
        history = db['history']
        history.append({'team_a': team_a_new, 'team_b': team_b_new, 'team_a_score': team_a_score,
                       'team_b_score': team_b_score, 'time': datetime.now(), 'old_ratings': {**team_a_ratings, **team_b_ratings}})
        db['history'] = history
        db.commit()

    print(f'[{guildid}]: record_result in {round(1000*(time.time()-start), 2)}ms')
    return team_a_ratings, team_b_ratings, team_a_new, team_b_new


def make_teams(players, guildid, pool=25):
    """Make teams based on rating."""
    start = time.time()
    guildid = str(guildid)
    player_ratings = get_ratings(players, guildid)
    team_a = team_b = []
    best_quality = 0.0

    for _ in range(pool):
        random.shuffle(players)
        team_size = len(players) // 2
        t1 = {str(uid): player_ratings[str(uid)]
              for uid in players[:team_size]}
        t2 = {str(uid): player_ratings[str(uid)]
              for uid in players[team_size:]}
        quality = ts.quality([t1, t2])
        if quality > best_quality:
            team_a = list(t1.keys())
            team_b = list(t2.keys())
            best_quality = quality

    # sort teams by rating
    team_a, team_b = sorted(team_a, key=lambda x: player_ratings[x]), sorted(
        team_b, key=lambda x: player_ratings[x])
    a_win = win_probability([player_ratings[str(uid)] for uid in team_a], [
                            player_ratings[str(uid)] for uid in team_b])
    b_win = win_probability([player_ratings[str(uid)] for uid in team_b], [
                            player_ratings[str(uid)] for uid in team_a])
    print(f'[{guildid}]: team_1: {a_win*100: .2f}%, team_2: {b_win*100: .2f}%, draw: {(1-a_win-b_win)*100: .2f}%')
    print(f'[{guildid}]: make_teams for in {1000*(time.time()-start): .2f}ms')
    return team_a, team_b, best_quality


def get_win_loss(userid, guildid):
    """Get win/loss counts for a user."""
    start = time.time()
    userid = str(userid)
    guildid = str(guildid)
    wins, losses = 0, 0
    with SqliteDict(str(guildid)+'.db') as db:
        if 'history' in db:
            for match in db['history']:
                if userid in match['team_a']:
                    if match['team_a_score'] > match['team_b_score']:
                        wins += 1
                    else:
                        losses += 1
                elif userid in match['team_b']:
                    if match['team_b_score'] > match['team_a_score']:
                        wins += 1
                    else:
                        losses += 1
    print(f'[{guildid}]: get_win_loss for {userid} in {round(1000*(time.time()-start), 2)}ms')
    return wins, losses


def time_since_last_match(userid, guildid, current_time=datetime.now()):
    """Returns the time in seconds since user's last match."""
    userid, guildid = str(userid), str(guildid)
    output = None
    with SqliteDict(guildid+'.db') as db:
        if 'history' in db:
            history = db['history']
            for _, match in enumerate(reversed(history)):
                if userid in match['team_a'] or userid in match['team_b']:
                    output = (current_time-match['time']).total_seconds()
                    break
    print(output)
    return output


def get_history(guildid, userid=None):
    """Fetch list of matches for guild or specified user in guild."""
    with SqliteDict(str(guildid)+'.db') as db:
        if 'history' not in db or not db['history']:
            history = None
        elif userid:
            history = list(filter(lambda x: (userid) in x['team_a'] or (
                userid) in x['team_b'], db['history']))
            history.reverse()
        else:
            # guild-wide match history
            history = db['history']
            history.reverse()
    if not history:
        return None
    return history


def get_past_ratings(userid, guildid, pad=False):
    """Get a list of past ratings(mu) for a user."""
    start = time.time()
    guildid = str(guildid)
    past_ratings = []
    with SqliteDict(str(guildid)+'.db') as db:
        if 'history' in db:
            if pad:
                history = db['history']
            else:
                history = list(filter(lambda x: (userid) in x['team_a'] or (
                    userid) in x['team_b'], db['history']))
            for match in history:
                if userid in match['old_ratings']:
                    past_ratings.append(match['old_ratings'][userid].mu)
                else:
                    if past_ratings:
                        past_ratings.append(past_ratings[-1])
                    else:
                        past_ratings.append(ts.global_env().mu)
            past_ratings.append(get_rating(userid, guildid).mu)
    print(f'[{guildid}]: get_past_ratings for {userid} in {round(1000*(time.time()-start), 2)}ms')
    return past_ratings


def get_ranks(players, guildid, metric='exposure'):
    """Get the leaderboard position of a list of players. Returns a {userid: position} dict."""
    if metric == 'exposure':
        leaderboard = get_leaderboard_by_exposure(guildid)
    elif metric == 'mean':
        leaderboard = get_leaderboard(guildid)
    if leaderboard:
        rank = 0
        last = 0
        last_rank = 0
        output = {}
        for item in leaderboard:
            rank += 1
            if metric == 'exposure' and not isclose(ts.expose(item[1]), last, abs_tol=0.0001):
                last = ts.expose(item[1])
                last_rank = rank
            elif metric == 'mean' and not isclose(item[1].mu, last, abs_tol=0.0001):
                last = item[1].mu
                last_rank = rank
            if item[0] in players:
                output[item[0]] = last_rank
        return output


def get_leaderboard(guildid):
    """Gets list of userids and TrueSkill ratings, sorted by current rating."""
    start = time.time()
    guildid = str(guildid)
    with SqliteDict(str(guildid)+'.db') as db:
        if 'ratings' in db:
            ratings = {str(id): get_rating(str(id), guildid)
                       for id in db['ratings'].keys()}
            ratings = {id: ratings[id]
                       for id in ratings if ratings[id] != ts.Rating()}
            leaderboard = sorted(ratings.items(), key=lambda x: (
                x[1].mu, -x[1].sigma), reverse=True)
            print(
                f'[{guildid}]: get_leaderboard in {round(1000*(time.time()-start), 2)}ms')
            return leaderboard
    print(f'[{guildid}]: get_leaderboard in {round(1000*(time.time()-start), 2)}ms')
    return None


def get_leaderboard_by_exposure(guildid):
    """Get leaderboard sorted by exposure (see trueskill.org for more info)."""
    start = time.time()
    guildid = str(guildid)
    ids = get_playerlist(guildid)
    if not ids:
        print(
            f'[{guildid}]: get_leaderboard_by_exposure in {round(1000*(time.time()-start), 2)}ms')
        return None
    ratings = get_ratings(ids, guildid)
    ratings = {id: ratings[id] for id in ratings if ratings[id] != ts.Rating()}
    leaderboard = sorted(
        ratings.items(), key=lambda x: ts.expose(x[1]), reverse=True)
    print(f'[{guildid}]: get_leaderboard_by_exposure in {round(1000*(time.time()-start), 2)}ms')
    return leaderboard


def undo_last_match(guildid):
    """Rollback to before the last recorded result."""
    guildid = str(guildid)
    match = None
    with SqliteDict(guildid+'.db') as db:
        if 'history' not in db or not db['history']:
            print('history not found in db')
            return None
        history = db['history']
        match = history[-1]
        # delete from match history
        del history[-1]
        db['history'] = history
        db.commit()
    for player in match['team_a']:
        set_rating(str(player), match['old_ratings'][player], guildid)
    for player in match['team_b']:
        set_rating(str(player), match['old_ratings'][player], guildid)
    return match
