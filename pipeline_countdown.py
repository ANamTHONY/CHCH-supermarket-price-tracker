"""Production entry point: all configured city stores, meat/eggs/milk; --test for explicit sampling."""
from production_runner import main

store_map = { "001": "Woolworths Avonhead",
             "002": "Woolworths Ashburton",
             "003": "Woolworths Northlands",
             "004": "Woolworths Belfast",
             "005": "Woolworths Christchurch Airport",
             "006": "Woolworths Church Corner",
             "007": "Woolworths Colombo St",
             "008": "Woolworths Eastgate",
             "009": "Woolworths Ferrymead",
             "010": "Woolworths Hornby",
             "011": "Woolworths Moorhouse Ave",
             "012": "Woolworths New Brighton",
             "013": "Woolworths The Palms"
             }

categories = [
    {"name": "Egg", "url": "https://www.woolworths.co.nz/shop/browse/pantry/eggs"},
    {"name": "Milk", "url": "https://www.woolworths.co.nz/shop/browse/fridge-deli/milk/full-cream-milk"},
    {"name": "Milk", "url": "https://www.woolworths.co.nz/shop/browse/fridge-deli/milk/trim-light-milk"},
    {"name": "Meat", "url": "https://www.woolworths.co.nz/shop/browse/meat-poultry/beef"},
    {"name": "Meat", "url": "https://www.woolworths.co.nz/shop/browse/meat-poultry/lamb"}
]

if __name__ == "__main__":
    main(source="woolworths")
