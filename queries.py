import json
import xmltodict
import pandas as pd
from flask_sqlalchemy import SQLAlchemy
from models import Base, League, Team, SeasonStats, WeekStats
from app import application, oauth
import logging

db = SQLAlchemy(application)

"""
Query the yahoo_api for whatever is specified in the url
"""
def query_yahoo(url):
    # refresh oauth token if needed
    if not oauth.token_is_valid():
        oauth.refresh_access_token()

    # query the yahoo api, convert xml to json and return
    xml_response = oauth.session.get(url)
    json_response = json.dumps(xmltodict.parse(xml_response.content))
    return json.loads(json_response)

"""
Query the database for a specific league
"""
def get_league(year):
    return db.session.query(League).filter(League.year == year).one()

"""
Query the database for a all leagues
"""
def get_all_leagues():
    return db.session.query(League).all()

"""
Query Yahoo API to figure out what the current week is
"""
def find_current_week(year):
    # retrieve the league for a given year
    league = get_league(year)

    # build the url for getting league data and query the YahooAPI
    base_url = "https://fantasysports.yahooapis.com/fantasy/v2"
    league_url = str.format('{0}/league/{1}', base_url, league.league_id)
    league_data = query_yahoo(league_url)

    # output the YahooAPI response
    msg = str.format("YahooAPI returned: {}", league_data)
    application.logger.info(msg)

    current_week = None
    # define the current week if we get the proper response from Yahoo and default to 1 if not
    if 'fantasy_content' in league_data:
        current_week = int(league_data['fantasy_content']['league']['current_week'])
    else:
        application.logger.warning("YahooAPI didn't return expected result: defaulting to 1")

    return current_week

"""
Query the database for the current week in a given year
"""
def get_current_week(year):
    league = get_league(year)
    return league.current_week

"""
Update current_week for a given year
"""
def set_current_week(year):
    # retrieve the league for a given year
    league = get_league(year)

    # get the current week for a given year
    current_week = find_current_week(year)

    # set the current_week if yahoo returned the expected response
    if current_week:
        league.current_week = current_week

        # update the league with proper settings
        db.session.merge(league)
        db.session.commit()

"""
Query the database for all teams in a given year
"""
def get_teams(year):
    return db.session.query(Team) \
        .join(League, Team.league_id == League.league_id) \
        .filter(League.year == year).all()

"""
Query the database for season stats for all teams in a given year
"""
def get_season_stats(year):
    query = str.format("select teams.name,season_stats.* from (season_stats join teams on season_stats.team_id = teams.id)" \
            " join leagues on teams.league_id = leagues.league_id where leagues.year = '{0}'", year)
    data_frame = pd.read_sql_query(query, con=db.engine)
    return data_frame

"""
Update every team's season stats in the database for a given year
"""
def update_season_stats(year):
    # get the SQLAlchemy objects for the league and all teams in a given year
    league = get_league(year)
    teams = get_teams(year)

    for t in teams:
        # build the url to get season stats
        base_url = "https://fantasysports.yahooapis.com/fantasy/v2"
        url = str.format('{0}/team/{1}.t.{2}/stats', base_url, league.league_id, t.team_key)
        data = query_yahoo(url)

        # output the YahooAPI response
        msg = str.format("YahooAPI returned: {}", data)
        application.logger.info(msg)

        # return 1 if Yahoo didnt provide the expected response
        if 'fantasy_content' not in data:
            application.logger.warning("YahooAPI didn't return expected result, returning 1")
            return 1

        # retrieve the stats object for that team and year
        stats = db.session.query(SeasonStats) \
            .join(Team, SeasonStats.team_id == Team.id) \
            .join(League, Team.league_id == League.league_id) \
            .filter(League.year == year) \
            .filter(Team.id == t.id).one()

        # transform data for the season_stats table
        generate_team_stats(stats,data['fantasy_content']['team']['team_stats']['stats']['stat'])

        # update the database with up to date stats
        db.session.merge(stats)
        db.session.commit()

    return 0

"""
Query the database for week stats for all teams in a given year and week
"""
def get_week_stats(year, week):
    query = str.format("select t.name, w.* from (week_stats as w join teams as t on w.team_id = t.id)"\
            " join leagues as l on t.league_id = l.league_id where l.year = '{0}' and w.week = '{1}'", year, week)
    data_frame = pd.read_sql_query(query, con=db.engine)
    return data_frame

def create_week_stats(year):
    # get the SQLAlchemy objects for the league and all teams in a given year
    league = get_league(year)
    teams = get_teams(year)
    week = get_current_week(year)

    weeks = db.session.query(WeekStats) \
        .filter(WeekStats.week == week).all()

    if weeks:
        application.logger.warning("Already have created weekly stats")
        return 1

    for t in teams:
        # build the url to get season stats
        base_url = "https://fantasysports.yahooapis.com/fantasy/v2"
        url = str.format('{0}/team/{1}.t.{2}/stats;type=week;week={3}', base_url, league.league_id, t.team_key, week)
        data = query_yahoo(url)

        # output the YahooAPI response
        msg = str.format("YahooAPI returned: {}", data)
        application.logger.info(msg)

        # return 1 if Yahoo didnt provide the expected response
        if 'fantasy_content' not in data:
            application.logger.warning("YahooAPI didn't return expected result, returning 1")
            return 1

        # create WeekStats object
        stats = WeekStats(league, t, week)

        # transform data for the season_stats table
        generate_team_stats(stats,data['fantasy_content']['team']['team_stats']['stats']['stat'])

        # update the database with up to date stats
        db.session.merge(stats)
        db.session.commit()

    return 0

def create_league(year):
    base_url = "https://fantasysports.yahooapis.com/fantasy/v2"

    url = str.format('{0}/users;use_login=1/games;game_codes=mlb/leagues',base_url)
    data = query_yahoo(url)
    seasons = data['fantasy_content']['users']['user']['games']['game']
    print seasons

    for season in seasons:
        for l in season['leagues']['league']:
            if type(l) is dict:
                name = l['name'].encode('utf-8').strip()
                if 'WWP Keeper' in name:
                    league_year = l['season'].encode('utf-8').strip()
                    if year == league_year:
                        league_id = l['league_key'].encode('utf-8').strip()
                        num_of_teams = l['num_teams'].encode('utf-8').strip()
                        week = l['start_week'].encode('utf-8').strip()

                        if not db.session.query(League).filter( League.year == year).all():
                            new_league = League(league_id,name,year,int(num_of_teams),week)
                            db.session.add(new_league)
                            db.session.commit()

def create_teams(league):
    base_url = "https://fantasysports.yahooapis.com/fantasy/v2"

    teams = []
    for team_key in range(1,league.num_of_teams+1):
        url = str.format('{0}/team/{1}.t.{2}/stats', base_url, league.league_id, team_key)
        data = query_yahoo(url)
        team_data = data['fantasy_content']['team']
        name = team_data['name'].encode('utf-8').strip()
        new_team = Team(team_key,name,league)
        db.session.add(new_team)
        teams.append(new_team)
    if teams:
        db.session.commit()

def create_season_stats(league,team):
    stats = SeasonStats(league, team)
    base_url = "https://fantasysports.yahooapis.com/fantasy/v2"
    url = str.format('{0}/team/{1}.t.{2}/stats', base_url, league.league_id, team.team_key)
    data = query_yahoo(url)
    generate_team_stats(stats,data['fantasy_content']['team']['team_stats']['stats']['stat'])
    db.session.add(stats)
    db.session.commit()

"""
Update every team's weekly stats in the database for a given year in the current week
"""
def update_week_stats(year):
    # get the SQLAlchemy objects for the league and all teams in a given year
    league = get_league(year)
    teams = get_teams(year)
    week = get_current_week(year)

    for t in teams:
        # build the url to get season stats
        base_url = "https://fantasysports.yahooapis.com/fantasy/v2"
        url = str.format('{0}/team/{1}.t.{2}/stats;type=week;week={3}', base_url, league.league_id, t.team_key, week)
        data = query_yahoo(url)

        # output the YahooAPI response
        msg = str.format("YahooAPI returned: {}", data)
        application.logger.info(msg)

        # return 1 if Yahoo didnt provide the expected response
        if 'fantasy_content' not in data:
            application.logger.warning("YahooAPI didn't return expected result, returning 1")
            return 1

        # retrieve the stats object for that team and year
        stats = db.session.query(WeekStats) \
            .join(Team, WeekStats.team_id == Team.id) \
            .join(League, Team.league_id == League.league_id) \
            .filter(League.year == year) \
            .filter(Team.id == t.id).filter(WeekStats.week == week).one()

        # transform data for the season_stats table
        generate_team_stats(stats,data['fantasy_content']['team']['team_stats']['stats']['stat'])

        # update the database with up to date stats
        db.session.merge(stats)
        db.session.commit()

    return 0

"""
Helper function that takes the raw yahoo data and translates into the preferred format for the tables
"""
def generate_team_stats(stats,data):
    # Yahoo gives a stat id and not a stat name so this dictionary maps the stat id to the stat name
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

    # run through all the stats retrieve from yahoo and update the corresponding field for the SeasonStats object
    for stat in data:
        if stat_map[stat['stat_id']] != 'N/A' and stat_map[stat['stat_id']] != 'IP':
            if stat['value'] == None:
                stat['value'] = '0'

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
