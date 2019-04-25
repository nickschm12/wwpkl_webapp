from flask import Flask, render_template, request
from app import application,scheduler
from queries import get_season_stats,update_season_stats
import pandas as pd

scheduler.add_job(func=update_season_stats, args=['2019'], trigger="interval", minutes=10)
scheduler.start()

def calculate_roto_standings(data_frame):
    # define the stat names in the database and a corresponding ranking so that we can rank the data frame
    stat_names = ['runs', 'hits', 'homeruns', 'rbis', 'stolen_bases', 'avg', 'ops',
                  'wins', 'loses', 'saves', 'strikeouts', 'holds', 'era', 'whip']
    batting_ranks = ['runs_rank','hits_rank','homeruns_rank','rbis_rank','stolen_bases_rank','avg_rank','ops_rank']
    pitching_ranks = ['wins_rank','loses_rank','saves_rank','strikeouts_rank','holds_rank','era_rank','whip_rank']

    for stat in stat_names:
        key = str.format('{0}_rank', stat)

        if stat in ['loses','era','whip']:
            data_frame[key] = data_frame[stat].rank(ascending=False)
        else:
            data_frame[key] = data_frame[stat].rank()

    data_frame['Batting Total Rank'] = data_frame[batting_ranks].sum(axis=1)
    data_frame['Pitching Total Rank'] = data_frame[pitching_ranks].sum(axis=1)
    data_frame['Total Rank'] = data_frame[['Batting Total Rank','Pitching Total Rank']].sum(axis=1)

    final_df = data_frame[['name','runs', 'hits', 'homeruns', 'rbis', 'stolen_bases', 'avg', 'ops', 'Batting Total Rank',
                          'wins', 'loses', 'saves', 'strikeouts', 'holds', 'era', 'whip', 'Pitching Total Rank',
                           'Total Rank']]
    return final_df.sort_values(['Total Rank'],ascending=[0])

@application.route('/', methods=['GET','POST'])
def index():
    columns = ['Team','R', 'H', 'HR', 'RBI', 'SB', 'AVG', 'OPS','Batting Rank',
               'W', 'L', 'SV', 'SO', 'HLD', 'ERA', 'WHIP', 'Pitching Rank',
               'Total Rank']
    year = '2019'
    stats = get_season_stats(year)
    roto = calculate_roto_standings(stats)
    roto.columns = columns
    return render_template('index.html', tables=[roto.to_html(table_id='roto-table', index=False, classes=['table-striped','table','table-bordered','compact','nowrap'])])

@application.route('/previous_seasons', methods=['GET','POST'])
def previous_seasons():
    seasons = ['2015','2016','2017','2018']
    columns = ['Team','R', 'H', 'HR', 'RBI', 'SB', 'AVG', 'OPS','Batting Rank',
               'W', 'L', 'SV', 'SO', 'HLD', 'ERA', 'WHIP', 'Pitching Rank',
               'Total Rank']
    year = request.form.get('seasons')
    stats = get_season_stats(year)
    roto = calculate_roto_standings(stats)
    roto.columns = columns
    return render_template('previous_seasons.html', seasons=seasons, tables=[roto.to_html(table_id='roto-table', index=False, classes=['table-striped','table','table-bordered','compact','nowrap'])])

if __name__ == '__main__':
    application.run()
