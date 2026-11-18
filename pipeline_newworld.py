"""Production entry point: all configured city stores, meat/eggs/milk; --test for explicit sampling."""
from production_runner import main

christchurch_stores = [
    "3ee7214b-6df4-4fdb-9dd6-3b2fc252ba6b"
    # , "95d161ea-9a31-4fca-acbe-96f271d627df",
    # "c6abac35-b75f-4a02-9b43-7ad5a7c7aa37","81f807e9-1879-484c-b27e-ded56245c6a4", "c1aaac72-38c0-4cc0-ad05-f241047d88c5",
    # "b3158cd8-72b9-40e5-8c4e-abd43c1be305", "bae1da58-ac6b-4ef2-816d-4932691218d1",
    # "a0d86b5f-fdf4-44d1-b7a2-f418bdb37f4e", "fc91d59f-6ab5-4447-8737-125e09e8e50e",
    # "0637c08c-ac36-4940-8582-38e44a4812fa", "bfe3a4ae-2f6d-46ed-ba60-28451a4807bf",
    # "bfe3a4ae-2f6d-46ed-ba60-28451a4807bf", "bfe3a4ae-2f6d-46ed-ba60-28451a4807bf"

]

categories = [
    {"name": "Egg", "path": "fresh-foods-and-bakery/dairy--eggs/eggs"},
    {"name": "Milk", "path": "fresh-foods-and-bakery/dairy--eggs/fresh-milk"},
    {"name": "Meat", "path": "fresh-foods-and-bakery/butchery/fresh-beef--lamb"},
]

if __name__ == "__main__":
    main(source="newworld")
