from flask import Flask, render_template, request
import os
import pandas as pd

from sqlalchemy.orm import scoped_session
from packages.database.queries import *
from packages.database import connections
from packages.yahoo.api import get_roster
from packages.projections import load_batting_projections, load_pitching_projections, build_lineup
import packages.config as config

app = Flask(__name__)

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
    all_week_stats = get_all_week_stats(engine, season)
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
                            available_years=get_available_years(session),
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
    stats = get_week_stats(engine, season, week)
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
                            available_years=get_available_years(session),
                            tables=[table_html]
                          )

@app.route('/team_info', methods=['GET','POST'])
def team_info():
    season = request.form.get('season')
    if not season:
        season = config.CURRENT_YEAR

    # define the options for the team dropdown
    teams = []
    results = get_teams(session,season)
    for t in results:
        teams.append(t.name)

    # default to using the first team in the list
    team = request.form.get('teams')
    if not team or team not in teams:
        team = teams[0]

    # get stats and create roto standings
    stats = get_season_stats(engine,season)
    no_data = stats.empty

    ranks_labels = ['R', 'H', 'HR', 'RBI', 'SB', 'AVG', 'OPS', 'W', 'L', 'SV', 'SO', 'HLD', 'ERA', 'WHIP']
    stats_labels = ['R', 'H', 'HR', 'RBI', 'SB', 'W', 'L', 'SV', 'SO', 'HLD']
    ranks = []
    team_stats = []
    league_avg = []

    if not no_data:
        roto = calculate_roto_standings(stats, True)

        # map each team to a row so its easier to locate
        team_row_map = {}
        for row in range(0, len(roto)):
            team_row_map[roto.iloc[row]['name']] = row

        # find the league average for all counting stats
        stat_names = ['runs', 'hits', 'homeruns', 'rbis', 'sb', 'wins', 'loses', 'saves', 'strikeouts', 'holds']
        for stat in stat_names:
            league_avg.append(roto[stat].mean())

        # find a teams row using the team to row map and the team that was selected
        team_row = roto.iloc[team_row_map[team]]

        ranks = team_row[['runs_rank','hits_rank','homeruns_rank','rbis_rank','sb_rank','avg_rank','ops_rank',
                          'wins_rank','loses_rank','saves_rank','strikeouts_rank','holds_rank','era_rank','whip_rank']]
        team_stats = team_row[['runs', 'hits', 'homeruns', 'rbis', 'sb', 'wins', 'loses', 'saves', 'strikeouts', 'holds']]

    return render_template( 'team_info.html',
                            active_tab='team_info',
                            team=team,
                            season=season,
                            no_data=no_data,
                            available_years=get_available_years(session),
                            teams=teams,
                            ranks_labels=ranks_labels,
                            ranks=ranks,
                            stats_labels=stats_labels,
                            stats=team_stats,
                            league_avg=league_avg
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

    season_df = get_all_season_stats_all_years(engine)
    week_df = get_all_week_stats_all_years(engine)

    season_df = season_df[season_df['year'] != '2020']

    season_records = make_records(season_df, ['year']) if not season_df.empty else []
    week_records = make_records(week_df, ['year', 'week']) if not week_df.empty else []

    return render_template('record_book.html',
                           active_tab='record_book',
                           season_records=season_records,
                           week_records=week_records)

@app.route('/projections')
def projections():
    return render_template('projections.html', active_tab='projections')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
