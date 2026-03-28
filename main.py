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

@cache.memoize(timeout=21600)  # 6 hours — updated manually
def _cached_transactions():
    return fetch_transactions()

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
    BASE_BUDGET = 260
    BASE_KEEPER_SPOTS = 6
    db_txns = _cached_db_transactions()
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

    # Exclude incomplete seasons
    season_df = season_df[(season_df['year'] != '2020') & (season_df['year'] != config.CURRENT_YEAR)]

    # Exclude the current in-progress week
    current_league = session.query(League).filter_by(year=config.CURRENT_YEAR).first()
    if current_league:
        current_week = int(current_league.current_week)
        week_df = week_df[~((week_df['year'] == config.CURRENT_YEAR) & (week_df['week'] >= current_week))]

    season_records = make_records(season_df, ['year']) if not season_df.empty else []
    week_records = make_records(week_df, ['year', 'week']) if not week_df.empty else []

    # Compute roto champion per year from regular season weekly data
    all_weeks = _cached_all_week_stats_all_years()
    roto_champs = {}
    for year in config.CHAMPIONS:
        yr_df = all_weeks[
            (all_weeks['year'] == year) &
            (all_weeks['week'] < config.PLAYOFF_WEEK_START)
        ]
        if yr_df.empty:
            continue
        agg = yr_df.groupby('name').agg(
            runs=('runs','sum'), hits=('hits','sum'), homeruns=('homeruns','sum'),
            rbis=('rbis','sum'), sb=('sb','sum'), avg=('avg','mean'),
            ops=('ops','mean'), wins=('wins','sum'), loses=('loses','sum'),
            saves=('saves','sum'), strikeouts=('strikeouts','sum'),
            holds=('holds','sum'), era=('era','mean'), whip=('whip','mean'),
        ).reset_index()
        roto = calculate_roto_standings(agg, False)
        roto_champs[year] = roto.iloc[0]['name']
    roto_champs['2020'] = "Ms. Dean's Lean"

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


@app.route('/projections')
def projections():
    return render_template('projections.html', active_tab='projections')

@app.route('/ping')
def ping():
    return 'ok', 200


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
