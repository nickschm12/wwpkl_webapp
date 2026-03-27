"""
Import rights player details from FanGraphs CSV + MLB Stats API.

- Rankings and FV grades come from the FanGraphs prospects board CSV.
- Levels come from the MLB Stats API (current minor league assignment).

Usage:
    PROJECT_ID=484894850064 DB_SECRET_ID=wwpkl_db DB_SECRET_VERSION=2 DB_HOST=localhost:5432 \
    FG_CSV=~/Downloads/fangraphs-the-board.csv \
    venv/bin/python scripts/import_rights_details.py
"""
import sys
import os
import re
import requests
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from packages.database import connections
from packages.database.queries import upsert_rights_player_details
from packages.projections import normalize_name
from packages.sheets import fetch_rights_players
from sqlalchemy.orm import sessionmaker

# ── Name overrides: sheet name → FanGraphs CSV name ──────────────────────────
NAME_OVERRIDES = {
    'Leodalis De Vries': 'Leo De Vries',
    'Jesus Made':        'Jesús Made',
    'Luis Pena':         'Luis Peña',
}

# ── MLB Stats API level lookup ────────────────────────────────────────────────
LEVEL_MAP = {11: 'AAA', 12: 'AA', 13: 'A+', 14: 'A', 16: 'Rookie', 17: 'DSL'}

def _build_mlb_index():
    index = {}
    for sport_id, level in LEVEL_MAP.items():
        resp = requests.get(
            f'https://statsapi.mlb.com/api/v1/sports/{sport_id}/players',
            params={'season': 2026, 'fields': 'people,id,fullName'},
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=10,
        )
        if resp.status_code != 200:
            continue
        for p in resp.json().get('people', []):
            norm = normalize_name(p.get('fullName', ''))
            if norm:
                index[norm] = level
    return index


def _parse_fv(val):
    """Convert FV strings like '55', '45+' to integer."""
    if pd.isna(val):
        return None
    return int(re.sub(r'[^\d]', '', str(val))) or None


# ── Main ──────────────────────────────────────────────────────────────────────
csv_path = os.path.expanduser(os.environ.get('FG_CSV', '~/Downloads/fangraphs-the-board.csv'))
print(f'Loading FanGraphs CSV: {csv_path}')
fg = pd.read_csv(csv_path)
fg['norm'] = fg['Name'].apply(normalize_name)
fg_index = {row['norm']: row for _, row in fg.iterrows()}

print('Building MLB level index...')
mlb_index = _build_mlb_index()
print(f'  {len(mlb_index)} players indexed from MLB Stats API')

print('Fetching rights players from Google Sheet...')
all_rights = fetch_rights_players()
all_players = sorted({p for players in all_rights.values() for p in players})
print(f'  {len(all_players)} unique rights players\n')

if os.environ.get('DB_HOST'):
    engine = connections.tcp_connection()
else:
    engine = connections.unix_connection()
session = sessionmaker(bind=engine)()

matched = 0
unmatched = []

for name in all_players:
    csv_name = NAME_OVERRIDES.get(name, name)
    norm_csv = normalize_name(csv_name)
    norm_orig = normalize_name(name)

    fg_row = fg_index.get(norm_csv)
    if fg_row is None:
        fg_row = fg_index.get(norm_orig)
    level   = mlb_index.get(norm_orig) or mlb_index.get(norm_csv)

    if fg_row is not None:
        ranking = int(fg_row['Top 100']) if not pd.isna(fg_row['Top 100']) else None
        fv      = _parse_fv(fg_row['FV'])
        upsert_rights_player_details(session, name, level or '', ranking, fv)
        matched += 1
        rank_str = str(ranking) if ranking else '—'
        fv_str   = str(fv) if fv else '—'
        lvl_str  = level or '—'
        print(f'  {name:<35} rank={rank_str:<5} FV={fv_str:<4} level={lvl_str}')
    else:
        unmatched.append(name)
        if level:
            upsert_rights_player_details(session, name, level, None, None)
            print(f'  {name:<35} rank=—     FV=—    level={level} (no CSV match)')

print(f'\n{matched} matched, {len(unmatched)} unmatched:')
for name in unmatched:
    print(f'  - {name}')
