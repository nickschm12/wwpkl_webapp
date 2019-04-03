from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from queries import get_team_stats,calculate_roto_standings
import pandas as pd


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://localhost/wwpkl'
db = SQLAlchemy(app)

@app.route('/')
def index():
    columns = ['Team','R', 'H', 'HR', 'RBI', 'SB', 'AVG', 'OPS','Batting Rank',
               'W', 'L', 'SV', 'SO', 'HLD', 'ERA', 'WHIP', 'Pitching Rank',
               'Total Rank']
    stats = get_team_stats('2019')
    roto = calculate_roto_standings(stats)
    roto.columns = columns
    return render_template('index.html', tables=[roto.to_html(index=False, classes=['table-striped','table'])])

if __name__ == '__main__':
    app.run()