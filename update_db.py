from queries import update_season_stats,update_week_stats

season_status = update_season_stats('2019')
if season_status:
    print "update_season_stats did not complete successfully"

week_status = update_week_stats('2019')
if week_status:
    print "update_week_stats did not complete successfully"
