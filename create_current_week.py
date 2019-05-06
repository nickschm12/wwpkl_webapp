from queries import create_week_stats

week_status = create_week_stats('2019')
if week_status:
    print "create_week_stats did not complete successfully"
