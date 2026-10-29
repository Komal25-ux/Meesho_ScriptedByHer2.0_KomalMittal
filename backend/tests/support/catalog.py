"""A small catalog shaped like the seeded one (scripts/seed_catalog.py).

Costs are chosen to land on both sides of the pricing crossover at 350 (see
backend/core/pricing.py), so tests see both the ₹150-profit rule and the
30%-margin rule at work.
"""


def product(product_id, name, category, cost, price, sizes, colors, material, description=""):
    return {
        "product_id": product_id,
        "name": name,
        "category": category,
        "meesho_cost_inr": cost,
        "suggested_selling_price_inr": price,
        "return_window_days": 7,
        "cod_available": True,
        "description": description or f"{name} in {material}.",
        "sizes": sizes,
        "colors": colors,
        "material": material,
        "base_image_url": f"https://img.example/{product_id}.jpg",
    }


RED_SAREE = product("SKU_001", "Red Banarasi Silk Saree", "sarees", 420, 599, ["Free Size"], ["Red", "Gold"], "Banarasi Silk")
BLUE_SAREE = product("SKU_002", "Blue Georgette Saree", "sarees", 380, 549, ["Free Size"], ["Blue"], "Georgette")
YELLOW_SAREE = product("SKU_003", "Yellow Chanderi Saree", "sarees", 300, 450, ["Free Size"], ["Yellow"], "Chanderi Cotton")
PINK_KURTI = product("SKU_010", "Pink Cotton Kurti", "kurtis", 250, 399, ["S", "M", "L", "XL"], ["Pink"], "Cotton")
WHITE_KURTI = product("SKU_011", "White Chikankari Kurti", "kurtis", 500, 715, ["M"], ["White"], "Cotton")
GREEN_SUIT = product("SKU_020", "Green Anarkali Suit", "suits", 700, 1000, ["M", "L"], ["Green"], "Rayon")

CATALOG = [RED_SAREE, BLUE_SAREE, YELLOW_SAREE, PINK_KURTI, WHITE_KURTI, GREEN_SUIT]
