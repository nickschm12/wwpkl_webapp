"""
Refresh Yahoo OAuth credentials and save a new version to GCloud Secret Manager.

Usage:
    PROJECT_ID=484894850064 YAHOO_SECRET_ID=wwpkl_yahoo YAHOO_SECRET_VERSION=7 \
    venv/bin/python scripts/refresh_yahoo_credentials.py
"""

import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from packages.yahoo.oauth import get_secrets, get_app_code, get_new_tokens
from google.cloud import secretmanager

# Step 1 — open browser for Yahoo auth
print('Opening Yahoo auth page in your browser...')
print('After logging in, Yahoo will show you a code. Copy it and paste it here.\n')
get_app_code()

app_code = input('Paste the code from Yahoo: ').strip()

# Step 2 — exchange for new tokens
print('\nFetching new tokens...')
get_new_tokens(app_code)

# Step 3 — prompt to save back to gcloud
print('\nCopy the Access Token and Refresh Token printed above.')
access_token  = input('Paste Access Token:  ').strip()
refresh_token = input('Paste Refresh Token: ').strip()

# Step 4 — build updated secret payload
secrets = get_secrets()
secrets['app_code']      = app_code
secrets['access_token']  = access_token
secrets['refresh_token'] = refresh_token

payload = json.dumps(secrets).encode('utf-8')

# Step 5 — write new version to Secret Manager
project_id = os.environ['PROJECT_ID']
secret_id  = os.environ['YAHOO_SECRET_ID']

client      = secretmanager.SecretManagerServiceClient()
secret_name = f'projects/{project_id}/secrets/{secret_id}'
response    = client.add_secret_version(
    request={'parent': secret_name, 'payload': {'data': payload}}
)
print(f'\nNew secret version created: {response.name}')
print('Done! Update YAHOO_SECRET_VERSION in app.yaml if needed.')
