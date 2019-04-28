from flask import Flask
from yahoo_oauth import OAuth2
from apscheduler.schedulers.background import BackgroundScheduler

application = Flask(__name__)
application.config.from_object('config')
application.debug = False

scheduler = BackgroundScheduler()

oauth = OAuth2(None, None, from_file='oauth2.json')
if not oauth.token_is_valid():
    oauth.refresh_access_token()
