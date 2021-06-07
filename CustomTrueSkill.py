from typing import Iterable
import trueskill as ts

def rate_with_round_score(winners:Iterable, losers:Iterable, winner_score:int, loser_score:int, factor=1):
    score_diff = winner_score - loser_score
    weight_change = (score_diff/winner_score)*factor
    w_temp, l_temp = ts.rate([winners, losers], ranks=[0, 1], weights=[[1 for i in winners], [1 for i in losers]])
    w_after, l_after = ts.rate([winners, losers], ranks=[0, 1], weights=[[1 for i in winners], [0.5+weight_change for i in losers]])
    w_after = [ts.Rating(w_after[i].mu, w_temp[i].sigma) for i in range(len(w_after))]
    l_after = [ts.Rating(l_after[i].mu, l_temp[i].sigma) for i in range(len(l_after))]
    return w_after, l_after