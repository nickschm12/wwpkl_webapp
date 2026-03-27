import logging
import os
import re
from sqlalchemy.orm import sessionmaker

from packages.yahoo.api import get_league, get_team, get_team_weekly_stats
from packages.database.models import Base, League, Team, SeasonStats, WeekStats
from packages.database import queries
from packages.database.connections import tcp_connection, unix_connection
import packages.config as config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

if os.environ.get("DB_HOST"):
    engine = tcp_connection()
else:
    engine = unix_connection()

Base.metadata.bind = engine
session = sessionmaker(bind=engine)()


def generate_team_stats(data):
    decimal_pattern = re.compile(r"^-?[0-9]?\.[0-9]*$")
    counting_pattern = re.compile(r"^[0-9]*$")

    team_stats = []
    for stat in data['team_stats']['stats']['stat']:
        stat_name = config.STAT_ID_TO_CAT[stat['stat_id']]
        if stat_name == 'N/A':
            continue

        value = stat['value']
        if value is None or value == '-':
            value = '0'

        if decimal_pattern.match(value):
            value = float(value)
        elif counting_pattern.match(value):
            value = int(value)

        team_stats.append(value)

    return team_stats


def init_season(request):
    """Create League and Team rows for CURRENT_YEAR. Run once at the start of each season."""
    year = config.CURRENT_YEAR
    log.info(f"Initializing season {year}")

    league_data = get_league('WWP Keeper Leagues', year)
    if not league_data:
        log.error(f"Could not find Yahoo league for year {year}")
        return f"League not found for {year}", 500

    league_key = league_data['league_key']
    num_teams = int(league_data.get('num_teams', league_data.get('num_of_teams', 12)))

    existing_league = session.query(League).filter_by(league_id=league_key).first()
    if existing_league:
        log.info(f"League {league_key} already exists — updating metadata")
        queries.update_league(session, existing_league, league_data['name'], year,
                              num_teams, league_data['current_week'])
    else:
        log.info(f"Creating league {league_key}")
        queries.insert_league(session, league_key, league_data['name'], year,
                              num_teams, league_data['current_week'])

    for team_key in range(1, num_teams + 1):
        team_data = get_team(league_key, team_key)
        team_name = team_data[0]['name']
        existing_team = session.query(Team).filter_by(league_id=league_key, team_key=team_key).first()
        if existing_team:
            log.info(f"  Team {team_key} already exists: {existing_team.name}")
        else:
            log.info(f"  Creating team {team_key}: {team_name}")
            queries.insert_team(session, team_key, team_name, league_key)

    return f"Season {year} initialized", 200


def update_league_meta(request):
    """Update current_week and metadata for the current season. Run on a regular cadence."""
    year = config.CURRENT_YEAR
    league_data = get_league('WWP Keeper Leagues', year)
    if not league_data:
        log.error(f"Could not find Yahoo league for year {year}")
        return "League not found", 500

    league = session.query(League).filter_by(league_id=league_data['league_key']).first()
    if not league:
        log.error("League not in DB — run init_season first")
        return "League not in DB", 500

    queries.update_league(session, league, league_data['name'], year,
                          league.num_of_teams, league_data['current_week'])
    log.info(f"League metadata updated — current week: {league_data['current_week']}")
    return "OK", 200


def season_stats(request):
    """Update cumulative season stats for all teams. Run on a regular cadence."""
    year = config.CURRENT_YEAR
    league = session.query(League).filter_by(year=year).one()
    teams = session.query(Team).filter_by(league_id=league.league_id).all()

    if not teams:
        log.error("No teams found — run init_season first")
        return "No teams found", 500

    errors = []
    for team in teams:
        try:
            data = get_team(league.league_id, team.team_key)
            stats = generate_team_stats(data)
            existing = session.query(SeasonStats).filter_by(team_id=team.id).all()
            if len(existing) == 0:
                queries.insert_season_stats(session, team.id, stats)
            elif len(existing) == 1:
                queries.update_season_stats(session, existing[0], stats)
            else:
                log.warning(f"Multiple season entries for {team.name} — skipping")
                continue
            log.info(f"  Updated season stats: {team.name}")
        except Exception as e:
            log.error(f"  Failed for {team.name}: {e}")
            errors.append(team.name)

    if errors:
        return f"Completed with errors: {errors}", 207
    return "OK", 200


def weekly_stats(request):
    """Update stats for the current week for all teams. Run on a regular cadence."""
    year = config.CURRENT_YEAR
    league = session.query(League).filter_by(year=year).one()
    teams = session.query(Team).filter_by(league_id=league.league_id).all()

    if not teams:
        log.error("No teams found — run init_season first")
        return "No teams found", 500

    week = league.current_week
    log.info(f"Updating week {week} stats")

    errors = []
    for team in teams:
        try:
            data = get_team_weekly_stats(league.league_id, team.team_key, week)
            stats = generate_team_stats(data)
            existing = session.query(WeekStats).filter_by(team_id=team.id, week=week).all()
            if len(existing) == 0:
                queries.insert_weekly_stats(session, team.id, week, stats)
            elif len(existing) == 1:
                queries.update_weekly_stats(session, existing[0], stats)
            else:
                log.warning(f"Multiple week entries for {team.name} week {week} — skipping")
                continue
            log.info(f"  Updated week {week} stats: {team.name}")
        except Exception as e:
            log.error(f"  Failed for {team.name}: {e}")
            errors.append(team.name)

    if errors:
        return f"Completed with errors: {errors}", 207
    return "OK", 200
