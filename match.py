from datetime import datetime
import discord
from typing import Dict, Optional, Set
from backend import make_teams, record_result


class Match:
    def __init__(
        self,
        players: Optional[Set[discord.User]],
        guild_id: int,
        db_match: Optional[Dict] = None,
    ):
        """Initialize and matchmake an object representing a single match.

        Args:
            players (Set[discord.User]): players in the match.
            guild_id (int): guild id of the match.
            db_match (Dict, optional): match history dictionary from db. Defaults to None.
        """
        if db_match:
            self.load_match(db_match, guild_id)
        else:
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
            return f"{self.team_a_score} - {self.team_b_score}"
        return f"{len(self.team_a)}v{len(self.team_b)} match @ {self.start_time.strftime(time_format)}"

    def get_summary(self):
        """Get summary of match result with player @s. Returns None if no result."""
        if self.team_a_score or self.team_b_score:
            return f"{','.join([f'<@!{id}>' for id in self.team_a])} {self.team_a_score}-{self.team_b_score} {','.join([f'<@!{id}>' for id in self.team_b])}"
        return None

    def get_time_string(self):
        """Get formatted full timestamp for match."""
        time_format = "%A, %b %d @ %I:%M %p"
        return self.start_time.strftime(time_format)

    def load_match(self, match: Dict, guild_id: int):
        """Load a match from db dict.

        Args:
            match (Dict): match history dictionary from db.
        """
        self.guild_id = guild_id
        self.start_time = match["time"]
        self.team_a = [id for id in match["team_a"]]
        self.team_b = [id for id in match["team_b"]]
        self.team_a_new, self.team_b_new = match["team_a"], match["team_b"]
        self.team_a_old = {k: match["old_ratings"][k] for k in self.team_a_new}
        self.team_b_old = {k: match["old_ratings"][k] for k in self.team_b_new}
        self.team_a_score, self.team_b_score = (
            match["team_a_score"],
            match["team_b_score"],
        )
