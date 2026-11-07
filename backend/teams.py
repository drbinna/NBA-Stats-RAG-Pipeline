"""The 30 NBA teams, keyed by the abbreviations used in the source data."""

TEAMS = {
    "ATL": ("Atlanta", "Hawks"), "BKN": ("Brooklyn", "Nets"), "BOS": ("Boston", "Celtics"),
    "CHA": ("Charlotte", "Hornets"), "CHI": ("Chicago", "Bulls"), "CLE": ("Cleveland", "Cavaliers"),
    "DAL": ("Dallas", "Mavericks"), "DEN": ("Denver", "Nuggets"), "DET": ("Detroit", "Pistons"),
    "GSW": ("Golden State", "Warriors"), "HOU": ("Houston", "Rockets"), "IND": ("Indiana", "Pacers"),
    "LAC": ("LA", "Clippers"), "LAL": ("Los Angeles", "Lakers"), "MEM": ("Memphis", "Grizzlies"),
    "MIA": ("Miami", "Heat"), "MIL": ("Milwaukee", "Bucks"), "MIN": ("Minnesota", "Timberwolves"),
    "NOP": ("New Orleans", "Pelicans"), "NYK": ("New York", "Knicks"), "OKC": ("Oklahoma City", "Thunder"),
    "ORL": ("Orlando", "Magic"), "PHI": ("Philadelphia", "76ers"), "PHX": ("Phoenix", "Suns"),
    "POR": ("Portland", "Trail Blazers"), "SAC": ("Sacramento", "Kings"), "SAN": ("San Antonio", "Spurs"),
    "TOR": ("Toronto", "Raptors"), "UTA": ("Utah", "Jazz"), "WAS": ("Washington", "Wizards"),
}

# Other ways people refer to a team. Cities shared by two teams (LA, New York) are left out.
TEAM_ALIASES = {
    "SAS": "SAN", "GS": "GSW", "NO": "NOP", "NY": "NYK", "PHO": "PHX", "BRK": "BKN", "UTAH": "UTA",
    "sixers": "PHI", "blazers": "POR", "wolves": "MIN", "cavs": "CLE", "mavs": "DAL", "dubs": "GSW",
    "okc": "OKC", "golden state": "GSW", "san antonio": "SAN", "oklahoma city": "OKC", "new orleans": "NOP",
}


def full_name(abbr: str) -> str:
    city, name = TEAMS[abbr]
    return f"{city} {name}"
