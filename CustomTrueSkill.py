from typing import Dict, List, Tuple
import trueskill as ts

def rate_with_round_score(winners, losers, winner_score: int, loser_score: int, factor=0.7):
    """Modified verison of TrueSkill rate for use in N v M matches with margin of victory."""
    score_diff = winner_score - loser_score
    weight_change = 1 + (score_diff/(winner_score)-0.5)*factor
    w_after, l_after = ts.rate([winners, losers], ranks=[0, 1])
    w_diffs = {id : w_after[id].mu - winners[id].mu for id in winners}
    l_diffs = {id : l_after[id].mu - losers[id].mu for id in losers}
    w_after = {id : ts.Rating(mu=winners[id].mu + w_diffs[id]*weight_change, sigma=w_after[id].sigma) for id in winners}
    l_after = {id : ts.Rating(mu=losers[id].mu + l_diffs[id]*weight_change, sigma=l_after[id].sigma) for id in losers}
    return w_after, l_after
