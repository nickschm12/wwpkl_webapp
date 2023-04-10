import re
from sqlalchemy.orm import sessionmaker

from packages.yahoo.oauth import get_new_tokens
from packages.yahoo.api import *
from packages.database.models import Base, League, Team, SeasonStats, WeekStats
from packages.database.queries import *
from packages.database.connections import tcp_connection,unix_connection
import packages.config as config

# Set up database connection
if os.environ.get("DB_HOST"):
    engine = tcp_connection()
else:
    engine = unix_connection()
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)
session = DBSession()

def generate_team_stats(data):
    decimal_pattern = re.compile("^-?[0-9]?\.[0-9]*$")
    counting_pattern = re.compile("^[0-9]*$")

    team_stats = []
    stat_data = data['team_stats']['stats']['stat']
    for stat in stat_data:
        stat_name = config.STAT_ID_TO_CAT[stat['stat_id']]
        if stat_name == 'N/A':
            continue

        value = stat['value']
        if (decimal_pattern.match(value)):
            value = float(value)
        elif (counting_pattern.match(value)):
            value = int(value)

        team_stats.append(value)

    return team_stats

def all_leagues(request):
    for year in ['2015','2016','2017','2018','2019','2020','2021','2022','2023']:
        league_data = get_league('WWP Keeper Leagues', year)
        league_result = session.query(League).filter_by(league_id=league_data['league_key']).all()

        if len(league_result) == 0:
            current_week = 0
            if 'current_week' in league_data:
                current_week = league_data['current_week']

            insert_league(session,league_data['league_key'],league_data['name'],year,league_data['num_teams'],current_week)


def all_teams(request):
    for year in ['2015','2016','2017','2018','2019','2020','2021','2022','2023']:
        league_result = session.query(League).filter_by(year=year).one()
        team_result = session.query(Team).filter_by(league_id=league_result.league_id).all()

        if team_result == None or len(team_result) == 0:
            team_data = get_teams(league_result.num_of_teams,league_result.league_id)
            for data in team_data:
                print("%s %s %s" % (data['team_id'],data['name'],league_result.league_id))
                #insert_team(session,data['team_id'],data['name'],league_result.league_id)

def all_season_stats(request):
    for year in ['2015','2016','2017','2018','2019','2020','2021','2022','2023']:
        league_result = session.query(League).filter_by(year=year).one()
        team_result = session.query(Team).filter_by(league_id=league_result.league_id).all()

        if team_result == None or len(team_result) == 0:
            continue
        else:
            for team in team_result:
                data = get_team(league_result.league_id,team.team_key)
                season_results = session.query(SeasonStats).filter_by(team_id=team.id).all()
                if len(season_results) == 0:
                    insert_season_stats(session,team.id,generate_team_stats(data))
                elif len(season_results) == 1:
                    update_season_stats(session,season_results[0],generate_team_stats(data))
                else:
                    print("More than 1 season entry for a team. Probably an error.")

def all_weekly_stats(request):
    for year in ['2015','2016','2017','2018','2019','2020','2021','2022','2023']:
        league_result = session.query(League).filter_by(year=year).one()
        team_result = session.query(Team).filter_by(league_id=league_result.league_id).all()

        if team_result == None or len(team_result) == 0:
            continue
        else:
            for team in team_result:
                for week in range(1, 26):
                    weekly_results = session.query(WeekStats).filter_by(team_id=team.id,week=week).all()
                    if len(weekly_results) == 0:
                        data = get_team_weekly_stats(league_result.league_id, team.team_key, week)
                        insert_weekly_stats(session, team.id, week, generate_team_stats(data))
                    elif len(weekly_results) == 1:
                        continue
                    else:
                        print("More than 1 season entry for a team. Probably an error.")

def update_league(request):
    year = '2023'
    league_data = get_league('WWP Keeper Leagues', year)
    league_result = session.query(League).filter_by(league_id=league_data['league_key']).all()
    print(league_result)

    if len(league_result) == 1:
        update_league(session,league_result[0],league_data['name'],year,league_data['num_of_teams'],league_data['current_week'])

def season_stats(request):
    year = '2023'
    league_result = session.query(League).filter_by(year=year).one()
    team_result = session.query(Team).filter_by(league_id=league_result.league_id).all()

    if team_result == None or len(team_result) == 0:
        print("No teams found.")
    else:
        for team in team_result:
            data = get_team(league_result.league_id, team.team_key)
            season_results = session.query(SeasonStats).filter_by(team_id=team.id).all()
            if len(season_results) == 0:
                insert_season_stats(session, team.id, generate_team_stats(data))
            elif len(season_results) == 1:
                update_season_stats(session, season_results[0], generate_team_stats(data))
            else:
                print("More than 1 season entry for a team. Probably an error.")

def weekly_stats(request):
    year = '2023'
    league_result = session.query(League).filter_by(year=year).one()
    team_result = session.query(Team).filter_by(league_id=league_result.league_id).all()

    if team_result == None or len(team_result) == 0:
        print("No teams found.")
    else:
        for team in team_result:
            week = league_result.current_week
            weekly_results = session.query(WeekStats).filter_by(team_id=team.id, week=week).all()
            data = get_team_weekly_stats(league_result.league_id, team.team_key, week)
            if len(weekly_results) == 0:
                insert_weekly_stats(session, team.id, week, generate_team_stats(data))
            elif len(weekly_results) == 1:
                update_weekly_stats(session,weekly_results[0],generate_team_stats(data))
            else:
                print("More than 1 season entry for a team. Probably an error.")
