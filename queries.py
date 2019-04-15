import json
import xmltodict
import pandas as pd
from flask_sqlalchemy import SQLAlchemy
from models import Base, League, Team, SeasonStats
from app import application, oauth

db = SQLAlchemy(application)

def query(url):
    if not oauth.token_is_valid():
        oauth.refresh_access_token()

    xml_response = oauth.session.get(url)
    json_response = json.dumps(xmltodict.parse(xml_response.content))
    return json.loads(json_response)

def get_league(year):
    return db.session.query(League).filter(League.year == year).one()

def get_all_leagues():
    return db.session.query(League).all()

def get_teams(year):
    return db.session.query(Team) \
        .join(League, Team.league_id == League.league_id) \
        .filter(League.year == year).all()

def get_season_stats(year):
    query = str.format("select teams.name,season_stats.* from (season_stats join teams on season_stats.team_id = teams.id)" \
            " join leagues on teams.league_id = leagues.league_id where leagues.year = '{0}'", year)
    data_frame = pd.read_sql_query(query, con=db.engine)
    return data_frame

def update_season_stats(year):
    print str.format("Updating season stats for {}", year)
    league = get_league(year)
    teams = get_teams(year)
    for t in teams:
        base_url = "https://fantasysports.yahooapis.com/fantasy/v2"
        url = str.format('{0}/team/{1}.t.{2}/stats', base_url, league.league_id, t.team_key)
        data = query(url)

        stats = db.session.query(SeasonStats) \
            .join(Team, SeasonStats.team_id == Team.id) \
            .join(League, Team.league_id == League.league_id) \
            .filter(League.year == year) \
            .filter(Team.id == t.id).one()

        generate_team_stats(stats,data['fantasy_content']['team']['team_stats']['stats']['stat'])

        db.session.merge(stats)
        db.session.commit()

def calculate_roto_standings(data_frame):
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

def generate_team_stats(stats,data):
    stat_map = {
        '7': 'R',
        '8': 'H',
        '12': 'HR',
        '13': 'RBI',
        '16': 'SB',
        '3': 'AVG',
        '55': 'OPS',
        '50': 'IP',
        '28': 'W',
        '29': 'L',
        '32': 'SV',
        '42': 'SO',
        '48': 'HLD',
        '26': 'ERA',
        '27': 'WHIP',
        '60': 'N/A',
        '1': 'N/A'
    }

    for stat in data:
        if stat_map[stat['stat_id']] != 'N/A' and stat_map[stat['stat_id']] != 'IP':
            if stat_map[stat['stat_id']] == 'R':
                stats.runs = int(stat['value'])
            elif stat_map[stat['stat_id']] == 'H':
                stats.hits = int(stat['value'])
            elif stat_map[stat['stat_id']] == 'HR':
                stats.homeruns = int(stat['value'])
            elif stat_map[stat['stat_id']] == 'RBI':
                stats.rbis = int(stat['value'])
            elif stat_map[stat['stat_id']] == 'SB':
                stats.stolen_bases = int(stat['value'])
            elif stat_map[stat['stat_id']] == 'AVG':
                if stat['value'] != '-':
                    stats.avg = float(stat['value'])
            elif stat_map[stat['stat_id']] == 'OPS':
                if stat['value'] != '-':
                    stats.ops = float(stat['value'])
            elif stat_map[stat['stat_id']] == 'W':
                stats.wins = int(stat['value'])
            elif stat_map[stat['stat_id']] == 'L':
                stats.loses = int(stat['value'])
            elif stat_map[stat['stat_id']] == 'SV':
                stats.saves = int(stat['value'])
            elif stat_map[stat['stat_id']] == 'SO':
                stats.strikeouts = int(stat['value'])
            elif stat_map[stat['stat_id']] == 'HLD':
                stats.holds = int(stat['value'])
            elif stat_map[stat['stat_id']] == 'ERA':
                if stat['value'] != '-':
                    stats.era = float(stat['value'])
            elif stat_map[stat['stat_id']] == 'WHIP':
                if stat['value'] != '-':
                    stats.whip = float(stat['value'])
