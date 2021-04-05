from flask import Flask, render_template, request
import os
import pandas as pd

from packages.database.queries import *
from packages.database import connections

app = Flask(__name__)

if os.environ.get("DB_HOST"):
    engine = connections.tcp_connection()
else:
    engine = connections.unix_connection()

DBSession = sessionmaker(bind=engine)
session = DBSession()

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
        season = '2021'

    category = request.form.get('cat')
    if category is None:
        category = 'Total Rank'
    ascending = False

    if category in ['L','ERA','WHIP']:
        ascending = True

    # get season stats and create roto standings
    season_stats = get_season_stats(engine,season)
    season_roto = calculate_roto_standings(season_stats, False)
    season_roto.columns = columns

    # define labels and values for the season bar chart
    labels = season_roto[season_roto.columns[0]]
    batting_ranks = season_roto[season_roto.columns[8]]
    pitching_ranks = season_roto[season_roto.columns[16]]

    season_roto = season_roto.sort_values(by=category, ascending=ascending)

    return render_template( 'index.html',
                            season=season,
                            labels=labels,
                            sort=category,
                            categories=columns,
                            batting_ranks=batting_ranks,
                            pitching_ranks=pitching_ranks,
                            tables=[
                                season_roto.to_html(
                                    table_id='season-roto-table',
                                    index=False,
                                    classes=['table-striped','table','table-bordered','compact','nowrap']
                                )
                            ]
                           )

@app.route('/week_by_week', methods=['GET','POST'])
def week_by_week():
    season = request.form.get('season')
    if season is None:
        season = '2021'

    week = request.form.get('week')
    if week is None:
        week = '1'

    # get stats and create roto standings
    stats = get_week_stats(engine, season, week)
    weekly_roto = calculate_roto_standings(stats, False)
    weekly_roto.columns = columns

    return render_template( 'week_by_week.html',
                            season=season,
                            week=week,
                            tables=[
                                weekly_roto.to_html(
                                    table_id='roto-table',
                                    index=False,
                                    classes=['table-striped','table','table-bordered','compact','nowrap']
                                )
                            ]
                          )

@app.route('/team_info', methods=['GET','POST'])
def team_info():
    season = request.form.get('season')
    if not season:
        season = '2021'

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
    roto = calculate_roto_standings(stats, True)

    # map each team to a row so its easier to locate
    team_row_map = {}
    for row in range(0,12):
        team_row_map[roto.iloc[row]['name']] = row

    # find the league average for all counting stats
    league_avg = []
    stat_names = ['runs', 'hits', 'homeruns', 'rbis', 'sb', 'wins', 'loses', 'saves', 'strikeouts', 'holds']
    for stat in stat_names:
        league_avg.append(roto[stat].mean())

    # find a teams row using the team to row map and the team that was selected
    team_row = roto.iloc[team_row_map[team]]

    # create the data frame for the radar chart
    ranks_labels = ['R', 'H', 'HR', 'RBI', 'SB', 'AVG', 'OPS', 'W', 'L', 'SV', 'SO', 'HLD', 'ERA', 'WHIP']
    ranks = team_row[['runs_rank','hits_rank','homeruns_rank','rbis_rank','sb_rank','avg_rank','ops_rank',
                      'wins_rank','loses_rank','saves_rank','strikeouts_rank','holds_rank','era_rank','whip_rank']]

    # create the data frame for the horizontal bar chart
    stats_labels = ['R', 'H', 'HR', 'RBI', 'SB', 'W', 'L', 'SV', 'SO', 'HLD']
    stats = team_row[['runs', 'hits', 'homeruns', 'rbis', 'sb', 'wins', 'loses', 'saves', 'strikeouts', 'holds']]

    return render_template( 'team_info.html',
                            team=team,
                            season=season,
                            teams=teams,
                            ranks_labels=ranks_labels,
                            ranks=ranks,
                            stats_labels=stats_labels,
                            stats=stats,
                            league_avg=league_avg
                          )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
