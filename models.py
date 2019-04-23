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

    def __init__(self, league_id, name, year, num_of_teams):
        self.league_id = league_id
        self.name = name
        self.year = year
        self.num_of_teams = num_of_teams

class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True)
    team_key = Column(Integer)
    name = Column(String(120))
    league_id = Column(String(120), ForeignKey('leagues.league_id'))
    league = relationship("League", backref="teams")

    def __init__(self, team_key, name, league):
        self.team_key = team_key
        self.name = name
        self.league = league

class SeasonStats(Base):
    __tablename__ = "season_stats"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey('teams.id'))
    team = relationship("Team", backref="season_stats")
    runs = Column(Integer)
    hits = Column(Integer)
    homeruns = Column(Integer)
    rbis = Column(Integer)
    stolen_bases = Column(Integer)
    avg = Column(Float)
    ops = Column(Float)
    wins = Column(Integer)
    loses = Column(Integer)
    saves = Column(Integer)
    strikeouts = Column(Integer)
    holds = Column(Integer)
    era = Column(Float)
    whip = Column(Float)

    def __init__(self, league, team):
        self.league = league
        self.team = team
        self.runs = 0
        self.hits = 0
        self.homeruns = 0
        self.rbis = 0
        self.stolen_bases = 0
        self.avg = 0.000
        self.ops = 0.000
        self.wins = 0
        self.loses = 0
        self.saves = 0
        self.strikeouts = 0
        self.holds = 0
        self.era = 0.000
        self.whip = 0.000

class WeekStats(Base):
    __tablename__ = "week_stats"

    id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey('teams.id'))
    team = relationship("Team", backref="week_stats")
    week = Column(Integer)
    runs = Column(Integer)
    hits = Column(Integer)
    homeruns = Column(Integer)
    rbis = Column(Integer)
    stolen_bases = Column(Integer)
    avg = Column(Float)
    ops = Column(Float)
    wins = Column(Integer)
    loses = Column(Integer)
    saves = Column(Integer)
    strikeouts = Column(Integer)
    holds = Column(Integer)
    era = Column(Float)
    whip = Column(Float)

    def __init__(self, league, team, week):
        self.league = league
        self.team = team
        self.week = week
        self.runs = 0
        self.hits = 0
        self.homeruns = 0
        self.rbis = 0
        self.stolen_bases = 0
        self.avg = 0.000
        self.ops = 0.000
        self.wins = 0
        self.loses = 0
        self.saves = 0
        self.strikeouts = 0
        self.holds = 0
        self.era = 0.000
        self.whip = 0.000