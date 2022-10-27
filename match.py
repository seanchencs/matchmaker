from datetime import datetime
import discord
from typing import Set
from CustomTrueSkill import win_probability
from backend import make_teams, record_result


class Match:
    def __init__(self, players: Set[discord.User], guild_id: int):
        self.players = players
        self.guild_id = guild_id
        player_ids = [player.id for player in self.players]
        (
            self.team_a,
            self.team_b,
            self.quality,
            self.a_win_prob,
            self.b_win_prob,
        ) = make_teams(player_ids, self.guild_id)
        self.team_a_score = 0
        self.team_b_score = 0
        self.start_time = datetime.now()

    def record_result(self, a_score: int, b_score: int):
        """Record winner of match."""
        self.team_a_score = a_score
        self.team_b_score = b_score
        (
            self.team_a_old,
            self.team_b_old,
            self.team_a_new,
            self.team_b_new,
        ) = record_result(self.team_a, self.team_b, a_score, b_score, self.guild_id)

    def get_title(self):
        """Get formatted title for match."""
        time_format = "%I:%M %p"
        if self.team_a_score or self.team_b_score:
            return f"{self.team_a_score}-{self.team_b_score} @ {self.start_time.strftime(time_format)}"
        return f"{len(self.team_a)}v{len(self.team_b)} match @ {self.start_time.strftime(time_format)}"

    def get_summary(self):
        if self.team_a_score or self.team_b_score:
            return f"{','.join([f'<@!{id}>' for id in self.team_a])} {self.team_a_score}-{self.team_b_score} {','.join([f'<@!{id}>' for id in self.team_b])}"
        return None
