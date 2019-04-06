from yahoo_oauth import OAuth2
from app import db
from models import Base, League, Team, SeasonStats
from queries import query, generate_team_stats
import json
import xmltodict

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
                    db.session.add(new_league)
                    leagues.append(new_league)
    return leagues


def create_teams(league):
    base_url = "https://fantasysports.yahooapis.com/fantasy/v2"

    teams = []
    for team_key in range(1,league.num_of_teams+1):
        url = str.format('{0}/team/{1}.t.{2}/stats', base_url, league.league_id, team_key)
        data = query(url)
        team_data = data['fantasy_content']['team']
        name = team_data['name'].encode('utf-8').strip()
        new_team = Team(team_key,name,league)
        db.session.add(new_team)
        teams.append(new_team)
    return teams

def create_stats(league,team):
    stats = SeasonStats(league, team)
    base_url = "https://fantasysports.yahooapis.com/fantasy/v2"
    url = str.format('{0}/team/{1}.t.{2}/stats', base_url, league.league_id, team.team_key)
    data = query(url)
    generate_team_stats(stats,data['fantasy_content']['team']['team_stats']['stats']['stat'])
    db.session.add(stats)

oauth = OAuth2(None, None, from_file='oauth2.json')
if not oauth.token_is_valid():
    oauth.refresh_access_token()

Base.metadata.create_all(db.engine)
leagues = create_leagues()
teams = []
for l in leagues:
    teams = teams + create_teams(l)

for t in teams:
    create_stats(t.league,t)

db.session.commit()
db.session.close()
