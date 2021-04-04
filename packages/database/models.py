from sqlalchemy import Column, String, Integer, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class League(Base):
    __tablename__ = "leagues"

    league_id = Column(String(120), unique=True, primary_key=True)
    name = Column(String(120))
    year = Column(String(120))
    num_of_teams = Column(Integer)
    current_week = Column(String(120))

class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    team_key = Column(Integer)
    name = Column(String(120))
    league_id = Column(String(120), ForeignKey('leagues.league_id'))

class SeasonStats(Base):
    __tablename__ = "season_stats"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey('teams.id'))
    runs = Column(Integer)
    hits = Column(Integer)
    homeruns = Column(Integer)
    rbis = Column(Integer)
    sb = Column(Integer)
    avg = Column(Float)
    ops = Column(Float)
    wins = Column(Integer)
    loses = Column(Integer)
    saves = Column(Integer)
    strikeouts = Column(Integer)
    holds = Column(Integer)
    era = Column(Float)
    whip = Column(Float)

class WeekStats(Base):
    __tablename__ = "week_stats"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey('teams.id'))
    week = Column(Integer)
    runs = Column(Integer)
    hits = Column(Integer)
    homeruns = Column(Integer)
    rbis = Column(Integer)
    sb = Column(Integer)
    avg = Column(Float)
    ops = Column(Float)
    wins = Column(Integer)
    loses = Column(Integer)
    saves = Column(Integer)
    strikeouts = Column(Integer)
    holds = Column(Integer)
    era = Column(Float)
    whip = Column(Float)
