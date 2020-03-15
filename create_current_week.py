from queries import create_week_stats,set_current_week

set_current_week('2020')

week_status = create_week_stats('2020')
if week_status:
    print "create_week_stats did not complete successfully"
