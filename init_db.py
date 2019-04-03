from yahoo_oauth import OAuth2
import json
import xmltodict
from models import Session, engine, Base, League, Team, Stats

def query(url):
    xml_response = oauth.session.get(url)
    json_response = json.dumps(xmltodict.parse(xml_response.content))
    return json.loads(json_response)

def create_leagues():
    base_url = "https://fantasysports.yahooapis.com/fantasy/v2"

    url = str.format('{0}/users;use_login=1/games;game_codes=mlb/leagues',base_url)
    data = query(url)
    seasons = data['fantasy_content']['users']['user']['games']['game']

    leagues = []
    for season in seasons:
        for l in season['leagues']['league']:
            if type(l) is dict:
                name = l['name'].encode('utf-8').strip()
                if 'WWP Keeper' in name:
                    league_id = l['league_key'].encode('utf-8').strip()
                    year = l['season'].encode('utf-8').strip()
                    num_of_teams = l['num_teams'].encode('utf-8').strip()
                    new_league = League(league_id,name,year,int(num_of_teams))
                    session.add(new_league)
                    leagues.append(new_league)
    return leagues


def create_teams(league):
    base_url = "https://fantasysports.yahooapis.com/fantasy/v2"

    for team_key in range(1,league.num_of_teams+1):
        url = str.format('{0}/team/{1}.t.{2}/stats', base_url, league.league_id, team_key)
        data = query(url)
        team_data = data['fantasy_content']['team']
        name = team_data['name'].encode('utf-8').strip()
        new_team = Team(team_key,name,league)
        session.add(new_team)
        generate_team_stats(league,new_team,team_data['team_stats']['stats']['stat'])

def generate_team_stats(league,team,data):
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

    stats = Stats(league,team)
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
    session.add(stats)

oauth = OAuth2(None, None, from_file='oauth2.json')
if not oauth.token_is_valid():
    oauth.refresh_access_token()

Base.metadata.create_all(engine)
session = Session()

leagues = create_leagues()
for l in leagues:
    create_teams(l)

session.commit()
session.close()


