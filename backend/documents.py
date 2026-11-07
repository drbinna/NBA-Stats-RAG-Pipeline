"""Turns structured rows into the text passages that get embedded.

Each passage repeats facts in the forms people ask about them: several date
formats, full team names and abbreviations, and tags for notable games.
"""
from datetime import date

from backend.teams import TEAMS, full_name


def long_date(d: date) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}"


def short_date(d: date) -> str:
    return f"{d.month}/{d.day}/{d.year}"


def date_tags(d: date, season_opener: bool) -> list:
    tags = []
    if (d.month, d.day) == (12, 25):
        tags.append("Christmas Day game")
    if season_opener:
        tags.append("season opener")
    return tags


def player_line_text(r: dict) -> str:
    d = r["game_date"]
    venue = "home" if r["home"] else "away"
    result = "win" if r["team_points"] > r["opp_points"] else "loss"
    parts = [f"{r['pts']} points", f"{r['reb']} rebounds", f"{r['ast']} assists",
             f"{r['stl']} steals", f"{r['blk']} blocks", f"{r['tov']} turnovers",
             f"{r['fgm']}-{r['fga']} FG", f"{r['fg3m']}-{r['fg3a']} 3PT", f"{r['ftm']}-{r['fta']} FT",
             f"{round(r['minutes'])} minutes", f"{r['plus_minus']:+d} plus-minus"]
    tags = date_tags(d, r.get("season_opener", False))
    tens = sum(v >= 10 for v in (r["pts"], r["reb"], r["ast"], r["stl"], r["blk"]))
    if tens >= 3:
        tags.append("triple-double")
    elif tens == 2:
        tags.append("double-double")
    if r["pts"] >= 50:
        tags.append("50-point game")
    elif r["pts"] >= 40:
        tags.append("40-point game")
    text = (f"{r['player_name']} ({r['team']}, {full_name(r['team'])}) vs {full_name(r['opponent'])} ({r['opponent']}), "
            f"{long_date(d)} ({short_date(d)}, {d.isoformat()}), {r['season']} season, {venue} {result} "
            f"{r['team_points']}-{r['opp_points']}: " + ", ".join(parts) + ".")
    return text + (" " + "; ".join(tags) + "." if tags else "")


def game_text(g: dict) -> str:
    d = g["game_date"]
    home, away = g["home_team"], g["away_team"]
    winner, loser = (home, away) if g["home_points"] > g["away_points"] else (away, home)
    margin = abs(g["home_points"] - g["away_points"])
    city = TEAMS[home][0]
    tags = date_tags(d, g.get("season_opener", False))
    if g.get("overtime"):
        tags.append("overtime")
    scorers = ", ".join(f"{p} {pts} ({t})" for p, pts, t in g["top_scorers"])
    text = (f"Final score: {full_name(home)} ({home}) {g['home_points']}, {full_name(away)} ({away}) {g['away_points']}. "
            f"Played {long_date(d)} ({short_date(d)}, {d.isoformat()}) in {city}, {g['season']} regular season. "
            f"The {TEAMS[winner][1]} beat the {TEAMS[loser][1]} by {margin}. Leading scorers: {scorers}.")
    return text + (" " + "; ".join(tags) + "." if tags else "")
