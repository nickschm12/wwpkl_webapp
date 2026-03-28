"""
One-time script to fetch historical playoff and H2H champions from Yahoo.
Run from repo root: python scripts/fetch_champions.py
Output can be pasted into packages/config.py as CHAMPIONS dict.
"""
import os
import sys
import json
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from packages.yahoo.api import query_yahoo, get_league

BASE_URL = 'https://fantasysports.yahooapis.com/fantasy/v2'
PLAYOFF_WEEK_START = 23


def get_h2h_champion(league_key, end_week):
    """
    H2H champion = team with the best regular season record (weeks 1-22).
    Yahoo standings include playoff weeks, so we subtract playoff W-L-T
    from the final totals to recover the regular season record.
    """
    # Step 1: get final standings
    data = query_yahoo(f'{BASE_URL}/league/{league_key}/standings')
    teams = data['fantasy_content']['league']['standings']['teams']['team']
    final = {}
    team_names = {}
    for t in teams:
        key = t['team_key']
        ot = t['team_standings'].get('outcome_totals')
        if not ot:
            return None
        final[key] = {
            'wins': int(ot['wins']),
            'losses': int(ot['losses']),
            'ties': int(ot.get('ties', 0)),
        }
        team_names[key] = t['name']

    # Step 2: sum up per-category W-L for each team across playoff weeks
    playoff_wl = defaultdict(lambda: {'wins': 0, 'losses': 0, 'ties': 0})
    for week in range(PLAYOFF_WEEK_START, end_week + 1):
        data = query_yahoo(f'{BASE_URL}/league/{league_key}/scoreboard;week={week}')
        sc = data['fantasy_content']['league'].get('scoreboard')
        if not sc:
            continue
        matchups = sc['matchups']['matchup']
        if isinstance(matchups, dict):
            matchups = [matchups]
        for m in matchups:
            stat_winners = m.get('stat_winners', {}).get('stat_winner', [])
            if isinstance(stat_winners, dict):
                stat_winners = [stat_winners]
            team_keys = [t['team_key'] for t in m['teams']['team']]
            for sw in stat_winners:
                if sw.get('is_tied') == '1':
                    for key in team_keys:
                        playoff_wl[key]['ties'] += 1
                else:
                    winner = sw.get('winner_team_key')
                    if winner:
                        playoff_wl[winner]['wins'] += 1
                        for key in team_keys:
                            if key != winner:
                                playoff_wl[key]['losses'] += 1

    # Step 3: subtract playoff W-L-T from final to get regular season record
    reg_season = {}
    for key, f in final.items():
        p = playoff_wl[key]
        reg_season[key] = {
            'wins': f['wins'] - p['wins'],
            'losses': f['losses'] - p['losses'],
        }

    # Step 4: rank by wins descending
    best_key = max(reg_season, key=lambda k: reg_season[k]['wins'])
    return team_names[best_key]


def get_playoff_champion(league_key, end_week):
    """
    The champion is the team with the most non-consolation playoff wins.
    They win every round they play — unlike seeded teams with byes who skip rounds.
    Works for both 2-week (end_week=24) and 3-week (end_week=25) playoff formats.
    """
    nc_wins = {}
    nc_win_names = {}
    for week in range(PLAYOFF_WEEK_START, end_week + 1):
        data = query_yahoo(f'{BASE_URL}/league/{league_key}/scoreboard;week={week}')
        sc = data['fantasy_content']['league'].get('scoreboard')
        if not sc:
            continue
        matchups = sc['matchups']['matchup']
        if isinstance(matchups, dict):
            matchups = [matchups]
        for m in matchups:
            if m.get('is_playoffs') == '1' and m.get('is_consolation') == '0':
                winner_key = m.get('winner_team_key')
                if not winner_key:
                    continue
                for t in m['teams']['team']:
                    if t['team_key'] == winner_key:
                        nc_wins[winner_key] = nc_wins.get(winner_key, 0) + 1
                        nc_win_names[winner_key] = t['name']
    if not nc_wins:
        return None
    best_key = max(nc_wins, key=nc_wins.get)
    return nc_win_names[best_key]


if __name__ == '__main__':
    results = {}
    for year in [str(y) for y in range(2015, 2026)]:
        print(f'Fetching {year}...', end=' ', flush=True)
        league = get_league('WWP Keeper Leagues', year)
        if not league:
            print('no league found')
            continue
        lk = league['league_key']
        end_week = int(league.get('end_week') or 25)
        h2h = get_h2h_champion(lk, end_week)
        playoff = get_playoff_champion(lk, end_week)
        results[year] = {'h2h_champion': h2h, 'playoff_champion': playoff}
        print(f'H2H={h2h}, Playoff={playoff}')

    print('\nPaste into config.py:\n')
    print('CHAMPIONS = ' + json.dumps(results, indent=4, ensure_ascii=False))
