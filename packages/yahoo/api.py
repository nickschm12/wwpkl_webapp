import json
import os
from requests import get, post
import time
import xmltodict
from .oauth import *

base_url = "https://fantasysports.yahooapis.com/fantasy/v2"

# takes in a request and queries yahoo for a response
def query_yahoo(url):
    secrets = get_secrets()

    # read in credentials for yahoo
    access_token = os.environ.get('ACCESS_TOKEN', secrets['access_token'])

    retries = 0
    success = False
    data = None

    while retries < 2 and success == False:
        # set up the web request
        headers = {
            'Authorization': 'Bearer %s' % access_token,
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        response = get(url, headers=headers)

        if response.ok:
            # parse xml output into json
            xpars = xmltodict.parse(response.text)
            json_response = json.dumps(xpars)
            data = json.loads(json_response)
            success = True
        else:
            error = response.json()

            # Refresh the token if it expired
            if "token_expired" in error['error']['description']:
                print("Token expired, trying again.")
                access_token = refresh_access_token()
                os.environ['ACCESS_TOKEN'] = access_token
            elif "token_rejected" in error['error']['description']:
                print("Token was rejected, grab a new set of credentials")
                print(response.text)
            else:
                print("Yahoo sent back an unknown response.")
                print(response.text)

            retries = retries + 1

    return data

def get_leagues(league_season, sport='mlb'):
    url = str.format('{0}/users;use_login=1/games;game_codes={1}/leagues',base_url,sport)
    data = query_yahoo(url)
    seasons = data['fantasy_content']['users']['user']['games']['game']

    for season in seasons:
        for l in season['leagues']['league']:
            if type(l) is dict and league_season in l['season']:
                print(l)

def get_league(league_name, league_season, sport='mlb'):
    url = str.format('{0}/users;use_login=1/games;game_codes={1}/leagues',base_url,sport)
    data = query_yahoo(url)
    seasons = data['fantasy_content']['users']['user']['games']['game']

    league = None
    for season in seasons:
        for l in season['leagues']['league']:
            if type(l) is dict:
                if league_name in l['name'] and league_season in l['season']:
                    league = l

    return league

def get_team(league_key, team_key):
    url = str.format('{0}/team/{1}.t.{2}/stats', base_url, league_key, team_key)
    data = query_yahoo(url)
    team_data = data['fantasy_content']['team']
    return team_data

def get_teams(num_teams,league_key):
    teams = []

    for team_key in range(1,int(num_teams)+1):
        url = str.format('{0}/team/{1}.t.{2}/stats', base_url, league_key, team_key)
        data = query_yahoo(url)
        team_data = data['fantasy_content']['team']
        teams.append(team_data)

    return teams

def get_team_weekly_stats(league_key,team_key,week):
    url = str.format('{0}/team/{1}.t.{2}/stats;type=week;week={3}', base_url, league_key, team_key, week)
    data = query_yahoo(url)
    team_data = data['fantasy_content']['team']
    return team_data

def get_team_matchup_stats(league_key, team_key, week):
    url = str.format('{0}/team/{1}.t.{2}/matchups;week={3}', base_url, league_key, team_key, week)
    data = query_yahoo(url)
    team_data = data['fantasy_content']
    return team_data

def get_teams_weekly_stats(num_teams,league_key, week):
    teams = []
    for team_key in range(1,int(num_teams)+1):
        url = str.format('{0}/team/{1}.t.{2}/stats;type=week;week={3}', base_url, league_key, team_key, week)
        data = query_yahoo(url)
        team_data = data['fantasy_content']['team']
        teams.append(team_data)

    return teams

def get_roster(league_key,team_key):
    url = str.format('{0}/team/{1}.t.{2}/roster/players', base_url, league_key, team_key)
    data = query_yahoo(url)
    roster_data = data['fantasy_content']['team']['roster']['players']['player']
    return roster_data

def get_players(league_json, start):
    url = str.format('{0}/league/{1}/players;start={2}', base_url, league_json['league_key'], start)
    data = query_yahoo(url)
    return data['fantasy_content']['league']['players']['player']

def get_scoreboard(league_key):
    url = str.format('{0}/league/{1}/scoreboard', base_url, league_key)
    data = query_yahoo(url)
    return data
