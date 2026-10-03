import re
from datetime import date
from decimal import Decimal


def transform(rows):
    totals, rejected, seen = {}, [], {}
    for index, row in enumerate(rows):
        try:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
                raise ValueError("Invalid identity")
            day, amount = row["date"], row["amount"]
            if not isinstance(day, str) or not re.fullmatch(r"\d{4}([- /])\d{2}\1\d{2}", day) or " " in day:
                raise ValueError("Invalid date shape")
            day = date.fromisoformat(day.replace("/", "-")).isoformat()
            if not isinstance(amount, str) or not re.fullmatch(r"\d+(?:\.\d{1,2})?", amount):
                raise ValueError("Invalid amount")
            amount = Decimal(amount)
            identity = row["id"]
            if identity in seen:
                if seen[identity] != (day, amount):
                    raise ValueError("Conflicting identity")
                continue
            seen[identity] = (day, amount)
            totals[day] = totals.get(day, Decimal("0")) + amount
        except (ValueError, KeyError, TypeError):
            rejected.append(index)
    return {"totals": {day: f"{totals[day]:.2f}" for day in sorted(totals)}, "rejected": rejected}
