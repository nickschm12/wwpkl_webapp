import pandas as pd
from models import Base, League, Team, Stats
from app import db

def get_leagues():
    db.session.query(League).all()

def get_teams():
    return db.session.query(Team) \
        .join(League, Team.league_id == League.league_id) \
        .filter(League.year == '2018')

def get_team_stats(year):
    query = str.format("select teams.name,stats.* from (stats join teams on stats.team_id = teams.id)" \
            " join leagues on teams.league_id = leagues.league_id where leagues.year = '{0}'", year)
    data_frame = pd.read_sql_query(query, con=db.engine)
    return data_frame

def calculate_roto_standings(data_frame):
    stat_names = ['runs', 'hits', 'homeruns', 'rbis', 'stolen_bases', 'avg', 'ops',
                  'wins', 'loses', 'saves', 'strikeouts', 'holds', 'era', 'whip']
    batting_ranks = ['runs_rank','hits_rank','homeruns_rank','rbis_rank','stolen_bases_rank','avg_rank','ops_rank']
    pitching_ranks = ['wins_rank','loses_rank','saves_rank','strikeouts_rank','holds_rank','era_rank','whip_rank']

    for stat in stat_names:
        key = str.format('{0}_rank', stat)

        if key in ['loses','era','whip']:
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
