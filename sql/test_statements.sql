select distinct(date(timestamp)) from ph_data where strftime('%H', timestamp) = '05' and pump_on = 1 ORDER BY ID DESC LIMIT 20;
