from flask import Flask, render_template
from app import application,scheduler
from queries import get_season_stats,update_season_stats,calculate_roto_standings
import pandas as pd

scheduler.add_job(func=update_season_stats, args=['2019'], trigger="interval", minutes=10)
scheduler.start()

@application.route('/')
def index():
    columns = ['Team','R', 'H', 'HR', 'RBI', 'SB', 'AVG', 'OPS','Batting Rank',
               'W', 'L', 'SV', 'SO', 'HLD', 'ERA', 'WHIP', 'Pitching Rank',
               'Total Rank']
    stats = get_season_stats('2019')
    roto = calculate_roto_standings(stats)
    roto.columns = columns
    return render_template('index.html', tables=[roto.to_html(index=False, classes=['table-striped','table'])])

if __name__ == '__main__':
    application.run()
