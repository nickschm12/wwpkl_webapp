import json
import xmltodict
import pandas as pd
from flask_sqlalchemy import SQLAlchemy
from models import Base, League, Team, SeasonStats, WeekStats
from app import application, oauth

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
def get_current_week(year):
    league = get_league(year)

    base_url = "https://fantasysports.yahooapis.com/fantasy/v2"
    league_url = str.format('{0}/league/{1}', base_url, league.league_id)
    league_data = query_yahoo(league_url)
    num_weeks = int(league_data['fantasy_content']['league']['current_week'])

    return num_weeks

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
    print str.format("Updating season stats for {}", year)

    # get the SQLAlchemy objects for the league and all teams in a given year
    league = get_league(year)
    teams = get_teams(year)

    for t in teams:
        # build the url to get season stats
        base_url = "https://fantasysports.yahooapis.com/fantasy/v2"
        url = str.format('{0}/team/{1}.t.{2}/stats', base_url, league.league_id, t.team_key)
        data = query_yahoo(url)

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

"""
Query the database for week stats for all teams in a given year and week
"""
def get_week_stats(year, week):
    query = str.format("select t.name, w.* from (week_stats as w join teams as t on w.team_id = t.id)"\
            " join leagues as l on t.league_id = l.league_id where l.year = '{0}' and w.week = '{1}'", year, week)
    data_frame = pd.read_sql_query(query, con=db.engine)
    return data_frame

"""
Update every team's weekly stats in the database for a given year in the current week
"""
def update_week_stats(year):
    # get the SQLAlchemy objects for the league and all teams in a given year
    league = get_league(year)
    teams = get_teams(year)
    week = get_current_week(year)

    print str.format("Updating week stats for {0} in {1}", week, year)

    for t in teams:
        # build the url to get season stats
        base_url = "https://fantasysports.yahooapis.com/fantasy/v2"
        url = str.format('{0}/team/{1}.t.{2}/stats;type=week;week={3}', base_url, league.league_id, t.team_key, week)
        data = query_yahoo(url)

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
