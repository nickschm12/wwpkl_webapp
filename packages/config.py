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

# H2H regular season champion and playoff champion by year (2020 omitted — shortened season)
CHAMPIONS = {
    '2015': {'h2h_champion': "Ms. Dean's Lean", 'playoff_champion': 'Hello'},
    '2016': {'h2h_champion': 'Hello',            'playoff_champion': 'Hello'},
    '2017': {'h2h_champion': "Paddy's Pub",      'playoff_champion': "Paddy's Pub"},
    '2018': {'h2h_champion': 'Hello',            'playoff_champion': 'Hello'},
    '2019': {'h2h_champion': 'Hello',            'playoff_champion': 'Hello'},
    '2020': {'h2h_champion': None,               'playoff_champion': None},
    '2021': {'h2h_champion': 'Task Unit Bruiser','playoff_champion': "Paddy's Pub"},
    '2022': {'h2h_champion': "Ms. Dean's Lean",  'playoff_champion': 'Omar Manaea'},
    '2023': {'h2h_champion': 'Hello',            'playoff_champion': 'Hello'},
    '2024': {'h2h_champion': 'Shmohawks',        'playoff_champion': 'The Bigots'},
    '2025': {'h2h_champion': 'Shmohawks',        'playoff_champion': 'Hello'},
}
