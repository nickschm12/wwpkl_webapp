CURRENT_YEAR = '2026'
PLAYOFF_WEEK_START = 23

# Yahoo gives a stat id and not a stat name so this dictionary maps the stat id to the stat name
STAT_ID_TO_CAT = {
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

COLUMNS = ['R','H','HR','RBI','SB','AVG','OPS','IP','W','L','SV','SO','HLD','ERA','WHIP']

# Maps any team name or name variant to a canonical real-person name.
# Unmapped names (one-off early players, unknowns) pass through as-is.
NAME_MAP = {
    # Fantasy team names → real names
    "Alan's Liang":          'Jared Rubenstein',
    'The Bigots':            'Jason Light',
    'Boogie Down Boyz':      'Ryan Phelan',
    'Hello':                 'Alan Liang',
    "Paddy's Pub":           'Ryan Billek',
    "Ms. Dean's Lean":       'Drew Kenavan',
    "Jobu's Rum":            'Paul Thompson',
    'Task Unit Bruiser':     'Jon Squeri',
    'AngelsInTheOutfield':   'Chris Campbell',
    'Ethan Alan':            'Andy Vogt',
    'Ethañ Alañ':            'Andy Vogt',
    "Ethan's Team":          'Andy Vogt',
    'Ethan Exotic':          'Andy Vogt',
    'Cedric M. Diggory':     'Andy Vogt',
    'Omar Manaea':           'Andy Vogt',
    'Bad News Kolbears':     'Steve Kolber',
    'Harry Highpants':       'Ethan Kaye',
    'Whit or WITTout':       'Ethan Kaye',
    'Shmohawks':             'Nick Schmidt',
    'ThanksForNothingDan':   'Zack Donohue',
    'Eckstein123':           'Mike Voltmer',
    "Miller Lite's":         'Chris Campbell',
    'Dangerous Nights Crew': 'Jon Squeri',
    'CPLL All-Stars':        'Ralph Aurora',
    "Hailey's Dad's Team":            'Ethan Kaye',
    "Roy Donk's Colgate Comedy Hour": 'Ethan Kaye',
    'JG Wentworth 877 GLAS-NOW':      'Ralph Aurora',
    # Name variants / typos in pre-2015 data
    'Ethan':                 'Ethan Kaye',
    'Drew Kenevan':          'Drew Kenavan',
    'Dan Brezyznski':        'Dan Brezynski',
    'Dan Brezyznksi':        'Dan Brezynski',
}

# H2H regular season champion and playoff champion by year (2020 omitted — shortened season)
# All entries use real person names (applied via NAME_MAP for post-2015 team names)
CHAMPIONS = {
    '2006': {'h2h_champion': 'Jason Light',    'playoff_champion': 'Jason Light'},
    '2007': {'h2h_champion': 'Ryan Billek',    'playoff_champion': 'Ethan Kaye'},
    '2008': {'h2h_champion': 'Alan Liang',     'playoff_champion': 'Mike Voltmer'},
    '2009': {'h2h_champion': 'Alan Liang',     'playoff_champion': 'Imran Hossain'},
    '2010': {'h2h_champion': 'Alan Liang',     'playoff_champion': 'Alan Liang'},
    '2011': {'h2h_champion': 'Alan Liang',     'playoff_champion': 'Drew Kenavan'},
    '2012': {'h2h_champion': 'Nick Schmidt',   'playoff_champion': 'Alan Liang'},
    '2013': {'h2h_champion': 'Alan Liang',     'playoff_champion': 'Drew Kenavan'},
    '2014': {'h2h_champion': 'Ethan Kaye',     'playoff_champion': 'Ethan Kaye'},
    '2015': {'h2h_champion': 'Drew Kenavan',   'playoff_champion': 'Alan Liang'},
    '2016': {'h2h_champion': 'Alan Liang',     'playoff_champion': 'Alan Liang'},
    '2017': {'h2h_champion': 'Ryan Billek',    'playoff_champion': 'Ryan Billek'},
    '2018': {'h2h_champion': 'Alan Liang',     'playoff_champion': 'Alan Liang'},
    '2019': {'h2h_champion': 'Alan Liang',     'playoff_champion': 'Alan Liang'},
    '2020': {'h2h_champion': None,             'playoff_champion': None},
    '2021': {'h2h_champion': 'Jon Squeri',     'playoff_champion': 'Ryan Billek'},
    '2022': {'h2h_champion': 'Drew Kenavan',   'playoff_champion': 'Andy Vogt'},
    '2023': {'h2h_champion': 'Alan Liang',     'playoff_champion': 'Alan Liang'},
    '2024': {'h2h_champion': 'Nick Schmidt',   'playoff_champion': 'Jason Light'},
    '2025': {'h2h_champion': 'Nick Schmidt',   'playoff_champion': 'Alan Liang'},
}
