from recover import recover

archive = [
    {"id": "a", "item": "power-cell", "quantity": 4},
    {"id": "b", "item": "coolant", "quantity": 2},
    {"id": "a", "item": "power-cell", "quantity": 4},
]
print(recover("restored.sqlite", archive))
