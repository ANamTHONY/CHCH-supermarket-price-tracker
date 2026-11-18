"""Production entry point: all configured city stores, meat/eggs/milk; --test for explicit sampling."""
from production_runner import main

christchurch_stores = [
    "4a279605-eaa8-470d-bcd4-0a9e3c9ab43b",
    "61dd754e-8525-4b9e-9e08-173389eea8a8",
    "8cd700ae-d96f-4761-bd7a-805d6b93536d",
    "be4c4780-218e-425a-a90f-63e21773572b",
    "dbca5e00-f7f9-43ae-91de-031ad16f8a92"
]

categories = [
    {"name": "Egg", "path": "fresh-foods-and-bakery/dairy--eggs/eggs"},
    {"name": "Milk", "path": "fresh-foods-and-bakery/dairy--eggs/fresh-milk"},
    {"name": "Meat", "path": "fresh-foods-and-bakery/butchery/fresh-beef--lamb"}
]

if __name__ == "__main__":
    main(source="paknsave")
