from typing import Iterable
import trueskill as ts

def rate_with_round_score(winners:Iterable, losers:Iterable, winner_score:int, loser_score:int, factor=1):
    score_diff = winner_score - loser_score
    weight_change = 1 + (score_diff/(winner_score)-0.5)*factor
    print(weight_change)
    w_after, l_after = ts.rate([winners, losers], ranks=[0, 1])
    w_diffs = [w_after[i].mu - winners[i].mu for i in range(len(winners))]
    l_diffs = [l_after[i].mu - losers[i].mu for i in range(len(losers))]
    w_after = [ts.Rating(mu=winners[i].mu + w_diffs[i]*weight_change, sigma=w_after[i].sigma) for i in range(len(winners))]
    l_after = [ts.Rating(mu=losers[i].mu + l_diffs[i]*weight_change, sigma=l_after[i].sigma) for i in range(len(losers))]
    return w_after, l_after
    