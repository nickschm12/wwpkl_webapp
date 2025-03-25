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
        value = stat['value']
        if value is None:
            value = '0'

        if value == '-':
            value = '0.0'

        if (decimal_pattern.match(value)):
            value = float(value)
        elif (counting_pattern.match(value)):
            value = int(value)

        team_stats.append(value)

    return team_stats

def update_league(request):
    year = '2025'
    league_data = get_league('WWP Keeper Leagues', year)
    league_result = session.query(League).filter_by(league_id=league_data['league_key']).all()
    print(league_result)

    if len(league_result) == 1:
        update_league(session,league_result[0],league_data['name'],year,league_data['num_of_teams'],league_data['current_week'])

def season_stats(request):
    year = '2025'
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
    year = '2025'
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
