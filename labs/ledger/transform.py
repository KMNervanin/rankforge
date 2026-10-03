def transform(rows):
    totals = {}
    for row in rows:
        day = row["date"]
        totals[day] = str(float(totals.get(day, 0)) + float(row["amount"]))
    return {"totals": totals, "rejected": []}
