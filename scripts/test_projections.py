"""
Local test script for pre-season projections.

Usage:
    PROJECT_ID=484894850064 DB_SECRET_ID=wwpkl_db DB_SECRET_VERSION=2 \
    YAHOO_SECRET_ID=<secret_id> YAHOO_SECRET_VERSION=<version> \
    venv/bin/python scripts/test_projections.py
"""

import sys
import os
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from packages.yahoo.api import get_league, get_roster, query_yahoo
from packages.projections import load_batting_projections, load_pitching_projections, build_lineup

BATTING_CSV  = os.path.expanduser('~/Downloads/fangraphs-leaderboard-projections (2).csv')
PITCHING_CSV = os.path.expanduser('~/Downloads/fangraphs-leaderboard-projections (3).csv')
LEAGUE_NAME  = 'WWP Keeper Leagues'
YEAR         = '2026'

# ── Load projections ──────────────────────────────────────────────────────────
print('Loading projections...')
with open(BATTING_CSV)  as f: batting_proj  = load_batting_projections(f)
with open(PITCHING_CSV) as f: pitching_proj = load_pitching_projections(f)
print(f'  Batters:  {len(batting_proj):,}')
print(f'  Pitchers: {len(pitching_proj):,}')

# ── Fetch league + rosters from Yahoo ────────────────────────────────────────
print(f'\nFetching league "{LEAGUE_NAME}" ({YEAR})...')
league     = get_league(LEAGUE_NAME, YEAR)
league_key = league['league_key']
num_teams  = int(league['num_teams'])
print(f'  League key: {league_key}  ({num_teams} teams)')

rows        = []
lineups_raw = {}
unmatched   = {}

for team_key in range(1, num_teams + 1):
    data      = query_yahoo(f'https://fantasysports.yahooapis.com/fantasy/v2/team/{league_key}.t.{team_key}')
    team_name = data['fantasy_content']['team']['name']
    roster    = get_roster(league_key, team_key)

    display_rows, team_stats, missed = build_lineup(roster, batting_proj, pitching_proj)
    team_stats['name'] = team_name
    rows.append(team_stats)
    lineups_raw[team_name] = display_rows
    if missed:
        unmatched[team_name] = missed
    print(f'  {team_name}  ({len(roster)} players, {len(missed)} unmatched)')

# ── Roto standings ────────────────────────────────────────────────────────────
from main import calculate_roto_standings

df       = pd.DataFrame(rows)
standings = calculate_roto_standings(df, with_ranks=False).reset_index(drop=True)

print('\n' + '='*90)
print('PROJECTED ROTO STANDINGS')
print('='*90)
print(standings.to_string(index=False))

# ── Per-team lineups ──────────────────────────────────────────────────────────
print('\n' + '='*90)
print('PROJECTED LINEUPS  (ordered by standings)')
print('='*90)

ordered_teams = standings['name'].tolist()
for team_name in ordered_teams:
    rank = standings[standings['name'] == team_name].index[0] + 1
    print(f'\n--- #{rank} {team_name} ---')
    for row in lineups_raw[team_name]:
        print(f"  {row['slot']:6s}  {row['name']:30s}  {row['stats']}")

# ── Unmatched players ─────────────────────────────────────────────────────────
if unmatched:
    print('\n' + '='*90)
    print('UNMATCHED PLAYERS (not found in projection files)')
    print('='*90)
    for team_name, players in unmatched.items():
        print(f'  {team_name}: {", ".join(players)}')
