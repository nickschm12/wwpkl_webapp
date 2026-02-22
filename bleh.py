"""
Dev script to fetch 2026 league info from Yahoo Fantasy API.
Reads credentials directly from creds/yahoo.json (no Secret Manager needed).
"""
import base64
import json
import requests
import xmltodict

with open('creds/yahoo.json') as f:
    creds = json.load(f)

BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"
OAUTH_URL = "https://api.login.yahoo.com/"

def yahoo_get(url, access_token):
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    response = requests.get(url, headers=headers)
    if response.ok:
        return json.loads(json.dumps(xmltodict.parse(response.text))), None
    return None, response

def refresh_access_token(creds):
    encoded = base64.b64encode(f"{creds['client_id']}:{creds['client_secret']}".encode()).decode()
    response = requests.post(
        OAUTH_URL + 'oauth2/get_token',
        headers={
            'Authorization': f'Basic {encoded}',
            'Content-Type': 'application/x-www-form-urlencoded'
        },
        data={
            'grant_type': 'refresh_token',
            'redirect_uri': 'oob',
            'code': creds['app_code'],
            'refresh_token': creds['refresh_token']
        }
    )
    if response.ok:
        return response.json()['access_token']
    print("Could not refresh token:", response.text)
    return None

# Always refresh first since the stored access token is likely stale
print("Refreshing Yahoo access token...")
access_token = refresh_access_token(creds)
if not access_token:
    exit(1)

# Fetch all leagues
url = f'{BASE_URL}/users;use_login=1/games;game_codes=mlb/leagues'
data, err = yahoo_get(url, access_token)
if err is not None:
    print("Failed to fetch leagues:", err.text)
    exit(1)

# Find the 2026 league
seasons = data['fantasy_content']['users']['user']['games']['game']
league = None
for season in seasons:
    for l in season['leagues']['league']:
        if type(l) is dict and 'WWP Keeper Leagues' in l['name'] and '2026' in l['season']:
            league = l

if not league:
    print("No 2026 league found. The league may not be set up in Yahoo yet.")
else:
    league_key = league['league_key']
    print(f"League key:   {league_key}")
    print(f"League name:  {league['name']}")
    print(f"Num teams:    {league['num_teams']}")
    print(f"Current week: {league['current_week']}")
    print()
    print("Teams:")
    for team_key in range(1, int(league['num_teams']) + 1):
        data, err = yahoo_get(f'{BASE_URL}/team/{league_key}.t.{team_key}/stats', access_token)
        if data:
            team = data['fantasy_content']['team']
            # Pre-draft: flat dict. In-season: list where [0] has metadata.
            team_name = team['name'] if isinstance(team, dict) else team[0]['name']
            print(f"  {team_key}: {team_name}")
