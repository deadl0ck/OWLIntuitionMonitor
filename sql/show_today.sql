sqlite3 pumphouse.db "SELECT * FROM PH_DATA WHERE TIMESTAMP > DATE('now','-1 day') ORDER BY ID ASC;"
