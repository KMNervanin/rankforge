import re
from datetime import date


def transform(rows):
    totals, rejected, seen = {}, [], {}
    for index, row in enumerate(rows):
        try:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
                raise ValueError("Invalid identity")
            day, amount = row["date"], row["amount"]
            if not isinstance(day, str) or not re.fullmatch(r"[0-9]{4}([-/])[0-9]{2}\1[0-9]{2}", day):
                raise ValueError("Invalid date shape")
            day = date.fromisoformat(day.replace("/", "-")).isoformat()
            if not isinstance(amount, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", amount):
                raise ValueError("Invalid amount")
            whole, _, fraction = amount.partition(".")
            whole = whole.lstrip("0") or "0"
            if len(whole) > 16:
                raise ValueError("Amount exceeds 9999999999999999.99")
            amount = int(whole) * 100 + int(fraction.ljust(2, "0"))
            identity = row["id"]
            if identity in seen:
                if seen[identity] != (day, amount):
                    raise ValueError("Conflicting identity")
                continue
            seen[identity] = (day, amount)
            totals[day] = totals.get(day, 0) + amount
        except (ValueError, KeyError, TypeError):
            rejected.append(index)
    return {"totals": {day: f"{totals[day] // 100}.{totals[day] % 100:02d}" for day in sorted(totals)}, "rejected": rejected}
