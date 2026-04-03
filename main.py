from flask import Flask, render_template, request, redirect, url_for
from flask_caching import Cache
import os
import pandas as pd

from sqlalchemy.orm import scoped_session
from packages.database.queries import *
from packages.database.models import Transaction as TransactionModel
from packages.database import connections
from packages.yahoo.api import get_roster
from packages.projections import load_batting_projections, load_pitching_projections, build_lineup, normalize_name
from packages.sheets import fetch_rights_players, fetch_keeper_costs, fetch_transactions, compute_budget_adjustments, compute_keeper_adjustments, MANAGER_TO_TEAM
import packages.config as config

app = Flask(__name__)

cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 300})

if os.environ.get("DB_HOST"):
    engine = connections.tcp_connection()
else:
    engine = connections.unix_connection()

DBSession = scoped_session(sessionmaker(bind=engine))
session = DBSession()

@app.before_request
def refresh_session():
    global session
    session = DBSession()

@app.teardown_appcontext
def shutdown_session(exception=None):
    if exception:
        try:
            DBSession.rollback()
        except Exception:
            pass
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

@cache.memoize(timeout=21600)  # 6 hours — updated manually
def _cached_transactions():
    return fetch_transactions()

@cache.memoize(timeout=300)  # 5 min — scoreboard changes weekly
def _cached_scoreboard(league_key, week):
    from packages.yahoo.api import query_yahoo
    data = query_yahoo(f'https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}/scoreboard;week={week}')
    return data['fantasy_content']['league']['scoreboard']['matchups']['matchup']

@cache.memoize(timeout=1800)  # 30 min — free agent pool changes slowly
def _cached_free_agents(league_key, position, count=5):
    from packages.yahoo.api import query_yahoo
    url = (f'https://fantasysports.yahooapis.com/fantasy/v2/league/{league_key}'
           f'/players;status=A;position={position};sort=AR;sort_type=season;count={count}')
    data = query_yahoo(url)
    players = data['fantasy_content']['league']['players'].get('player', [])
    if isinstance(players, dict):
        players = [players]
    result = []
    for p in players:
        if isinstance(p, dict):
            name_info = p.get('name', {})
            name = name_info.get('full') if isinstance(name_info, dict) else None
            ep = p.get('eligible_positions', {}).get('position', '')
            pos = ep if isinstance(ep, str) else (ep[0] if ep else '')
            if name:
                result.append({'name': name, 'pos': pos})
    return result


@cache.memoize(timeout=300)  # 5 min — live stats update during games
def _cached_team_week_stats(league_key, team_key, week):
    from packages.yahoo.api import query_yahoo
    data = query_yahoo(f'https://fantasysports.yahooapis.com/fantasy/v2/team/{league_key}.t.{team_key}/stats;type=week;week={week}')
    return data['fantasy_content']['team']


def _parse_yahoo_stats(team_data):
    """Parse Yahoo team stats response into {category: value} dict."""
    stats = {}
    stat_list = team_data.get('team_stats', {}).get('stats', {}).get('stat', [])
    if isinstance(stat_list, dict):
        stat_list = [stat_list]
    for s in stat_list:
        cat = config.STAT_ID_TO_CAT.get(str(s.get('stat_id', '')))
        if cat and cat not in ('N/A', 'IP'):
            try:
                stats[cat] = float(s.get('value') or 0)
            except (ValueError, TypeError):
                stats[cat] = 0.0
    return stats

@cache.memoize(timeout=300)  # 5 min — refreshed after admin edits
def _cached_db_transactions():
    return get_transactions(session)

@cache.memoize(timeout=3600)  # 1 hour — roster changes with pickups/trades
def _cached_roster(league_id, team_key):
    return get_roster(league_id, team_key)

@cache.memoize(timeout=3600)  # 1 hour
def _cached_rights_player_details():
    return get_all_rights_player_details(session)

def _fmt_txn_date(d):
    """Format a date object as M/D/YYYY without leading zeros."""
    if hasattr(d, 'month'):
        return f"{d.month}/{d.day}/{d.year}"
    return str(d) if d else ''


def _txn_obj_to_dict(txn):
    return {
        'id': txn.id,
        'date': _fmt_txn_date(txn.date),
        'date_obj': txn.date,
        'year': txn.year,
        'is_preseason': txn.is_preseason,
        'party_a': txn.party_a,
        'party_b': txn.party_b,
        'a_sends': txn.a_sends,
        'b_sends': txn.b_sends,
        'a_player': _extract_player(txn.a_sends),
        'b_player': _extract_player(txn.b_sends),
        'a_dollars': txn.a_dollars or 0,
        'b_dollars': txn.b_dollars or 0,
        'a_keeper_spots': txn.a_keeper_spots or 0,
        'b_keeper_spots': txn.b_keeper_spots or 0,
        'raw': txn.raw,
    }


def _compute_budget_adjustments_db(txns, year):
    adjustments = {}
    for txn in txns:
        if txn.year != str(year) or txn.is_preseason or not txn.party_a:
            continue
        a, b = txn.party_a, txn.party_b
        if txn.a_dollars:
            adjustments[a] = adjustments.get(a, 0) - txn.a_dollars
            adjustments[b] = adjustments.get(b, 0) + txn.a_dollars
        if txn.b_dollars:
            adjustments[b] = adjustments.get(b, 0) - txn.b_dollars
            adjustments[a] = adjustments.get(a, 0) + txn.b_dollars
    return adjustments


def _compute_keeper_adjustments_db(txns, year):
    adjustments = {}
    for txn in txns:
        if txn.year != str(year) or txn.is_preseason or not txn.party_a:
            continue
        a, b = txn.party_a, txn.party_b
        if txn.a_keeper_spots:
            adjustments[a] = adjustments.get(a, 0) - txn.a_keeper_spots
            adjustments[b] = adjustments.get(b, 0) + txn.a_keeper_spots
        if txn.b_keeper_spots:
            adjustments[b] = adjustments.get(b, 0) - txn.b_keeper_spots
            adjustments[a] = adjustments.get(a, 0) + txn.b_keeper_spots
    return adjustments


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

    labels = []
    batting_ranks = []
    pitching_ranks = []
    table_html = ''
    week_numbers = []
    team_week_ranks = {}

    if not regular_season_stats.empty:
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
    else:
        # Fall back to season_stats for years with no weekly data (pre-2015)
        season_stats = _cached_season_stats(season)
        if not season_stats.empty:
            season_stats = season_stats[
                ['name','runs','hits','homeruns','rbis','sb','avg','ops',
                 'wins','loses','saves','strikeouts','holds','era','whip']
            ].copy()
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

    no_data = not table_html

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
    BASE_BUDGET = 260
    BASE_KEEPER_SPOTS = 6
    try:
        db_txns = _cached_db_transactions()
    except Exception:
        db_txns = []
    budget_adjustments = _compute_budget_adjustments_db(db_txns, config.CURRENT_YEAR)
    keeper_adjustments = _compute_keeper_adjustments_db(db_txns, config.CURRENT_YEAR)
    adjustment = budget_adjustments.get(team, 0)
    adjusted_budget = BASE_BUDGET + adjustment
    keeper_adj = keeper_adjustments.get(team, 0)
    adjusted_keeper_spots = BASE_KEEPER_SPOTS + keeper_adj

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
                            base_budget=BASE_BUDGET,
                            adjusted_budget=adjusted_budget,
                            budget_adjustment=adjustment,
                            base_keeper_spots=BASE_KEEPER_SPOTS,
                            adjusted_keeper_spots=adjusted_keeper_spots,
                            keeper_adjustment=keeper_adj,
                          )

@app.route('/rulebook')
def rulebook():
    return render_template('rulebook.html', active_tab='rulebook')

@app.route('/transactions', methods=['GET', 'POST'])
def transactions():
    try:
        years = get_transaction_years(session)
        error = None
    except Exception as e:
        years = []
        error = str(e)
    selected = request.form.get('year') or (years[0] if years else None)
    txns = []
    if selected and not error:
        try:
            txns = [_txn_obj_to_dict(t) for t in get_transactions(session, selected)]
        except Exception as e:
            error = str(e)
    return render_template('transactions.html', active_tab='transactions',
                           years=years, selected=selected,
                           txns=txns, error=error)

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

    # Normalize team names to real person names
    season_df = season_df.copy()
    week_df = week_df.copy()
    season_df['name'] = season_df['name'].map(lambda n: config.NAME_MAP.get(n, n))
    week_df['name'] = week_df['name'].map(lambda n: config.NAME_MAP.get(n, n))

    # Exclude incomplete seasons
    season_df = season_df[(season_df['year'] != '2020') & (season_df['year'] != config.CURRENT_YEAR)]

    # Exclude the current in-progress week
    current_league = session.query(League).filter_by(year=config.CURRENT_YEAR).first()
    if current_league:
        current_week = int(current_league.current_week)
        week_df = week_df[~((week_df['year'] == config.CURRENT_YEAR) & (week_df['week'] >= current_week))]

    season_records = make_records(season_df, ['year']) if not season_df.empty else []
    week_records = make_records(week_df, ['year', 'week']) if not week_df.empty else []

    # Compute roto champion per year from regular season weekly data;
    # fall back to season_stats for years with no weekly data (pre-2015)
    all_weeks = week_df  # already name-mapped
    all_seasons = season_df  # already name-mapped (pre-filter)
    roto_champs = {}
    for year in config.CHAMPIONS:
        yr_df = all_weeks[
            (all_weeks['year'] == year) &
            (all_weeks['week'] < config.PLAYOFF_WEEK_START)
        ]
        if not yr_df.empty:
            agg = yr_df.groupby('name').agg(
                runs=('runs','sum'), hits=('hits','sum'), homeruns=('homeruns','sum'),
                rbis=('rbis','sum'), sb=('sb','sum'), avg=('avg','mean'),
                ops=('ops','mean'), wins=('wins','sum'), loses=('loses','sum'),
                saves=('saves','sum'), strikeouts=('strikeouts','sum'),
                holds=('holds','sum'), era=('era','mean'), whip=('whip','mean'),
            ).reset_index()
        else:
            agg = all_seasons[all_seasons['year'] == year][
                ['name','runs','hits','homeruns','rbis','sb','avg','ops',
                 'wins','loses','saves','strikeouts','holds','era','whip']
            ].copy()
        if agg.empty:
            continue
        roto = calculate_roto_standings(agg, False)
        roto_champs[year] = roto.iloc[0]['name']
    roto_champs['2020'] = 'Drew Kenavan'

    champions = [
        {'year': year, 'roto_champion': roto_champs.get(year), **data}
        for year, data in sorted(config.CHAMPIONS.items(), reverse=True)
    ]

    # Stat callouts
    from collections import Counter
    playoff_counts = Counter(c['playoff_champion'] for c in champions if c['playoff_champion'])
    h2h_counts = Counter(c['h2h_champion'] for c in champions if c['h2h_champion'])
    roto_counts = Counter(c['roto_champion'] for c in champions if c['roto_champion'])
    top_playoff = playoff_counts.most_common(1)[0]
    top_h2h = h2h_counts.most_common(1)[0]
    top_roto = roto_counts.most_common(1)[0]
    callouts = [
        {'label': 'Most Playoff Titles', 'team': top_playoff[0], 'value': f'{top_playoff[1]}x'},
        {'label': 'Most H2H Titles',     'team': top_h2h[0],     'value': f'{top_h2h[1]}x'},
        {'label': 'Most Roto Titles',    'team': top_roto[0],    'value': f'{top_roto[1]}x'},
    ]

    return render_template('record_book.html',
                           active_tab='record_book',
                           champions=champions,
                           callouts=callouts,
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


_TEAM_NAMES = sorted(MANAGER_TO_TEAM.values())


def _build_sends(player, dollars, keeper_spots):
    parts = []
    if player:
        parts.append(player)
    if dollars:
        parts.append(f'${dollars}')
    if keeper_spots == 1:
        parts.append('Keeper Spot')
    elif keeper_spots > 1:
        parts.append(f'{keeper_spots} Keeper Spots')
    return ', '.join(parts) or None


def _extract_player(sends_str):
    """Strip dollar amounts and keeper spot mentions to get just the player name."""
    import re as _re
    if not sends_str:
        return ''
    s = _re.sub(r'\$\d+', '', sends_str)
    s = _re.sub(r'\d*\s*Keeper Spots?', '', s, flags=_re.IGNORECASE)
    s = _re.sub(r',\s*,', ',', s)
    return s.strip(', ').strip()


@app.route('/admin/transactions', methods=['GET'])
def admin_transactions():
    year_filter = request.args.get('year', '')
    edit_id = request.args.get('edit')
    years = get_transaction_years(session)
    txns = [_txn_obj_to_dict(t) for t in get_transactions(session, year_filter if year_filter else None)]
    edit_txn = None
    if edit_id:
        obj = session.query(TransactionModel).filter_by(id=int(edit_id)).first()
        if obj:
            edit_txn = _txn_obj_to_dict(obj)
    return render_template('admin_transactions.html',
                           txns=txns, years=years, year_filter=year_filter,
                           edit_txn=edit_txn, team_names=_TEAM_NAMES)


def _parse_txn_form():
    from datetime import date as date_type
    raw_date = request.form.get('date', '').strip()
    d = date_type.fromisoformat(raw_date)
    year = str(d.year)
    party_a = request.form.get('party_a', '').strip() or None
    party_b = request.form.get('party_b', '').strip() or None
    a_player = request.form.get('a_player', '').strip()
    b_player = request.form.get('b_player', '').strip()
    a_dollars = int(request.form.get('a_dollars') or 0)
    b_dollars = int(request.form.get('b_dollars') or 0)
    a_keeper_spots = int(request.form.get('a_keeper_spots') or 0)
    b_keeper_spots = int(request.form.get('b_keeper_spots') or 0)
    a_sends = _build_sends(a_player, a_dollars, a_keeper_spots)
    b_sends = _build_sends(b_player, b_dollars, b_keeper_spots)
    is_preseason = bool(request.form.get('is_preseason'))
    return d, year, party_a, party_b, a_sends, b_sends, is_preseason, a_dollars, b_dollars, a_keeper_spots, b_keeper_spots


@app.route('/admin/transactions/add', methods=['POST'])
def admin_transactions_add():
    try:
        d, year, party_a, party_b, a_sends, b_sends, is_preseason, a_dollars, b_dollars, a_keeper_spots, b_keeper_spots = _parse_txn_form()
        raw = f"{party_a} sends {a_sends} to {party_b} for {b_sends}" if party_a else ''
        insert_transaction(session, d, year, party_a, party_b, a_sends, b_sends,
                           is_preseason, a_dollars, b_dollars, a_keeper_spots, b_keeper_spots, raw)
        cache.delete_memoized(_cached_db_transactions)
    except Exception:
        pass
    year_filter = request.form.get('year_filter', '')
    return redirect(url_for('admin_transactions', year=year_filter))


@app.route('/admin/transactions/edit/<int:txn_id>', methods=['POST'])
def admin_transactions_edit(txn_id):
    try:
        d, year, party_a, party_b, a_sends, b_sends, is_preseason, a_dollars, b_dollars, a_keeper_spots, b_keeper_spots = _parse_txn_form()
        raw = f"{party_a} sends {a_sends} to {party_b} for {b_sends}" if party_a else ''
        update_transaction(session, txn_id, date=d, year=year, party_a=party_a, party_b=party_b,
                           a_sends=a_sends, b_sends=b_sends, is_preseason=is_preseason,
                           a_dollars=a_dollars, b_dollars=b_dollars,
                           a_keeper_spots=a_keeper_spots, b_keeper_spots=b_keeper_spots, raw=raw)
        cache.delete_memoized(_cached_db_transactions)
    except Exception:
        pass
    year_filter = request.form.get('year_filter', '')
    return redirect(url_for('admin_transactions', year=year_filter))


@app.route('/admin/transactions/delete/<int:txn_id>', methods=['POST'])
def admin_transactions_delete(txn_id):
    delete_transaction(session, txn_id)
    cache.delete_memoized(_cached_db_transactions)
    year_filter = request.form.get('year_filter', '')
    return redirect(url_for('admin_transactions', year=year_filter))


_SCOUTING_CATS = [
    ('runs',       'R',    '{:.0f}', 'batting',  False),
    ('hits',       'H',    '{:.0f}', 'batting',  False),
    ('homeruns',   'HR',   '{:.0f}', 'batting',  False),
    ('rbis',       'RBI',  '{:.0f}', 'batting',  False),
    ('sb',         'SB',   '{:.0f}', 'batting',  False),
    ('avg',        'AVG',  '{:.3f}', 'batting',  False),
    ('ops',        'OPS',  '{:.3f}', 'batting',  False),
    ('wins',       'W',    '{:.0f}', 'pitching', False),
    ('loses',      'L',    '{:.0f}', 'pitching', True),
    ('saves',      'SV',   '{:.0f}', 'pitching', False),
    ('strikeouts', 'SO',   '{:.0f}', 'pitching', False),
    ('holds',      'HLD',  '{:.0f}', 'pitching', False),
    ('era',        'ERA',  '{:.2f}', 'pitching', True),
    ('whip',       'WHIP', '{:.2f}', 'pitching', True),
]

_CAT_TO_STAT_ID = {
    'R': '7', 'H': '8', 'HR': '12', 'RBI': '13', 'SB': '16', 'AVG': '3', 'OPS': '55',
    'W': '28', 'L': '29', 'SV': '32', 'SO': '42', 'HLD': '48', 'ERA': '26', 'WHIP': '27',
}

_CAT_VOLATILITY = {
    'R': 'low', 'H': 'low', 'HR': 'medium', 'RBI': 'low', 'SB': 'high',
    'AVG': 'low', 'OPS': 'low', 'W': 'medium', 'L': 'low', 'SV': 'high',
    'SO': 'low', 'HLD': 'high', 'ERA': 'medium', 'WHIP': 'low',
}


@app.route('/scouting', methods=['GET', 'POST'])
def scouting():
    season = config.CURRENT_YEAR
    MY_TEAM = 'Shmohawks'

    db_teams = get_teams(session, season)
    teams_list = [t.name for t in db_teams]
    teams_by_name = {t.name: t for t in db_teams}

    my_team = request.form.get('my_team') or MY_TEAM

    # Fetch league and determine current week
    current_week = None
    league_obj = None
    try:
        league_obj = session.query(League).filter(League.year == season).first()
        if league_obj:
            current_week = int(league_obj.current_week)
    except Exception:
        pass

    max_week = config.PLAYOFF_WEEK_START - 1
    selected_week = int(request.form.get('week') or current_week or 1)
    selected_week = max(1, min(selected_week, max_week))

    # Auto-detect opponent from scoreboard for the selected week
    matchup_week = selected_week
    opponent = ''
    try:
        if league_obj:
            matchups = _cached_scoreboard(league_obj.league_id, selected_week)
            if isinstance(matchups, dict):
                matchups = [matchups]
            for m in matchups:
                team_list_m = m['teams']['team']
                if isinstance(team_list_m, dict):
                    team_list_m = [team_list_m]
                names = [tm['name'] for tm in team_list_m]
                if my_team in names:
                    opponent = next((n for n in names if n != my_team), '')
                    break
    except Exception:
        pass

    # Season-long category comparison
    comparison = []
    my_edges = []
    their_edges = []

    all_week_stats = _cached_all_week_stats(season)
    regular = all_week_stats[all_week_stats['week'] < config.PLAYOFF_WEEK_START]

    if not regular.empty and opponent:
        stats_df = regular.groupby('name').agg(
            runs=('runs','sum'), hits=('hits','sum'), homeruns=('homeruns','sum'),
            rbis=('rbis','sum'), sb=('sb','sum'), avg=('avg','mean'),
            ops=('ops','mean'), wins=('wins','sum'), loses=('loses','sum'),
            saves=('saves','sum'), strikeouts=('strikeouts','sum'),
            holds=('holds','sum'), era=('era','mean'), whip=('whip','mean'),
        ).reset_index()

        roto = calculate_roto_standings(stats_df, True)
        num_teams = len(stats_df)

        my_row = roto[roto['name'] == my_team].iloc[0] if my_team in roto['name'].values else None
        opp_row = roto[roto['name'] == opponent].iloc[0] if opponent in roto['name'].values else None

        if my_row is not None and opp_row is not None:
            for stat, label, fmt, group, low_is_good in _SCOUTING_CATS:
                my_raw = int(my_row[f'{stat}_rank'])
                opp_raw = int(opp_row[f'{stat}_rank'])
                my_rank = num_teams + 1 - my_raw
                opp_rank = num_teams + 1 - opp_raw
                my_val = fmt.format(my_row[stat])
                opp_val = fmt.format(opp_row[stat])
                diff = opp_rank - my_rank  # positive = I'm better
                if diff >= 3:
                    edge = 'mine'
                    my_edges.append(label)
                elif diff <= -3:
                    edge = 'theirs'
                    their_edges.append(label)
                else:
                    edge = 'close'
                comparison.append({
                    'label': label, 'group': group,
                    'my_rank': my_rank, 'opp_rank': opp_rank,
                    'my_val': my_val, 'opp_val': opp_val,
                    'edge': edge,
                    'volatility': _CAT_VOLATILITY.get(label, 'low'),
                })

    # Recent form: last 4 complete weeks
    recent_form = []
    if matchup_week and opponent:
        for w in range(max(1, matchup_week - 4), matchup_week):
            wk_data = all_week_stats[all_week_stats['week'] == w]
            if wk_data.empty:
                continue
            wk_roto = calculate_roto_standings(wk_data, False)
            wk_sorted = wk_roto.sort_values('Total Rank', ascending=False).reset_index(drop=True)
            rank_map = {row['name']: idx + 1 for idx, row in wk_sorted.iterrows()}
            recent_form.append({
                'week': w,
                'my_rank': rank_map.get(my_team),
                'opp_rank': rank_map.get(opponent),
            })

    # Live matchup stats (only for current week)
    live_stats = []
    if selected_week == current_week and opponent and league_obj:
        my_team_obj = teams_by_name.get(my_team)
        opp_team_obj = teams_by_name.get(opponent)
        if my_team_obj and opp_team_obj:
            try:
                my_live_data = _cached_team_week_stats(league_obj.league_id, my_team_obj.team_key, matchup_week)
                opp_live_data = _cached_team_week_stats(league_obj.league_id, opp_team_obj.team_key, matchup_week)
                my_live = _parse_yahoo_stats(my_live_data)
                opp_live = _parse_yahoo_stats(opp_live_data)
                for stat, label, fmt, group, low_is_good in _SCOUTING_CATS:
                    my_v = my_live.get(label, 0.0)
                    opp_v = opp_live.get(label, 0.0)
                    if low_is_good:
                        edge = 'mine' if my_v < opp_v else ('theirs' if opp_v < my_v else 'close')
                    else:
                        edge = 'mine' if my_v > opp_v else ('theirs' if opp_v > my_v else 'close')
                    live_stats.append({
                        'label': label, 'group': group,
                        'my_val': fmt.format(my_v),
                        'opp_val': fmt.format(opp_v),
                        'edge': edge,
                    })
            except Exception:
                pass

    live_score = None
    if live_stats:
        my_wins = sum(1 for s in live_stats if s['edge'] == 'mine')
        opp_wins = sum(1 for s in live_stats if s['edge'] == 'theirs')
        ties = sum(1 for s in live_stats if s['edge'] == 'close')
        live_score = {'mine': my_wins, 'theirs': opp_wins, 'ties': ties}

    # Streaming tips based on opponent's edges
    # Streaming targets
    _batting_cats = ['R', 'H', 'HR', 'RBI', 'SB', 'AVG', 'OPS']
    _sp_cats = ['W', 'SO', 'ERA', 'WHIP', 'L']
    _rp_cats = ['SV', 'HLD']

    streaming_cats = [c['label'] for c in comparison if c['edge'] == 'theirs']
    fa_batters, fa_starters, fa_relievers = [], [], []

    if league_obj and streaming_cats:
        primary_bat = next((c for c in streaming_cats if c in _batting_cats), None)
        primary_sp  = next((c for c in streaming_cats if c in _sp_cats), None)
        primary_rp  = next((c for c in streaming_cats if c in _rp_cats), None)
        try:
            if primary_bat:
                fa_batters = _cached_free_agents(league_obj.league_id, 'B', 5)
        except Exception:
            pass
        try:
            if primary_sp:
                fa_starters = _cached_free_agents(league_obj.league_id, 'SP', 5)
        except Exception:
            pass
        try:
            if primary_rp:
                fa_relievers = _cached_free_agents(league_obj.league_id, 'RP', 5)
        except Exception:
            pass

    _name_w = max(len(my_team), len(opponent), 8) * 0.65 + 1.0
    team_col_width = f"{_name_w:.1f}rem"
    season_table_width = f"{3.5 + 2 * _name_w + 4.0:.1f}rem"
    live_table_width   = f"{3.5 + 2 * _name_w:.1f}rem"
    recent_table_width = f"{4.0 + 2 * _name_w:.1f}rem"

    return render_template('scouting.html',
                           teams=teams_list,
                           my_team=my_team,
                           opponent=opponent,
                           team_col_width=team_col_width,
                           season_table_width=season_table_width,
                           live_table_width=live_table_width,
                           recent_table_width=recent_table_width,
                           matchup_week=matchup_week,
                           selected_week=selected_week,
                           current_week=current_week,
                           max_week=max_week,
                           comparison=comparison,
                           my_edges=my_edges,
                           their_edges=their_edges,
                           recent_form=recent_form,
                           live_stats=live_stats,
                           live_score=live_score,
                           streaming_cats=streaming_cats,
                           fa_batters=fa_batters,
                           fa_starters=fa_starters,
                           fa_relievers=fa_relievers,
                           season=season)


@app.route('/projections')
def projections():
    return render_template('projections.html', active_tab='projections')

@app.route('/ping')
def ping():
    return 'ok', 200


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
