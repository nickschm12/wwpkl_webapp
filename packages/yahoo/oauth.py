# https://joinative.com/yahoo-gemini-api-oauth-authentication-python

import base64
from google.cloud import secretmanager
import json
import os
from requests import get, post
import webbrowser
import xmltodict

base_url = 'https://api.login.yahoo.com/'

project_id = os.environ.get('PROJECT_ID')
yahoo_secret_id = os.environ.get('YAHOO_SECRET_ID')
yahoo_secret_version = os.environ.get('YAHOO_SECRET_VERSION')

def get_secrets():
    client = secretmanager.SecretManagerServiceClient()

    name = f"projects/{project_id}/secrets/{yahoo_secret_id}/versions/{yahoo_secret_version}"

    response = client.access_secret_version(request={"name": name})
    payload = response.payload.data.decode("UTF-8")
    return json.loads(payload)

# function to grab the app code from yahoo if it ever expires
def get_app_code():
    secrets = get_secrets()
    code_url = "oauth2/request_auth?client_id={}&redirect_uri=oob&response_type=code&language=en-us".format(secrets['client_id'])
    webbrowser.open(base_url + code_url)

# if the refresh token expires, query yahoo for a new full set of credentials and update the credentials file
def get_new_tokens(app_code):
    #secrets = get_secrets()

    encoded = base64.b64encode((secrets['client_id'] + ':' + secrets['client_secret']).encode("utf-8"))

    headers = {
        'Authorization': f'Basic {encoded.decode("utf-8")}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = {
        'grant_type': 'authorization_code',
        'redirect_uri': 'oob',
        'code': app_code
    }
    response = post(base_url + 'oauth2/get_token', headers=headers, data=data)

    if response.ok:
        print("Access Token: {}".format(response.json()['access_token']))
        print("Refresh Token: {}".format(response.json()['refresh_token']))
    else:
        print("Could not retrieve new tokens!")
        print(response.text)

# if the access token expires use the refresh token to get a new one and update the credentials file
def refresh_access_token():
    secrets = get_secrets()

    encoded = base64.b64encode((secrets['client_id'] + ':' + secrets['client_secret']).encode("utf-8"))

    headers = {
        'Authorization': f'Basic {encoded.decode("utf-8")}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = {
        'grant_type': 'refresh_token',
        'redirect_uri': 'oob',
        'code': secrets['app_code'],
        'refresh_token': secrets['refresh_token']
    }

    response = post(base_url + 'oauth2/get_token', headers=headers, data=data)

    if response.ok:
        return response.json()['access_token']
    else:
        print("Could not refresh access token!")
        print(response.text)