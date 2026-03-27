import csv
import io
import requests

from .projections import normalize_name

RIGHTS_SHEET_URL = (
    'https://docs.google.com/spreadsheets/d/'
    '1rC7olwPSGzjxLLuVIuO4zpYVwMq4MtMMK3R5Kb08UkI/export?format=csv&gid=0'
)

_KEEPER_SHEET_BASE = (
    'https://docs.google.com/spreadsheets/d/'
    '1FD03mBKeG9HI16wyaLyPuxzQdj_6puMVoufCCzNKH8c/export?format=csv&gid='
)
KEEPER_HITTERS_URL = _KEEPER_SHEET_BASE + '2075427949'
KEEPER_PITCHERS_URL = _KEEPER_SHEET_BASE + '1364743628'

MANAGER_TO_TEAM = {
    'Alan':   'Hello',
    'Andy':   'Omar Manaea',
    'Billek': "Paddy's Pub",
    'Chris':  "Miller Lite's",
    'Drew':   "Ms. Dean's Lean",
    'Ethan':  "Hailey's Dad's Team",
    'Jared':  "Alan's Liang",
    'Jason':  'The Bigots',
    'Jon':    'Dangerous Nights Crew',
    'Nick':   'Shmohawks',
    'Ralph':  'CPLL All-Stars',
    'Phelan': 'Boogie Down Boyz',
}


def fetch_rights_players():
    """Fetch rights players from Google Sheet.

    Returns:
        dict: {team_name: [player_name, ...]}
    """
    resp = requests.get(RIGHTS_SHEET_URL, allow_redirects=True)
    resp.raise_for_status()

    rows = list(csv.reader(io.StringIO(resp.text)))

    # Row 0: manager first names
    # Row 1: empty
    # Row 2: "Rights" labels
    # Rows 3–6: up to 4 player names per manager
    managers = rows[0]
    result = {}

    for i, manager in enumerate(managers):
        manager = manager.strip()
        team = MANAGER_TO_TEAM.get(manager)
        if not team:
            continue
        players = []
        for row in rows[3:7]:
            if i < len(row) and row[i].strip():
                players.append(row[i].strip())
        result[team] = players

    return result


def fetch_keeper_costs():
    """Fetch keeper first-year data from hitters + pitchers tabs and calculate costs.

    Cost formula: MIN(60, (currentYear - firstYear)² / 2)
    The header row's first cell contains the current year (e.g. "2026").

    Returns:
        dict: {normalized_player_name: cost_float}
    """
    costs = {}
    for url in (KEEPER_HITTERS_URL, KEEPER_PITCHERS_URL):
        resp = requests.get(url, allow_redirects=True)
        resp.raise_for_status()
        rows = list(csv.reader(io.StringIO(resp.text)))
        if not rows:
            continue
        try:
            current_year = int(rows[0][0])
        except (ValueError, IndexError):
            continue
        next_year = current_year + 1
        for row in rows[1:]:
            if len(row) < 3 or not row[0].strip():
                continue
            name = row[0].strip()
            try:
                fir_yr = int(float(row[2].strip()))
            except ValueError:
                continue
            cost = min(60.0, (next_year - fir_yr) ** 2 / 2)
            costs[normalize_name(name)] = cost
    return costs
