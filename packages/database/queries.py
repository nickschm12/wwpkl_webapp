import pandas as pd
from sqlalchemy.orm import sessionmaker

from .models import League, Team, SeasonStats, WeekStats

def insert_league(session,league_id,name,year,num_of_teams,current_week):
    league = League(
        league_id=league_id,
        name=name,
        year=year,
        num_of_teams=num_of_teams,
        current_week=current_week
    )
    session.add(league)
    session.commit()

def update_league(session,league,name,year,num_of_teams,current_week):
    league.name = name
    league.year = year
    league.num_of_teams = num_of_teams
    league.current_week = current_week
    session.merge(league)
    session.commit()

def insert_team(session,team_key,name,league_id):
    team = Team(
        team_key=team_key,
        name=name,
        league_id=league_id
    )
    session.add(team)
    session.commit()

def update_team_name(session,team,name):
    team.name = name
    session.merge(team)
    session.commit()

def get_teams(session,year):
    return session.query(Team).join(League, Team.league_id == League.league_id).filter(League.year == year).all()


def insert_season_stats(session,team_id,stats):
    season_stats = SeasonStats(
        team_id=team_id,
        runs=stats[0],
        hits=stats[1],
        homeruns=stats[2],
        rbis=stats[3],
        sb=stats[4],
        avg=stats[5],
        ops=stats[6],
        wins=stats[8],
        loses=stats[9],
        saves=stats[10],
        strikeouts=stats[11],
        holds=stats[12],
        era=stats[13],
        whip=stats[14],
    )
    session.add(season_stats)
    session.commit()

def update_season_stats(session,season_stats,stats):
    season_stats.runs = stats[0]
    season_stats.hits = stats[1]
    season_stats.homeruns = stats[2]
    season_stats.rbis = stats[3]
    season_stats.sb = stats[4]
    season_stats.avg = stats[5]
    season_stats.ops = stats[6]
    season_stats.wins = stats[8]
    season_stats.loses = stats[9]
    season_stats.saves = stats[10]
    season_stats.strikeouts = stats[11]
    season_stats.holds = stats[12]
    season_stats.era = stats[13]
    season_stats.whip = stats[14]

    session.merge(season_stats)
    session.commit()

def get_season_stats(engine, year):
    query = str.format("select teams.name,season_stats.* from (season_stats join teams on season_stats.team_id = teams.id)" \
            " join leagues on teams.league_id = leagues.league_id where leagues.year = '{0}'", year)
    data_frame = pd.read_sql_query(query, con=engine)
    return data_frame

def insert_weekly_stats(session,team_id,week,stats):
    week_stats = WeekStats(
        team_id=team_id,
        week=week,
        runs=stats[0],
        hits=stats[1],
        homeruns=stats[2],
        rbis=stats[3],
        sb=stats[4],
        avg=stats[5],
        ops=stats[6],
        wins=stats[8],
        loses=stats[9],
        saves=stats[10],
        strikeouts=stats[11],
        holds=stats[12],
        era=stats[13],
        whip=stats[14],
    )
    session.add(week_stats)
    session.commit()


def update_weekly_stats(session, week_stats, stats):
    week_stats.runs = stats[0]
    week_stats.hits = stats[1]
    week_stats.homeruns = stats[2]
    week_stats.rbis = stats[3]
    week_stats.sb = stats[4]
    week_stats.avg = stats[5]
    week_stats.ops = stats[6]
    week_stats.wins = stats[8]
    week_stats.loses = stats[9]
    week_stats.saves = stats[10]
    week_stats.strikeouts = stats[11]
    week_stats.holds = stats[12]
    week_stats.era = stats[13]
    week_stats.whip = stats[14]

    session.merge(week_stats)
    session.commit()

def get_week_stats(engine, year, week):
    query = str.format("select t.name, w.* from (week_stats as w join teams as t on w.team_id = t.id) join "
                       "leagues as l on t.league_id = l.league_id where l.year = '{0}' and w.week = '{1}'", year, week)
    data_frame = pd.read_sql_query(query, con=engine)
    return data_frame
