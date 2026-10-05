import re
from datetime import datetime
from decimal import Decimal, localcontext


def transform(rows):
    seen, totals, rejected = {}, {}, []
    with localcontext() as context:
        context.prec = 18 + len(str(max(1, len(rows))))
        for index, row in enumerate(rows):
            try:
                if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
                    raise ValueError("Invalid identity")
                raw_day, raw_amount = row["date"], row["amount"]
                if not isinstance(raw_day, str) or not re.fullmatch(r"[0-9]{4}([-/])[0-9]{2}\1[0-9]{2}", raw_day):
                    raise ValueError("Invalid date")
                day = datetime.strptime(raw_day.replace("/", "-"), "%Y-%m-%d").date().isoformat()
                if not isinstance(raw_amount, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", raw_amount):
                    raise ValueError("Invalid amount")
                amount = Decimal(raw_amount)
                if amount > Decimal("9999999999999999.99"):
                    raise ValueError("Amount too large")
                identity = row["id"]
                if identity in seen:
                    if seen[identity] != (day, amount):
                        raise ValueError("Conflict")
                    continue
                seen[identity] = day, amount
                totals[day] = totals.get(day, Decimal(0)) + amount
            except (ValueError, TypeError, KeyError):
                rejected.append(index)
        return {"totals": {day: format(totals[day], ".2f") for day in sorted(totals)}, "rejected": rejected[::-1]}
