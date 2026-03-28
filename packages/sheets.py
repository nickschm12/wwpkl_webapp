import csv
import io
import re
import requests
from datetime import date, datetime

from dateutil import parser as dateparser
from .projections import normalize_name

RIGHTS_SHEET_URL = (
    'https://docs.google.com/spreadsheets/d/'
    '1rC7olwPSGzjxLLuVIuO4zpYVwMq4MtMMK3R5Kb08UkI/export?format=csv&gid=0'
)
TRANSACTIONS_SHEET_URL = (
    'https://docs.google.com/spreadsheets/d/'
    '1rC7olwPSGzjxLLuVIuO4zpYVwMq4MtMMK3R5Kb08UkI/export?format=csv&gid=1513498000'
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


def _normalize_item(text):
    """Normalize common transaction item phrases."""
    return re.sub(r'\ba keeper spot\b', 'Keeper Spot', text, flags=re.IGNORECASE)


def _parse_transaction(raw_date, description, year):
    """Parse a raw transaction row into a structured dict."""
    # Parse date
    try:
        parsed_date = dateparser.parse(raw_date, default=datetime(int(year), 1, 1))
        date_str = parsed_date.strftime('%-m/%-d/%Y')
        is_preseason = parsed_date.date() < date(int(year), 3, 25)
    except Exception:
        parsed_date = None
        date_str = raw_date
        is_preseason = False

    # Parse structure: "[Manager] sends/trades [stuff] to [Manager] for [stuff]"
    pattern = r'^(\w+)\s+(?:sends|trades)\s+(.+?)\s+to\s+(\w+)\s+for\s+(.+)$'
    m = re.match(pattern, description, re.IGNORECASE)
    if m and m.group(1) in MANAGER_TO_TEAM and m.group(3) in MANAGER_TO_TEAM:
        a_name, a_sends, b_name, b_sends = m.groups()
        a_sends_norm = _normalize_item(a_sends.strip())
        b_sends_norm = _normalize_item(b_sends.strip())
        a_dollars = sum(int(x) for x in re.findall(r'\$(\d+)', a_sends))
        b_dollars = sum(int(x) for x in re.findall(r'\$(\d+)', b_sends))
        a_keeper_spots = len(re.findall(r'Keeper Spot', a_sends_norm, re.IGNORECASE))
        b_keeper_spots = len(re.findall(r'Keeper Spot', b_sends_norm, re.IGNORECASE))
        return {
            'date': date_str,
            'parsed_date': parsed_date,
            'is_preseason': is_preseason,
            'party_a': MANAGER_TO_TEAM[a_name],
            'party_b': MANAGER_TO_TEAM[b_name],
            'a_sends': a_sends_norm,
            'b_sends': b_sends_norm,
            'a_dollars': a_dollars,
            'b_dollars': b_dollars,
            'a_keeper_spots': a_keeper_spots,
            'b_keeper_spots': b_keeper_spots,
            'raw': description,
        }

    # Fallback: unstructured
    return {
        'date': date_str,
        'parsed_date': parsed_date,
        'is_preseason': is_preseason,
        'party_a': None, 'party_b': None,
        'a_sends': None, 'b_sends': None,
        'a_dollars': 0, 'b_dollars': 0,
        'raw': description,
    }


def fetch_transactions():
    """Fetch and parse transactions from Google Sheet.

    Returns:
        list: [{year, transactions: [parsed_txn]}] sorted newest first
    """
    resp = requests.get(TRANSACTIONS_SHEET_URL, allow_redirects=True)
    resp.raise_for_status()
    rows = list(csv.reader(io.StringIO(resp.text)))

    sections = {}
    current_year = None
    for row in rows[1:]:  # skip header
        if not row or not row[0].strip():
            continue
        cell = row[0].strip()
        if cell.isdigit() and len(cell) == 4:
            current_year = cell
            continue
        if current_year is None:
            continue
        description = row[1].strip() if len(row) > 1 else ''
        if not description:
            continue
        sections.setdefault(current_year, []).append(
            _parse_transaction(cell, description, current_year)
        )

    return [
        {'year': year, 'transactions': txns}
        for year, txns in sorted(sections.items(), reverse=True)
    ]


def compute_keeper_adjustments(transactions_by_year, year):
    """Compute net keeper spot adjustments per team for in-season trades in given year.

    Returns:
        dict: {team_name: net_keeper_spot_change}
    """
    section = next((s for s in transactions_by_year if s['year'] == str(year)), None)
    if not section:
        return {}

    adjustments = {}
    for txn in section['transactions']:
        if txn['is_preseason'] or not txn['party_a']:
            continue
        a, b = txn['party_a'], txn['party_b']
        if txn['a_keeper_spots']:
            adjustments[a] = adjustments.get(a, 0) - txn['a_keeper_spots']
            adjustments[b] = adjustments.get(b, 0) + txn['a_keeper_spots']
        if txn['b_keeper_spots']:
            adjustments[b] = adjustments.get(b, 0) - txn['b_keeper_spots']
            adjustments[a] = adjustments.get(a, 0) + txn['b_keeper_spots']

    return adjustments


def compute_budget_adjustments(transactions_by_year, year):
    """Compute net dollar adjustments per team for in-season trades in given year.

    Returns:
        dict: {team_name: net_dollar_change}  positive = received, negative = sent
    """
    section = next((s for s in transactions_by_year if s['year'] == str(year)), None)
    if not section:
        return {}

    adjustments = {}
    for txn in section['transactions']:
        if txn['is_preseason'] or not txn['party_a']:
            continue
        a, b = txn['party_a'], txn['party_b']
        # party_a sent a_dollars to party_b
        if txn['a_dollars']:
            adjustments[a] = adjustments.get(a, 0) - txn['a_dollars']
            adjustments[b] = adjustments.get(b, 0) + txn['a_dollars']
        # party_b sent b_dollars to party_a
        if txn['b_dollars']:
            adjustments[b] = adjustments.get(b, 0) - txn['b_dollars']
            adjustments[a] = adjustments.get(a, 0) + txn['b_dollars']

    return adjustments


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
