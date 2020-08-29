from flask import Flask, render_template, request
from app import application
from queries import get_season_stats,get_week_stats,get_current_week,get_teams
import pandas as pd
import logging

# define the the table headers for all stat tables
columns = ['Team','R', 'H', 'HR', 'RBI', 'SB', 'AVG', 'OPS','Batting Rank',
           'W', 'L', 'SV', 'SO', 'HLD', 'ERA', 'WHIP', 'Pitching Rank',
           'Total Rank']

def calculate_roto_standings(data_frame,with_ranks):
    # define the stat names in the database and a corresponding ranking so that we can rank the data frame
    stat_names = ['runs', 'hits', 'homeruns', 'rbis', 'stolen_bases', 'avg', 'ops',
                  'wins', 'loses', 'saves', 'strikeouts', 'holds', 'era', 'whip']

    # define the rank categories
    batting_ranks = ['runs_rank','hits_rank','homeruns_rank','rbis_rank','stolen_bases_rank','avg_rank','ops_rank']
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
    final_df = data_frame[['name','runs', 'hits', 'homeruns', 'rbis', 'stolen_bases', 'avg', 'ops', 'Batting Total Rank',
                          'wins', 'loses', 'saves', 'strikeouts', 'holds', 'era', 'whip', 'Pitching Total Rank',
                           'Total Rank']]

    return final_df.sort_values(['Total Rank'],ascending=[0])

@application.route('/', methods=['GET','POST'])
def index():
    # define the default values for the current year and week
    year = '2020'
    week = get_current_week(year)

    # output which week and year we are getting stats for
    msg = str.format("Getting {} season stats and week {} stats", year, week)
    application.logger.info(msg)

    # get season stats and create roto standings
    season_stats = get_season_stats(year)
    season_roto = calculate_roto_standings(season_stats, False)
    season_roto.columns = columns

    # define labels and values for the season bar chart
    labels = season_roto[season_roto.columns[0]]
    batting_ranks = season_roto[season_roto.columns[8]]
    pitching_ranks = season_roto[season_roto.columns[16]]

    # get weekly stats and create roto standings
    week_stats = get_week_stats(year, week)
    week_roto = calculate_roto_standings(week_stats, False)
    week_roto.columns = columns

    return render_template( 'index.html',
                            year=year,
                            week=week,
                            labels=labels,
                            batting_ranks=batting_ranks,
                            pitching_ranks=pitching_ranks,
                            tables=[ season_roto.to_html(table_id='season-roto-table', index=False, classes=['table-striped','table','table-bordered','compact','nowrap']),
                                     week_roto.to_html(table_id='week-roto-table', index=False, classes=['table-striped','table','table-bordered','compact','nowrap'])
                                   ]
                           )

@application.route('/previous_seasons', methods=['GET','POST'])
def previous_seasons():
    # define the options for dropdowns
    seasons = ['2015','2016','2017','2018','2019']

    # get user input from the dropdown
    year = request.form.get('seasons')

    # the first time the page is opened year will be empty so pick a default value
    if not year:
        year = '2019'

    # output which week and year we are getting stats for
    msg = str.format("Getting previous season stats for the {} season ", year)
    application.logger.info(msg)

    # get stats and create roto standings
    stats = get_season_stats(year)
    roto = calculate_roto_standings(stats, False)
    roto.columns = columns

    # define labels and values for the season bar chart
    labels = roto[roto.columns[0]]
    batting_ranks = roto[roto.columns[8]]
    pitching_ranks = roto[roto.columns[16]]

    return render_template( 'previous_seasons.html',
                            year=year,
                            seasons=seasons,
                            labels=labels,
                            batting_ranks=batting_ranks,
                            pitching_ranks=pitching_ranks,
                            tables=[roto.to_html(table_id='roto-table', index=False, classes=['table-striped','table','table-bordered','compact','nowrap'])]
                          )

@application.route('/week_by_week', methods=['GET','POST'])
def week_by_week():
    # define the options for dropdowns
    seasons = ['2019']
    weeks = list(range(1,26))

    # get user input from dropdowns
    year = request.form.get('seasons')
    week = request.form.get('weeks')

    # the first time the page is opened year and week will be empty so give them default values
    if not year:
        year = '2019'
    if not week:
        week = get_current_week(year)

    # output which week and year we are getting stats for
    msg = str.format("Getting stats for week {} and the {} season ", week, year)
    application.logger.info(msg)

    # get stats and create roto standings
    stats = get_week_stats(year, week)
    roto = calculate_roto_standings(stats, False)
    roto.columns = columns

    # define labels and values for the season bar chart
    labels = roto[roto.columns[0]]
    batting_ranks = roto[roto.columns[8]]
    pitching_ranks = roto[roto.columns[16]]

    return render_template( 'week_by_week.html',
                            year=year,
                            week=week,
                            seasons=seasons,
                            weeks=weeks,
                            batting_ranks=batting_ranks,
                            pitching_ranks=pitching_ranks,
                            tables=[roto.to_html(table_id='roto-table', index=False, classes=['table-striped','table','table-bordered','compact','nowrap'])]
                          )

@application.route('/team_info', methods=['GET','POST'])
def team_info():
    # define the options for the team dropdown
    year = '2020'
    teams = []
    results = get_teams(year)
    for t in results:
        teams.append(t.name)

    # get user input from the dropdown
    team = request.form.get('teams')

    # default to using the first team in the list
    if not team:
        team = teams[0]

    # output which week and year we are getting stats for
    msg = str.format("Getting season stats for the {} season ", year)
    application.logger.info(msg)

    # get stats and create roto standings
    stats = get_season_stats(year)
    roto = calculate_roto_standings(stats, True)

    # map each team to a row so its easier to locate
    team_row_map = {}
    for row in range(0,12):
        team_row_map[roto.iloc[row]['name']] = row

    # find the league average for all counting stats
    league_avg = []
    stat_names = ['runs', 'hits', 'homeruns', 'rbis', 'stolen_bases', 'wins', 'loses', 'saves', 'strikeouts', 'holds']
    for stat in stat_names:
        league_avg.append(roto[stat].mean())

    # find a teams row using the team to row map and the team that was selected
    team_row = roto.iloc[team_row_map[team]]

    # create the data frame for the radar chart
    ranks_labels = ['R', 'H', 'HR', 'RBI', 'SB', 'AVG', 'OPS', 'W', 'L', 'SV', 'SO', 'HLD', 'ERA', 'WHIP']
    ranks = team_row[['runs_rank','hits_rank','homeruns_rank','rbis_rank','stolen_bases_rank','avg_rank','ops_rank',
                      'wins_rank','loses_rank','saves_rank','strikeouts_rank','holds_rank','era_rank','whip_rank']]

    # create the data frame for the horizontal bar chart
    stats_labels = ['R', 'H', 'HR', 'RBI', 'SB', 'W', 'L', 'SV', 'SO', 'HLD']
    stats = team_row[['runs', 'hits', 'homeruns', 'rbis', 'stolen_bases', 'wins', 'loses', 'saves', 'strikeouts', 'holds']]

    return render_template( 'team_info.html',
                            team=team,
                            teams=teams,
                            ranks_labels=ranks_labels,
                            ranks=ranks,
                            stats_labels=stats_labels,
                            stats=stats,
                            league_avg=league_avg
                          )

if __name__ == '__main__':
    application.logger.info("Starting the application")
    application.run()
