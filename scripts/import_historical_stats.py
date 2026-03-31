"""
Import pre-2015 season stats from the historical record book spreadsheet.

Creates League + Team rows with IDs prefixed 'hist_' and inserts SeasonStats
for years 2006–2014. Safe to re-run (skips years already in the DB).

Usage:
    PROJECT_ID=484894850064 DB_SECRET_ID=wwpkl_db DB_SECRET_VERSION=2 DB_HOST=localhost:5432 \
    venv/bin/python scripts/import_historical_stats.py
"""
import sys
import os
import openpyxl

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from packages.database import connections
from packages.database.models import League, Team, SeasonStats
from sqlalchemy.orm import sessionmaker

XLSX = os.path.expanduser('~/Downloads/Keeper League Record Book-Updated End of 2024.xlsx')
YEARS = [str(y) for y in range(2006, 2015)]  # 2006–2014

engine = connections.tcp_connection()
Session = sessionmaker(bind=engine)
session = Session()

wb = openpyxl.load_workbook(XLSX)

for year in YEARS:
    league_id = f'hist_{year}'

    # Skip if already imported
    if session.query(League).filter_by(league_id=league_id).first():
        print(f'{year}: already imported, skipping')
        continue

    ws = wb[year]
    rows = list(ws.iter_rows(min_row=2, values_only=True))

    # Collect team stat rows (skip Final Position row and anything after it)
    team_rows = []
    for row in rows:
        if row[0] == 'Final Position' or row[0] is None:
            break
        if isinstance(row[0], str):
            team_rows.append(row)

    if not team_rows:
        print(f'{year}: no team rows found, skipping')
        continue

    # Create league row
    league = League(
        league_id=league_id,
        name='WWP Keeper League',
        year=year,
        num_of_teams=len(team_rows),
        current_week='22',
    )
    session.add(league)
    session.flush()

    imported = 0
    for row in team_rows:
        name, r, h, hr, rbi, sb, avg, ops, w, l, sv, k, hld, era, whip = row[:15]
        if not name or not isinstance(name, str):
            continue

        team = Team(name=name.strip(), team_key=0, league_id=league_id)
        session.add(team)
        session.flush()

        stats = SeasonStats(
            team_id=team.id,
            runs=int(r) if r is not None else None,
            hits=int(h) if h is not None else None,
            homeruns=int(hr) if hr is not None else None,
            rbis=int(rbi) if rbi is not None else None,
            sb=int(sb) if sb is not None else None,
            avg=float(avg) if avg is not None else None,
            ops=float(ops) if ops is not None else None,
            wins=int(w) if w is not None else None,
            loses=int(l) if l is not None else None,
            saves=int(sv) if sv is not None else None,
            strikeouts=int(k) if k is not None else None,
            holds=int(hld) if hld is not None else None,
            era=float(era) if era is not None else None,
            whip=float(whip) if whip is not None else None,
        )
        session.add(stats)
        imported += 1

    session.commit()
    print(f'{year}: imported {imported} teams')

session.close()
print('Done.')
