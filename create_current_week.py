from queries import create_week_stats,set_current_week

set_current_week('2019')

week_status = create_week_stats('2019')
if week_status:
    print "create_week_stats did not complete successfully"
