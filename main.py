from flask import Flask, render_template, request, redirect, url_for
from flask_caching import Cache
import os
import pandas as pd

from sqlalchemy.orm import scoped_session
from packages.database.queries import *
from packages.database import connections
from packages.yahoo.api import get_roster
from packages.projections import load_batting_projections, load_pitching_projections, build_lineup, normalize_name
from packages.sheets import fetch_rights_players, fetch_keeper_costs
import packages.config as config

app = Flask(__name__)

cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 300})

if os.environ.get("DB_HOST"):
    engine = connections.tcp_connection()
else:
    engine = connections.unix_connection()

DBSession = scoped_session(sessionmaker(bind=engine))
session = DBSession()

@app.teardown_appcontext
def shutdown_session(exception=None):
    DBSession.remove()

# define the the table headers for all stat tables
columns = ['Team','R', 'H', 'HR', 'RBI', 'SB', 'AVG', 'OPS','Batting Rank',
           'W', 'L', 'SV', 'SO', 'HLD', 'ERA', 'WHIP', 'Pitching Rank',
           'Total Rank']

def calculate_roto_standings(data_frame,with_ranks):
    # define the stat names in the database and a corresponding ranking so that we can rank the data frame
    stat_names = ['runs', 'hits', 'homeruns', 'rbis', 'sb', 'avg', 'ops',
                  'wins', 'loses', 'saves', 'strikeouts', 'holds', 'era', 'whip']

    # define the rank categories
    batting_ranks = ['runs_rank','hits_rank','homeruns_rank','rbis_rank','sb_rank','avg_rank','ops_rank']
    pitching_ranks = ['wins_rank','loses_rank','saves_rank','strikeouts_rank','holds_rank','era_rank','whip_rank']

    # rank each stat category
    for stat in stat_names:
        key = str.format('{0}_rank', stat)

        # some pitching categories are ranked in decending order
        if stat in ['loses','era','whip']:
            data_frame[key] = data_frame[stat].rank(ascending=False)
        else:
            data_frame[key] = data_frame[stat].rank()

    # sum all the ranks and create a new column for batting, pitching and total
    data_frame['Batting Total Rank'] = data_frame[batting_ranks].sum(axis=1)
    data_frame['Pitching Total Rank'] = data_frame[pitching_ranks].sum(axis=1)
    data_frame['Total Rank'] = data_frame[['Batting Total Rank','Pitching Total Rank']].sum(axis=1)

    if with_ranks:
        return data_frame

    # strip down the data frame to only the columns we are interested in
    final_df = data_frame[['name','runs', 'hits', 'homeruns', 'rbis', 'sb', 'avg', 'ops', 'Batting Total Rank',
                          'wins', 'loses', 'saves', 'strikeouts', 'holds', 'era', 'whip', 'Pitching Total Rank',
                           'Total Rank']]

    return final_df.sort_values(['Total Rank'],ascending=[0])

# ── Cached data fetchers ───────────────────────────────────────────────────────

@cache.memoize(timeout=1800)  # 30 min — updated by cloud functions
def _cached_all_week_stats(season):
    return get_all_week_stats(engine, season)

@cache.memoize(timeout=1800)  # 30 min
def _cached_week_stats(season, week):
    return get_week_stats(engine, season, week)

@cache.memoize(timeout=86400)  # 24 hours — only changes at season start
def _cached_available_years():
    return get_available_years(session)

@cache.memoize(timeout=1800)  # 30 min
def _cached_season_stats(season):
    return get_season_stats(engine, season)

@cache.memoize(timeout=1800)  # 30 min — record book queries cover all years
def _cached_all_season_stats_all_years():
    return get_all_season_stats_all_years(engine)

@cache.memoize(timeout=1800)  # 30 min
def _cached_all_week_stats_all_years():
    return get_all_week_stats_all_years(engine)

@cache.memoize(timeout=21600)  # 6 hours — Google Sheet changes rarely
def _cached_rights_players():
    return fetch_rights_players()

@cache.memoize(timeout=21600)  # 6 hours — Google Sheet changes rarely
def _cached_keeper_costs():
    return fetch_keeper_costs()

@cache.memoize(timeout=3600)  # 1 hour — roster changes with pickups/trades
def _cached_roster(league_id, team_key):
    return get_roster(league_id, team_key)

@cache.memoize(timeout=3600)  # 1 hour
def _cached_rights_player_details():
    return get_all_rights_player_details(session)

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/', methods=['GET','POST'])
def index():
    # define the default values for the current year and week
    season = request.form.get('season')
    if season is None:
        season = config.CURRENT_YEAR

    category = request.form.get('cat')
    if category is None:
        category = 'Total Rank'
    ascending = False

    if category in ['L','ERA','WHIP']:
        ascending = True

    # get all regular season week stats (excluding playoffs)
    all_week_stats = _cached_all_week_stats(season)
    regular_season_stats = all_week_stats[all_week_stats['week'] < config.PLAYOFF_WEEK_START]
    no_data = regular_season_stats.empty

    labels = []
    batting_ranks = []
    pitching_ranks = []
    table_html = ''
    week_numbers = []
    team_week_ranks = {}

    if not no_data:
        # Aggregate cumulative regular season stats from weekly data
        season_stats = regular_season_stats.groupby('name').agg(
            runs=('runs', 'sum'),
            hits=('hits', 'sum'),
            homeruns=('homeruns', 'sum'),
            rbis=('rbis', 'sum'),
            sb=('sb', 'sum'),
            avg=('avg', 'mean'),
            ops=('ops', 'mean'),
            wins=('wins', 'sum'),
            loses=('loses', 'sum'),
            saves=('saves', 'sum'),
            strikeouts=('strikeouts', 'sum'),
            holds=('holds', 'sum'),
            era=('era', 'mean'),
            whip=('whip', 'mean'),
        ).reset_index()

        season_roto = calculate_roto_standings(season_stats, False)
        season_roto.columns = columns
        labels = season_roto[season_roto.columns[0]]
        batting_ranks = season_roto[season_roto.columns[8]]
        pitching_ranks = season_roto[season_roto.columns[16]]
        season_roto = season_roto.sort_values(by=category, ascending=ascending)
        table_html = season_roto.to_html(
            table_id='season-roto-table',
            index=False,
            classes=['table-striped','table','table-bordered','table-sm','compact','nowrap']
        )

        # Compute cumulative week-by-week rank data for line chart
        week_numbers = sorted(regular_season_stats['week'].unique().tolist())
        team_names_ordered = labels.tolist()
        team_week_ranks = {team: [] for team in team_names_ordered}
        for week_num in week_numbers:
            cumulative_df = regular_season_stats[regular_season_stats['week'] <= week_num].groupby('name').agg(
                runs=('runs', 'sum'),
                hits=('hits', 'sum'),
                homeruns=('homeruns', 'sum'),
                rbis=('rbis', 'sum'),
                sb=('sb', 'sum'),
                avg=('avg', 'mean'),
                ops=('ops', 'mean'),
                wins=('wins', 'sum'),
                loses=('loses', 'sum'),
                saves=('saves', 'sum'),
                strikeouts=('strikeouts', 'sum'),
                holds=('holds', 'sum'),
                era=('era', 'mean'),
                whip=('whip', 'mean'),
            ).reset_index()
            week_roto = calculate_roto_standings(cumulative_df, False)
            rank_map = dict(zip(week_roto['name'], week_roto['Total Rank']))
            for team in team_names_ordered:
                team_week_ranks[team].append(rank_map.get(team, None))

    return render_template( 'index.html',
                            active_tab='home',
                            season=season,
                            no_data=no_data,
                            available_years=_cached_available_years(),
                            labels=labels,
                            sort=category,
                            categories=columns,
                            batting_ranks=batting_ranks,
                            pitching_ranks=pitching_ranks,
                            tables=[table_html],
                            week_numbers=week_numbers,
                            team_week_ranks=team_week_ranks
                           )

@app.route('/week_by_week', methods=['GET','POST'])
def week_by_week():
    season = request.form.get('season')
    if season is None:
        season = config.CURRENT_YEAR

    week = request.form.get('week')
    if week is None:
        week = '1'

    category = request.form.get('cat')
    if category is None:
        category = 'Total Rank'
    ascending = category in ['L', 'ERA', 'WHIP']

    # get stats and create roto standings
    stats = _cached_week_stats(season, week)
    no_data = stats.empty

    table_html = ''
    if not no_data:
        weekly_roto = calculate_roto_standings(stats, False)
        weekly_roto.columns = columns
        weekly_roto = weekly_roto.sort_values(by=category, ascending=ascending)
        table_html = weekly_roto.to_html(
            table_id='roto-table',
            index=False,
            classes=['table-striped','table','table-bordered','table-sm','compact','nowrap']
        )

    return render_template( 'week_by_week.html',
                            active_tab='week_by_week',
                            season=season,
                            week=week,
                            sort=category,
                            no_data=no_data,
                            available_years=_cached_available_years(),
                            tables=[table_html]
                          )

@app.route('/team_info', methods=['GET','POST'])
def team_info():
    season = request.form.get('season')
    if not season:
        season = config.CURRENT_YEAR

    # define the options for the team dropdown
    teams = []
    results = get_teams(session, season)
    for t in results:
        teams.append(t.name)

    # default to using the first team in the list
    team = request.form.get('teams')
    if not team or team not in teams:
        team = teams[0]

    # Category ranking tiles
    CATS = [
        ('runs',       'R',   '{:.0f}', 'batting'),
        ('hits',       'H',   '{:.0f}', 'batting'),
        ('homeruns',   'HR',  '{:.0f}', 'batting'),
        ('rbis',       'RBI', '{:.0f}', 'batting'),
        ('sb',         'SB',  '{:.0f}', 'batting'),
        ('avg',        'AVG', '{:.3f}', 'batting'),
        ('ops',        'OPS', '{:.3f}', 'batting'),
        ('wins',       'W',   '{:.0f}', 'pitching'),
        ('loses',      'L',   '{:.0f}', 'pitching'),
        ('saves',      'SV',  '{:.0f}', 'pitching'),
        ('strikeouts', 'SO',  '{:.0f}', 'pitching'),
        ('holds',      'HLD', '{:.0f}', 'pitching'),
        ('era',        'ERA', '{:.2f}', 'pitching'),
        ('whip',       'WHIP','{:.2f}', 'pitching'),
    ]

    category_tiles = []
    all_week_stats = _cached_all_week_stats(season)
    regular_season_stats = all_week_stats[all_week_stats['week'] < config.PLAYOFF_WEEK_START]
    if not regular_season_stats.empty:
        stats_df = regular_season_stats.groupby('name').agg(
            runs=('runs', 'sum'), hits=('hits', 'sum'), homeruns=('homeruns', 'sum'),
            rbis=('rbis', 'sum'), sb=('sb', 'sum'), avg=('avg', 'mean'),
            ops=('ops', 'mean'), wins=('wins', 'sum'), loses=('loses', 'sum'),
            saves=('saves', 'sum'), strikeouts=('strikeouts', 'sum'),
            holds=('holds', 'sum'), era=('era', 'mean'), whip=('whip', 'mean'),
        ).reset_index()
    else:
        stats_df = regular_season_stats
    if not stats_df.empty and team in stats_df['name'].values:
        roto = calculate_roto_standings(stats_df, True)
        num_teams = len(stats_df)
        row = roto[roto['name'] == team].iloc[0]
        for stat, label, fmt, group in CATS:
            raw_rank = int(row[f'{stat}_rank'])
            # Roto ranks: 12 = best, 1 = worst for all stats. Invert so display rank 1 = best.
            rank = num_teams + 1 - raw_rank
            color = 'success' if rank <= 4 else ('secondary' if rank <= 8 else 'danger')
            category_tiles.append({
                'label': label,
                'rank': rank,
                'value': fmt.format(row[stat]),
                'color': color,
                'group': group,
            })

    # Rights players from Google Sheet + DB details
    try:
        all_rights = _cached_rights_players()
    except Exception:
        all_rights = {}

    details_map = _cached_rights_player_details()
    raw_rights = all_rights.get(team, [])
    rights_players = []
    for name in raw_rights:
        d = details_map.get(normalize_name(name))
        rights_players.append({
            'name':    name,
            'level':   d.level    if d else '',
            'ranking': d.ranking  if d else '',
            'fv':      d.fv       if d else '',
        })

    # Keeper calculator: Yahoo roster + pre-calculated costs
    keeper_roster = []
    keeper_error = None
    team_obj = next((t for t in results if t.name == team), None)
    league_obj = session.query(League).filter(League.year == season).first()
    next_year = int(config.CURRENT_YEAR) + 1
    if team_obj and league_obj:
        try:
            roster_data = _cached_roster(league_obj.league_id, team_obj.team_key)
            costs_map = _cached_keeper_costs()
            for player in roster_data:
                name_full = player['name']['full']
                pos = player.get('display_position', '')
                cost = costs_map.get(normalize_name(name_full), 0.5)
                keeper_roster.append({'name': name_full, 'position': pos, 'cost': cost})
        except Exception as e:
            keeper_error = str(e)

    return render_template( 'team_info.html',
                            active_tab='team_info',
                            team=team,
                            season=season,
                            available_years=_cached_available_years(),
                            teams=teams,
                            category_tiles=category_tiles,
                            rights_players=rights_players,
                            keeper_roster=keeper_roster,
                            keeper_error=keeper_error,
                            next_year=next_year,
                          )

@app.route('/rulebook')
def rulebook():
    return render_template('rulebook.html', active_tab='rulebook')

@app.route('/record_book')
def record_book():
    STATS = [
        ('runs',        'Runs',         '{:,}',   False),
        ('hits',        'Hits',         '{:,}',   False),
        ('homeruns',    'Home Runs',    '{:,}',   False),
        ('rbis',        'RBI',          '{:,}',   False),
        ('sb',          'Stolen Bases', '{:,}',   False),
        ('avg',         'AVG',          '{:.3f}', False),
        ('ops',         'OPS',          '{:.3f}', False),
        ('wins',        'Wins',         '{:,}',   False),
        ('loses',       'Losses',       '{:,}',   True),
        ('saves',       'Saves',        '{:,}',   False),
        ('strikeouts',  'Strikeouts',   '{:,}',   False),
        ('holds',       'Holds',        '{:,}',   False),
        ('era',         'ERA',          '{:.2f}', True),
        ('whip',        'WHIP',         '{:.2f}', True),
    ]

    def make_records(df, extra_cols):
        records = []
        for col, label, fmt, low_is_good in STATS:
            if df[col].isna().all():
                continue
            best_row = df.loc[df[col].idxmin() if low_is_good else df[col].idxmax()]
            worst_row = df.loc[df[col].idxmax() if low_is_good else df[col].idxmin()]
            records.append({
                'stat': label,
                'best': {
                    'value': fmt.format(best_row[col]),
                    'team': best_row['name'],
                    **{k: best_row[k] for k in extra_cols},
                },
                'worst': {
                    'value': fmt.format(worst_row[col]),
                    'team': worst_row['name'],
                    **{k: worst_row[k] for k in extra_cols},
                },
            })
        return records

    season_df = _cached_all_season_stats_all_years()
    week_df = _cached_all_week_stats_all_years()

    # Exclude incomplete seasons
    season_df = season_df[(season_df['year'] != '2020') & (season_df['year'] != config.CURRENT_YEAR)]

    # Exclude the current in-progress week
    current_league = session.query(League).filter_by(year=config.CURRENT_YEAR).first()
    if current_league:
        current_week = int(current_league.current_week)
        week_df = week_df[~((week_df['year'] == config.CURRENT_YEAR) & (week_df['week'] >= current_week))]

    season_records = make_records(season_df, ['year']) if not season_df.empty else []
    week_records = make_records(week_df, ['year', 'week']) if not week_df.empty else []

    return render_template('record_book.html',
                           active_tab='record_book',
                           season_records=season_records,
                           week_records=week_records)

@app.route('/admin/rights', methods=['GET', 'POST'])
def admin_rights():
    if request.method == 'POST':
        for key, value in request.form.items():
            if key.startswith('level_'):
                player_name = key[len('level_'):]
                level   = value.strip()
                ranking = request.form.get(f'ranking_{player_name}', '').strip()
                fv      = request.form.get(f'fv_{player_name}', '').strip()
                upsert_rights_player_details(session, player_name, level, ranking, fv)
        # Invalidate rights caches after admin update
        cache.delete_memoized(_cached_rights_player_details)
        return redirect(url_for('admin_rights'))

    try:
        all_rights = _cached_rights_players()
    except Exception:
        all_rights = {}

    details_map = _cached_rights_player_details()

    teams_rights = []
    for team_name, players in sorted(all_rights.items()):
        rows = []
        for name in players:
            d = details_map.get(normalize_name(name))
            rows.append({
                'name':    name,
                'level':   d.level    if d else '',
                'ranking': d.ranking  if d else '',
                'fv':      d.fv       if d else '',
            })
        teams_rights.append({'team': team_name, 'players': rows})

    return render_template('admin_rights.html', teams_rights=teams_rights)


@app.route('/projections')
def projections():
    return render_template('projections.html', active_tab='projections')

@app.route('/ping')
def ping():
    return 'ok', 200


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
