import os
import sys
import time
from dotenv import load_dotenv
from supabase import create_client

# Load variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ── PHONETIC TRANSLITERATION HELPER ───────────────────────────
# Every product name in this file is a plain space-separated sequence of the
# English fashion vocabulary below (colors, materials, garment types,
# adjectives) - so a per-word lookup table is enough to build a consistent
# phonetic Devanagari rendering of any name, without hand-typing 100
# individual translations (error-prone) or attempting real machine
# translation (would translate meaning, not the required phonetic sound).
WORD_MAP = {
    # Colors
    "Yellow": "येलो", "Red": "रेड", "Blue": "ब्लू", "Green": "ग्रीन", "Pink": "पिंक",
    "Black": "ब्लैक", "White": "व्हाइट", "Orange": "ऑरेंज", "Purple": "पर्पल",
    "Maroon": "मरून", "Beige": "बेज", "Gold": "गोल्ड", "Silver": "सिल्वर",
    "Mint": "मिंट", "Peach": "पीच", "Navy": "नेवी", "Crimson": "क्रिमसन",
    "Emerald": "एमराल्ड", "Royal": "रॉयल", "Wine": "वाइन", "Blush": "ब्लश",
    "Sky": "स्काई", "Multicolor": "मल्टीकलर", "Rani": "रानी", "Grey": "ग्रे",
    "Mustard": "मस्टर्ड", "Coral": "कोरल", "Turquoise": "टर्कोइज़", "Ivory": "आइवरी",
    "Magenta": "मैजेंटा", "Lavender": "लैवेंडर", "Denim": "डेनिम", "Teal": "टील",
    # Materials / fabrics
    "Banarasi": "बनारसी", "Silk": "सिल्क", "Chanderi": "चंदेरी", "Cotton": "कॉटन",
    "Georgette": "जॉर्जेट", "Organza": "ऑर्गेंज़ा", "Bandhani": "बांधनी", "Net": "नेट",
    "Chiffon": "शिफॉन", "Kanjeevaram": "कांजीवरम", "Linen": "लिनन", "Blend": "ब्लेंड",
    "Chikankari": "चिकनकारी", "Rayon": "रेयॉन", "Velvet": "वेलवेट", "Crepe": "क्रेप",
    "Satin": "सैटिन", "Embroidered": "एम्ब्रॉयडर्ड", "Sequined": "सीक्विन्ड",
    "Floral": "फ्लोरल", "Print": "प्रिंट", "Wrap": "रैप", "Bodycon": "बॉडीकॉन",
    "Sundress": "सनड्रेस", "Palazzo": "पलाज़ो", "Shirt": "शर्ट",
    # Garment types / structure
    "Saree": "साड़ी", "Kurti": "कुर्ती", "Kurta": "कुर्ता", "Suit": "सूट",
    "Anarkali": "अनारकली", "Top": "टॉप", "Dress": "ड्रेस", "Lehenga": "लहंगा",
    "Set": "सेट", "Material": "मटेरियल", "and": "और", "Pant": "पैंट",
    # Adjectives
    "Basic": "बेसिक", "Premium": "प्रीमियम", "Grand": "ग्रैंड", "Designer": "डिज़ाइनर",
    "A-Line": "ए-लाइन", "Bridal": "ब्राइडल",
}

def transliterate(name: str) -> str:
    return " ".join(WORD_MAP.get(word, word) for word in name.split(" "))

# ── CATALOG GENERATION (Dense Cluster Strategy) ───────────────
# Not 100 random items - deliberately structured so RAG search demos work:
#   1. Cross-Category Color Clashing: 8 distinct "Yellow" items spread across
#      different categories/materials (sarees, kurtis, suits, tops, lehengas,
#      dresses) - marked YELLOW CLUSTER below.
#   2. Deep Style Variations: 3 flagship items (one saree, one suit, one
#      kurti) with rich colors[] (4-5 options) and full sizes[] arrays -
#      marked FLAGSHIP below.
#   3. Price Tiering: basic vs premium pairs within the same category -
#      marked PRICE TIER below.
#   4. Every description ends with "(<Devanagari transliteration of name>)".
_SAREE_OCCASIONS = [
    "wedding season and festive celebrations", "Haldi ceremonies and daytime rituals",
    "family functions and traditional pujas", "festive gatherings and cultural events",
    "evening parties and receptions", "Karwa Chauth and religious ceremonies",
]
_KURTI_OCCASIONS = [
    "daily wear and college outings", "office wear and casual meetups",
    "summer daywear and brunch dates", "festive daywear and family visits",
    "casual outings paired with jeans or palazzos",
]
_SUIT_OCCASIONS = [
    "festive occasions and family functions", "office wear and daytime events",
    "wedding functions and receptions", "casual daywear and outings",
]
_TOP_OCCASIONS = [
    "college outings and casual daywear", "office wear and evening plans",
    "date nights and parties", "everyday casual styling",
]
_LEHENGA_OCCASIONS = [
    "wedding functions and sangeet nights", "festive celebrations and receptions",
    "engagement ceremonies and parties",
]
_DRESS_OCCASIONS = [
    "parties and date nights", "office-to-evening styling",
    "brunches and casual outings", "festive western styling",
]

def _desc(lead: str, occasions: list, idx: int, name: str) -> str:
    occasion = occasions[idx % len(occasions)]
    return f"{lead} Perfect for {occasion}. ({transliterate(name)})"

def build_catalog() -> list:
    products = []
    sku = 0

    def add(name, category, price, cost, sizes, colors, material, lead, occasions, cod=True, window=7):
        nonlocal sku
        sku += 1
        products.append({
            "product_id": f"SKU_{sku:03d}",
            "name": name,
            "category": category,
            "suggested_selling_price_inr": price,
            "meesho_cost_inr": cost,
            "return_window_days": window,
            "cod_available": cod,
            "description": _desc(lead, occasions, sku, name),
            "sizes": sizes,
            "colors": colors,
            "material": material,
            "base_image_url": f"https://picsum.photos/seed/SKU_{sku:03d}/600/400",
        })

    O = _SAREE_OCCASIONS
    add("Yellow Banarasi Silk Saree", "sarees", 1299, 890, ["Free Size"], ["Yellow", "Gold"], "Banarasi Silk",
        "Vibrant yellow Banarasi silk saree with a rich gold zari border.", O)  # YELLOW CLUSTER
    add("Royal Banarasi Silk Saree", "sarees", 1499, 1050,
        ["Free Size"], ["Crimson Red", "Emerald Green", "Royal Gold", "Royal Blue", "Wine Maroon"], "Banarasi Silk",
        "Our flagship Banarasi silk saree, woven in five rich colourways with a heavy zari border.", O)  # FLAGSHIP
    add("Red Banarasi Silk Saree", "sarees", 899, 620, ["Free Size"], ["Red", "Gold"], "Banarasi Silk",
        "Elegant red Banarasi silk saree with gold zari borders.", O)
    add("Yellow Chanderi Cotton Saree", "sarees", 699, 480, ["Free Size"], ["Yellow", "Silver"], "Chanderi Cotton",
        "Vibrant yellow Chanderi cotton saree with a silver border.", O)  # YELLOW CLUSTER
    add("Green Chanderi Cotton Saree", "sarees", 649, 440, ["Free Size"], ["Green", "Silver"], "Chanderi Cotton",
        "Fresh green Chanderi cotton saree with a silver border, light and breathable.", O)
    add("Blue Georgette Saree", "sarees", 499, 340, ["Free Size"], ["Blue"], "Georgette",
        "Lightweight blue georgette saree with a soft drape, easy to style.", O)
    add("Floral Organza Saree Pink", "sarees", 799, 550, ["Free Size"], ["Pink"], "Organza",
        "Trending lightweight organza saree in pastel pink with large floral prints.", O)
    add("Floral Organza Saree Peach", "sarees", 799, 550, ["Free Size"], ["Peach"], "Organza",
        "Trending lightweight organza saree in soft peach with large floral prints.", O)
    add("Multicolor Bandhani Saree", "sarees", 549, 320, ["Free Size"], ["Red", "Yellow"], "Georgette",
        "Traditional Rajasthani tie-dye Bandhani saree in red and yellow shades.", O)
    add("Orange Bandhani Saree", "sarees", 549, 320, ["Free Size"], ["Orange", "White"], "Georgette",
        "Traditional Rajasthani tie-dye Bandhani saree in orange and white shades.", O)
    add("Beige Cotton Silk Saree", "sarees", 699, 480, ["Free Size"], ["Beige", "Gold"], "Cotton Silk",
        "Understated beige cotton-silk saree with a gold self-weave border.", O)
    add("Maroon Cotton Silk Saree", "sarees", 699, 480, ["Free Size"], ["Maroon", "Gold"], "Cotton Silk",
        "Rich maroon cotton-silk saree with a gold self-weave border.", O)
    add("Black Net Saree", "sarees", 599, 400, ["Free Size"], ["Black", "Silver"], "Net",
        "Sleek black net saree with delicate silver sequin work, great for evenings.", O)
    add("Wine Net Saree", "sarees", 599, 400, ["Free Size"], ["Wine Maroon", "Gold"], "Net",
        "Rich wine-coloured net saree with delicate gold sequin work.", O)
    add("Sky Blue Chiffon Saree", "sarees", 449, 300, ["Free Size"], ["Sky Blue"], "Chiffon",
        "Airy sky blue chiffon saree, effortless to drape for daytime events.", O)
    add("Lavender Chiffon Saree", "sarees", 449, 300, ["Free Size"], ["Lavender"], "Chiffon",
        "Airy lavender chiffon saree, effortless to drape for daytime events.", O)
    add("Royal Blue Kanjeevaram Silk Saree", "sarees", 1399, 980, ["Free Size"], ["Royal Blue", "Gold"], "Kanjeevaram Silk",
        "Opulent royal blue Kanjeevaram silk saree with a temple-motif gold border.", O)
    add("Emerald Green Kanjeevaram Silk Saree", "sarees", 1399, 980, ["Free Size"], ["Emerald Green", "Gold"], "Kanjeevaram Silk",
        "Opulent emerald green Kanjeevaram silk saree with a temple-motif gold border.", O)
    add("White Linen Saree", "sarees", 599, 400, ["Free Size"], ["White"], "Linen",
        "Crisp white linen saree, minimal and breathable for summer days.", O)
    add("Rani Pink Linen Saree", "sarees", 599, 400, ["Free Size"], ["Rani Pink"], "Linen",
        "Vibrant rani pink linen saree, minimal and breathable for summer days.", O)
    add("Grey Georgette Saree", "sarees", 499, 340, ["Free Size"], ["Grey"], "Georgette",
        "Understated grey georgette saree with a soft drape, easy to style.", O)
    add("Black Bandhani Saree", "sarees", 549, 320, ["Free Size"], ["Black", "Yellow"], "Georgette",
        "Traditional Rajasthani tie-dye Bandhani saree in black and yellow shades.", O)

    O = _KURTI_OCCASIONS
    add("Yellow Cotton Kurti", "kurtis", 399, 280, ["S", "M", "L", "XL"], ["Yellow"], "Cotton",
        "Breezy yellow cotton kurti for everyday comfort.", O)  # YELLOW CLUSTER
    add("Basic Blue Cotton Kurti", "kurtis", 399, 280, ["S", "M", "L", "XL"], ["Blue"], "Cotton",
        "Simple, breathable blue cotton kurti at an everyday price.", O)  # PRICE TIER (basic)
    add("Premium Embroidered Maroon Kurti", "kurtis", 999, 700, ["S", "M", "L", "XL", "XXL"], ["Maroon", "Gold"], "Cotton Silk",
        "Richly embroidered maroon kurti in premium cotton-silk with gold thread work.", O)  # PRICE TIER (premium)
    add("Yellow Georgette Kurti", "kurtis", 449, 310, ["S", "M", "L", "XL"], ["Yellow"], "Georgette",
        "Flowy yellow georgette kurti with delicate neckline embroidery.", O)  # YELLOW CLUSTER
    add("Teal Georgette Designer Kurti", "kurtis", 429, 300, ["S", "M", "L", "XL"], ["Teal", "White"], "Georgette",
        "Lightweight teal georgette kurti with white embroidery around the neckline.", O)
    add("Grand Chikankari Cotton Kurti", "kurtis", 799, 560,
        ["S", "M", "L", "XL", "XXL"], ["White", "Mint Green", "Peach", "Sky Blue"], "Cotton Georgette",
        "Our flagship Lucknowi Chikankari kurti, offered in four breezy colourways.", O)  # FLAGSHIP
    add("White Chikankari Kurti", "kurtis", 599, 410, ["S", "M", "L", "XL"], ["White"], "Cotton Georgette",
        "Lucknowi Chikankari work kurti in classic white, breathable and elegant.", O)
    add("Black Cotton Kurti and Pant Set", "kurtis", 499, 350, ["S", "M", "L", "XL"], ["Black"], "Cotton",
        "Classic black regular-wear kurti with straight pants in breathable cotton.", O)
    add("Rani Pink Rayon Kurti", "kurtis", 549, 380, ["S", "M", "L", "XL"], ["Rani Pink"], "Rayon",
        "Vibrant rani pink rayon kurti with a flattering A-line cut.", O)
    add("Grey Rayon Kurti", "kurtis", 549, 380, ["S", "M", "L", "XL"], ["Grey"], "Rayon",
        "Understated grey rayon kurti with a flattering A-line cut.", O)
    add("Green Embroidered Kurta Set", "kurtis", 549, 380, ["M", "L", "XL"], ["Green"], "Cotton Blend",
        "Traditional green straight-fit kurta set with delicate zari embroidery detailing.", O)
    add("Orange Cotton Kurti", "kurtis", 429, 300, ["S", "M", "L", "XL"], ["Orange"], "Cotton",
        "Bright orange cotton kurti, breathable and easy to style.", O)
    add("Purple Cotton Silk Kurti", "kurtis", 649, 450, ["S", "M", "L", "XL"], ["Purple", "Gold"], "Cotton Silk",
        "Rich purple cotton-silk kurti with a subtle gold self-weave.", O)
    add("Mustard Linen Kurti", "kurtis", 599, 410, ["S", "M", "L", "XL"], ["Mustard"], "Linen",
        "Earthy mustard linen kurti, minimal and breathable for summer wear.", O)
    add("Peach Cotton Blend Kurti", "kurtis", 449, 310, ["S", "M", "L", "XL"], ["Peach"], "Cotton Blend",
        "Soft peach cotton-blend kurti for effortless daily wear.", O)
    add("Coral Georgette Kurti", "kurtis", 479, 330, ["S", "M", "L", "XL"], ["Coral"], "Georgette",
        "Flowy coral georgette kurti with a flattering silhouette.", O)
    add("Navy Blue Cotton Kurti", "kurtis", 429, 300, ["S", "M", "L", "XL"], ["Navy Blue"], "Cotton",
        "Classic navy blue cotton kurti, versatile for work or casual wear.", O)
    add("Beige Linen Kurti", "kurtis", 599, 410, ["S", "M", "L", "XL"], ["Beige"], "Linen",
        "Minimal beige linen kurti, breathable and elegant.", O)
    add("Wine Velvet Kurti", "kurtis", 899, 630, ["S", "M", "L", "XL"], ["Wine Maroon"], "Velvet",
        "Festive wine velvet kurti with a rich, plush finish.", O)
    add("Turquoise Rayon Kurti", "kurtis", 549, 380, ["S", "M", "L", "XL"], ["Turquoise"], "Rayon",
        "Vivid turquoise rayon kurti with a flattering A-line cut.", O)
    add("Ivory Chikankari Kurti", "kurtis", 649, 450, ["S", "M", "L", "XL"], ["Ivory"], "Cotton Georgette",
        "Lucknowi Chikankari work kurti in soft ivory, breathable and elegant.", O)
    add("Magenta Cotton Kurti", "kurtis", 429, 300, ["S", "M", "L", "XL"], ["Magenta"], "Cotton",
        "Bold magenta cotton kurti, breathable and easy to style.", O)

    O = _SUIT_OCCASIONS
    add("Yellow Anarkali Suit", "suits", 899, 630, ["S", "M", "L", "XL"], ["Yellow", "Gold"], "Cotton Silk",
        "Flared yellow Anarkali suit set with a gold-bordered dupatta.", O)  # YELLOW CLUSTER
    add("Grand Anarkali Suit", "suits", 1199, 840,
        ["S", "M", "L", "XL", "XXL"], ["Crimson Red", "Emerald Green", "Royal Gold", "Navy Blue", "Blush Pink"], "Cotton Silk",
        "Our flagship Anarkali suit, offered in five rich colourways with a flared silhouette.", O)  # FLAGSHIP
    add("Pink Cotton Anarkali Suit", "suits", 899, 650, ["S", "M", "L", "XL", "XXL"], ["Pink"], "Cotton",
        "Flared pink cotton Anarkali suit set with a floral print dupatta.", O)
    add("Basic Cotton Silk Suit Material", "suits", 599, 410, ["Unstitched - Custom Fit"], ["Beige", "Gold"], "Cotton Silk",
        "Unstitched cotton-silk suit material with self-design and zari weave borders.", O, window=10)  # PRICE TIER (basic)
    add("Premium Net Anarkali Suit", "suits", 1199, 840, ["S", "M", "L", "XL"], ["Royal Blue", "Silver"], "Net",
        "Heavily embellished net Anarkali suit with silver sequin work.", O)  # PRICE TIER (premium)
    add("Red Georgette Palazzo Suit", "suits", 799, 550, ["S", "M", "L", "XL"], ["Red"], "Georgette",
        "Flowy red georgette palazzo suit set, comfortable for all-day wear.", O)
    add("Green Georgette Palazzo Suit", "suits", 799, 550, ["S", "M", "L", "XL"], ["Green"], "Georgette",
        "Flowy green georgette palazzo suit set, comfortable for all-day wear.", O)
    add("Black Chanderi Suit Set", "suits", 749, 520, ["S", "M", "L", "XL"], ["Black", "Gold"], "Chanderi",
        "Elegant black Chanderi suit set with a fine gold self-weave.", O)
    add("Maroon Chanderi Suit Set", "suits", 749, 520, ["S", "M", "L", "XL"], ["Maroon", "Gold"], "Chanderi",
        "Elegant maroon Chanderi suit set with a fine gold self-weave.", O)
    add("Sky Blue Cotton Suit", "suits", 599, 410, ["S", "M", "L", "XL"], ["Sky Blue"], "Cotton",
        "Breathable sky blue cotton suit set for daytime comfort.", O)
    add("Mint Green Cotton Suit", "suits", 599, 410, ["S", "M", "L", "XL"], ["Mint Green"], "Cotton",
        "Breathable mint green cotton suit set for daytime comfort.", O)
    add("Peach Net Suit", "suits", 849, 590, ["S", "M", "L", "XL"], ["Peach"], "Net",
        "Delicate peach net suit set with light embellishment.", O)
    add("Lavender Georgette Suit", "suits", 799, 550, ["S", "M", "L", "XL"], ["Lavender"], "Georgette",
        "Flowy lavender georgette suit set, comfortable for all-day wear.", O)
    add("Orange Silk Blend Suit", "suits", 899, 630, ["S", "M", "L", "XL"], ["Orange", "Gold"], "Silk Blend",
        "Festive orange silk-blend suit set with a subtle gold sheen.", O)
    add("Grey Cotton Suit", "suits", 599, 410, ["S", "M", "L", "XL"], ["Grey"], "Cotton",
        "Breathable grey cotton suit set for daytime comfort.", O)
    add("Wine Velvet Suit Set", "suits", 999, 700, ["S", "M", "L", "XL"], ["Wine Maroon"], "Velvet",
        "Festive wine velvet suit set with a rich, plush finish.", O)
    add("Turquoise Georgette Suit", "suits", 799, 550, ["S", "M", "L", "XL"], ["Turquoise"], "Georgette",
        "Flowy turquoise georgette suit set, comfortable for all-day wear.", O)
    add("Ivory Net Suit", "suits", 899, 630, ["S", "M", "L", "XL"], ["Ivory", "Silver"], "Net",
        "Delicate ivory net suit set with silver sequin work.", O)

    O = _TOP_OCCASIONS
    add("Yellow Chiffon Top", "tops", 349, 240, ["S", "M", "L", "XL"], ["Yellow"], "Chiffon",
        "Breezy yellow chiffon top, easy to dress up or down.", O)  # YELLOW CLUSTER
    add("Basic Blue Cotton Top", "tops", 299, 200, ["S", "M", "L", "XL"], ["Blue"], "Cotton",
        "Simple, breathable blue cotton top at an everyday price.", O)  # PRICE TIER (basic)
    add("Premium Sequined Black Top", "tops", 799, 560, ["S", "M", "L", "XL"], ["Black", "Silver"], "Satin",
        "Statement black satin top with all-over silver sequin work.", O)  # PRICE TIER (premium)
    add("Red Crepe Top", "tops", 349, 240, ["S", "M", "L", "XL"], ["Red"], "Crepe",
        "Flowy red crepe top with a relaxed, flattering fit.", O)
    add("White Rayon Top", "tops", 329, 230, ["S", "M", "L", "XL"], ["White"], "Rayon",
        "Crisp white rayon top for effortless everyday styling.", O)
    add("Denim Blue Shirt Top", "tops", 449, 310, ["S", "M", "L", "XL"], ["Denim Blue"], "Denim",
        "Classic denim blue shirt top, a versatile wardrobe staple.", O)
    add("Satin Wine Top", "tops", 599, 420, ["S", "M", "L", "XL"], ["Wine Maroon"], "Satin",
        "Lustrous wine satin top with a smooth, elegant drape.", O)
    add("Floral Print Rayon Top", "tops", 379, 260, ["S", "M", "L", "XL"], ["Multicolor"], "Rayon",
        "Playful floral print rayon top, perfect for sunny days.", O)
    add("Peach Chiffon Top", "tops", 349, 240, ["S", "M", "L", "XL"], ["Peach"], "Chiffon",
        "Breezy peach chiffon top, easy to dress up or down.", O)
    add("Mint Green Crepe Top", "tops", 379, 260, ["S", "M", "L", "XL"], ["Mint Green"], "Crepe",
        "Flowy mint green crepe top with a relaxed, flattering fit.", O)
    add("Mustard Cotton Top", "tops", 329, 230, ["S", "M", "L", "XL"], ["Mustard"], "Cotton",
        "Earthy mustard cotton top for effortless everyday styling.", O)
    add("Coral Satin Top", "tops", 549, 380, ["S", "M", "L", "XL"], ["Coral"], "Satin",
        "Lustrous coral satin top with a smooth, elegant drape.", O)
    add("Navy Blue Rayon Top", "tops", 349, 240, ["S", "M", "L", "XL"], ["Navy Blue"], "Rayon",
        "Versatile navy blue rayon top for work or casual wear.", O)
    add("Blush Pink Crepe Top", "tops", 379, 260, ["S", "M", "L", "XL"], ["Blush Pink"], "Crepe",
        "Flowy blush pink crepe top with a relaxed, flattering fit.", O)

    O = _LEHENGA_OCCASIONS
    add("Yellow Net Lehenga", "lehengas", 1499, 1050, ["S", "M", "L", "XL"], ["Yellow", "Gold"], "Net",
        "Festive yellow net lehenga with delicate gold embellishment.", O)  # YELLOW CLUSTER
    add("Red Silk Bridal Lehenga", "lehengas", 2499, 1750, ["S", "M", "L", "XL"], ["Red", "Gold"], "Silk",
        "Opulent red bridal lehenga in pure silk with heavy gold embroidery.", O, cod=False)
    add("Green Georgette Lehenga", "lehengas", 1299, 900, ["S", "M", "L", "XL"], ["Green"], "Georgette",
        "Flowy green georgette lehenga, light enough for long celebrations.", O)
    add("Pink Net Lehenga", "lehengas", 1399, 980, ["S", "M", "L", "XL"], ["Pink", "Silver"], "Net",
        "Festive pink net lehenga with delicate silver embellishment.", O)
    add("Royal Blue Velvet Lehenga", "lehengas", 1999, 1400, ["S", "M", "L", "XL"], ["Royal Blue", "Gold"], "Velvet",
        "Rich royal blue velvet lehenga with heavy gold embroidery.", O, cod=False)
    add("Maroon Silk Lehenga", "lehengas", 1899, 1330, ["S", "M", "L", "XL"], ["Maroon", "Gold"], "Silk",
        "Opulent maroon silk lehenga with heavy gold embroidery.", O, cod=False)
    add("Peach Net Lehenga", "lehengas", 1299, 900, ["S", "M", "L", "XL"], ["Peach"], "Net",
        "Festive peach net lehenga, light enough for long celebrations.", O)
    add("Turquoise Georgette Lehenga", "lehengas", 1349, 940, ["S", "M", "L", "XL"], ["Turquoise"], "Georgette",
        "Flowy turquoise georgette lehenga, light enough for long celebrations.", O)
    add("Black Velvet Lehenga", "lehengas", 1799, 1260, ["S", "M", "L", "XL"], ["Black", "Gold"], "Velvet",
        "Rich black velvet lehenga with heavy gold embroidery.", O, cod=False)
    add("Mint Green Net Lehenga", "lehengas", 1299, 900, ["S", "M", "L", "XL"], ["Mint Green"], "Net",
        "Festive mint green net lehenga, light enough for long celebrations.", O)
    add("Orange Silk Lehenga", "lehengas", 1599, 1120, ["S", "M", "L", "XL"], ["Orange", "Gold"], "Silk",
        "Vibrant orange silk lehenga with rich gold embroidery.", O)
    add("Ivory Net Lehenga", "lehengas", 1599, 1120, ["S", "M", "L", "XL"], ["Ivory", "Silver"], "Net",
        "Elegant ivory net lehenga with delicate silver embellishment.", O)

    O = _DRESS_OCCASIONS
    add("Yellow A-Line Dress", "dresses", 599, 420, ["S", "M", "L", "XL"], ["Yellow"], "Crepe",
        "Breezy yellow A-Line dress with a flattering silhouette.", O)  # YELLOW CLUSTER
    add("Basic Black Cotton Dress", "dresses", 449, 310, ["S", "M", "L", "XL"], ["Black"], "Cotton",
        "Simple, versatile black cotton dress at an everyday price.", O)  # PRICE TIER (basic)
    add("Premium Sequined Wine Dress", "dresses", 999, 700, ["S", "M", "L", "XL"], ["Wine Maroon", "Gold"], "Satin",
        "Statement wine satin dress with all-over gold sequin work.", O)  # PRICE TIER (premium)
    add("Red Wrap Dress", "dresses", 549, 380, ["S", "M", "L", "XL"], ["Red"], "Crepe",
        "Flattering red wrap dress, easy to style for any occasion.", O)
    add("Floral Print Crepe Dress", "dresses", 499, 350, ["S", "M", "L", "XL"], ["Multicolor"], "Crepe",
        "Playful floral print crepe dress, perfect for sunny days.", O)
    add("Navy Blue Bodycon Dress", "dresses", 549, 380, ["S", "M", "L", "XL"], ["Navy Blue"], "Georgette",
        "Sleek navy blue bodycon dress for evening plans.", O)
    add("Blush Pink Satin Dress", "dresses", 699, 490, ["S", "M", "L", "XL"], ["Blush Pink"], "Satin",
        "Lustrous blush pink satin dress with a smooth, elegant drape.", O)
    add("Emerald Green Georgette Dress", "dresses", 649, 450, ["S", "M", "L", "XL"], ["Emerald Green"], "Georgette",
        "Flowy emerald green georgette dress, light and elegant.", O)
    add("White Cotton Sundress", "dresses", 449, 310, ["S", "M", "L", "XL"], ["White"], "Cotton",
        "Crisp white cotton sundress for effortless summer styling.", O)
    add("Coral Crepe Dress", "dresses", 549, 380, ["S", "M", "L", "XL"], ["Coral"], "Crepe",
        "Flattering coral crepe dress, easy to style for any occasion.", O)
    add("Grey Bodycon Dress", "dresses", 499, 350, ["S", "M", "L", "XL"], ["Grey"], "Georgette",
        "Sleek grey bodycon dress for evening plans.", O)
    add("Lavender Georgette Dress", "dresses", 599, 420, ["S", "M", "L", "XL"], ["Lavender"], "Georgette",
        "Flowy lavender georgette dress, light and elegant.", O)

    return products

MOCK_PRODUCTS = build_catalog()

# Real, individually-verified product photos. Each was found via web search,
# downloaded, and visually inspected (Read tool) before being trusted here -
# NOT picked from search-result titles/alt-text alone. That distinction
# matters: earlier in this project, picking images without viewing them put
# a beach photo on a saree listing and men's clothing on a women's item.
# Falls back to the picsum placeholder (see build_catalog/add()) for any SKU
# not present in this map. A few items are noted approximations where no
# exact color/fabric match exists on Unsplash - garment type was prioritized
# over exact shade in those cases.
VERIFIED_IMAGE_URLS = {
    "SKU_001": "https://images.unsplash.com/photo-1781154109400-ac768a5a79cc?w=600&q=80",
    "SKU_002": "https://images.unsplash.com/photo-1756483496916-5ebab85028df?w=600&q=80",
    "SKU_003": "https://images.unsplash.com/photo-1732850195110-eeea3f216a65?w=600&q=80",
    "SKU_004": "https://images.unsplash.com/photo-1681717075175-19feb7a6f664?w=600&q=80",
    "SKU_005": "https://images.unsplash.com/photo-1771654803890-a288916d4c9e?w=600&q=80",
    "SKU_006": "https://images.unsplash.com/photo-1585531977323-8d57bac2121b?w=600&q=80",
    "SKU_007": "https://images.unsplash.com/photo-1775486101623-3eb0f11d1e37?w=600&q=80",
    "SKU_008": "https://images.unsplash.com/photo-1619173945851-66c8e4b9db2c?w=600&q=80",
    "SKU_009": "https://images.unsplash.com/photo-1769103948746-8592931bbdad?w=600&q=80",
    "SKU_010": "https://images.unsplash.com/photo-1754782806540-a3c773ac0c9c?w=600&q=80",
    "SKU_011": "https://images.unsplash.com/photo-1607647735186-f3c200aa175a?w=600&q=80",
    "SKU_012": "https://images.unsplash.com/photo-1769500802800-51f5662b82b1?w=600&q=80",
    "SKU_013": "https://images.unsplash.com/photo-1710969496397-b22b12860b07?w=600&q=80",
    "SKU_014": "https://images.unsplash.com/photo-1730144615465-adedba32ae37?w=600&q=80",
    "SKU_015": "https://images.unsplash.com/photo-1638280220720-92a5a5ad1897?w=600&q=80",
    "SKU_016": "https://images.unsplash.com/photo-1762320562013-45bd4f133fba?w=600&q=80",
    "SKU_017": "https://images.unsplash.com/photo-1585531977323-8d57bac2121b?w=600&q=80",
    "SKU_018": "https://images.unsplash.com/photo-1756483509177-bbabd67a3234?w=600&q=80",
    "SKU_019": "https://images.unsplash.com/photo-1778770217853-a907b882b0c9?w=600&q=80",
    "SKU_020": "https://images.unsplash.com/photo-1729101146153-88f1d7837298?w=600&q=80",
    "SKU_021": "https://images.unsplash.com/photo-1758119461027-44f323ed6b4c?w=600&q=80",
    "SKU_022": "https://images.unsplash.com/photo-1737536023585-3c377d1ea03e?w=600&q=80",
    "SKU_023": "https://images.unsplash.com/photo-1760287363878-1a09af715b80?w=600&q=80",
    "SKU_024": "https://images.unsplash.com/photo-1766994063815-e4762e991c1f?w=600&q=80",
    "SKU_025": "https://images.unsplash.com/photo-1708534246055-d7b149acb731?w=600&q=80",
    "SKU_026": "https://images.unsplash.com/photo-1729203510675-e197604795b6?w=600&q=80",
    "SKU_027": "https://images.unsplash.com/photo-1769063382670-823451e5a7ef?w=600&q=80",
    "SKU_028": "https://images.unsplash.com/photo-1745313452052-0e4e341f326c?w=600&q=80",
    "SKU_029": "https://images.unsplash.com/photo-1752653425039-cf1ff22d61bc?w=600&q=80",
    "SKU_030": "https://images.unsplash.com/photo-1768803968260-3dab844c1476?w=600&q=80",
    "SKU_031": "https://images.unsplash.com/photo-1773439878533-77383b20577c?w=600&q=80",
    "SKU_032": "https://images.unsplash.com/photo-1773439877855-cd193d949717?w=600&q=80",
    "SKU_033": "https://images.unsplash.com/photo-1765436607852-7ae171f0d13b?w=600&q=80",
    "SKU_034": "https://images.unsplash.com/photo-1720159265244-d83e0c9fc01b?w=600&q=80",
    "SKU_035": "https://images.unsplash.com/photo-1669199529119-65dda6d4167d?w=600&q=80",
    "SKU_036": "https://images.unsplash.com/photo-1774437895653-5ce783f5cf7c?w=600&q=80",
    "SKU_037": "https://images.unsplash.com/photo-1743229995503-a67a09c4e180?w=600&q=80",
    "SKU_038": "https://images.unsplash.com/photo-1693987658395-333b847c2781?w=600&q=80",
    "SKU_039": "https://images.unsplash.com/photo-1766994063823-ed214f883548?w=600&q=80",
    "SKU_040": "https://images.unsplash.com/photo-1754391851702-e5275cf80e34?w=600&q=80",
    "SKU_041": "https://images.unsplash.com/photo-1704119141149-b7558b2803f7?w=600&q=80",
    "SKU_042": "https://images.unsplash.com/photo-1693990149455-95a906f31951?w=600&q=80",
    "SKU_043": "https://images.unsplash.com/photo-1745313452052-0e4e341f326c?w=600&q=80",
    "SKU_044": "https://images.unsplash.com/photo-1760287364328-e30221615f2e?w=600&q=80",
    "SKU_045": "https://images.unsplash.com/photo-1743229995477-a9e80d48af73?w=600&q=80",
    "SKU_046": "https://images.unsplash.com/photo-1759840279499-f9de9764b2cf?w=600&q=80",
    "SKU_047": "https://images.unsplash.com/photo-1741847639057-b51a25d42892?w=600&q=80",
    "SKU_048": "https://images.unsplash.com/photo-1712852733629-c5b8194290e8?w=600&q=80",
    "SKU_049": "https://images.unsplash.com/photo-1756483510820-4b9302a27556?w=600&q=80",
    "SKU_050": "https://images.unsplash.com/photo-1768289222423-4984f638c542?w=600&q=80",
    "SKU_051": "https://images.unsplash.com/photo-1745996506594-4182dd83d19f?w=600&q=80",
    "SKU_052": "https://images.unsplash.com/photo-1761571260010-8aa90a08c934?w=600&q=80",
    "SKU_053": "https://images.unsplash.com/photo-1708534246055-d7b149acb731?w=600&q=80",
    "SKU_054": "https://images.unsplash.com/photo-1780247723311-2dae151784d1?w=600&q=80",
    "SKU_055": "https://images.unsplash.com/photo-1773439877127-ecfe17c9eb62?w=600&q=80",
    "SKU_056": "https://images.unsplash.com/photo-1743229995503-a67a09c4e180?w=600&q=80",
    "SKU_057": "https://images.unsplash.com/photo-1705920821957-5d1a22a1d829?w=600&q=80",
    "SKU_058": "https://images.unsplash.com/photo-1705921345983-645ac1ac9db7?w=600&q=80",
    "SKU_059": "https://images.unsplash.com/photo-1773439878174-201b8b441e75?w=600&q=80",
    "SKU_060": "https://images.unsplash.com/photo-1779253806210-5da53324527c?w=600&q=80",
    "SKU_061": "https://images.unsplash.com/photo-1705920821970-ca98041338fe?w=600&q=80",
    "SKU_062": "https://images.unsplash.com/photo-1702975785351-9f020c9b0409?w=600&q=80",
    "SKU_063": "https://images.unsplash.com/photo-1711188054302-75e493d78646?w=600&q=80",
    "SKU_064": "https://images.unsplash.com/photo-1598911540912-48ec1504a8ac?w=600&q=80",
    "SKU_065": "https://images.unsplash.com/photo-1562468689-22db61602255?w=600&q=80",
    "SKU_066": "https://images.unsplash.com/photo-1573497491677-1b69852c78a3?w=600&q=80",
    "SKU_067": "https://images.unsplash.com/photo-1753395298691-eb93244d76c1?w=600&q=80",
    "SKU_068": "https://images.unsplash.com/photo-1485286433112-1388205988c5?w=600&q=80",
    "SKU_069": "https://images.unsplash.com/photo-1711188052656-9e90308f1047?w=600&q=80",
    "SKU_070": "https://images.unsplash.com/photo-1564257631407-4deb1f99d992?w=600&q=80",
    "SKU_071": "https://images.unsplash.com/photo-1564595076323-71cc27edacf8?w=600&q=80",
    "SKU_072": "https://images.unsplash.com/photo-1702974779263-6de52dbe29a3?w=600&q=80",
    "SKU_073": "https://images.unsplash.com/photo-1613477757159-7fbb73011611?w=600&q=80",
    "SKU_074": "https://images.unsplash.com/photo-1654064902438-d39debb8a089?w=600&q=80",
    "SKU_075": "https://images.unsplash.com/photo-1553255428-ec08904d034b?w=600&q=80",
    "SKU_076": "https://images.unsplash.com/photo-1630401606832-a272d6cf44c2?w=600&q=80",
    "SKU_077": "https://images.unsplash.com/photo-1574847872646-abff244bbd87?w=600&q=80",
    "SKU_078": "https://images.unsplash.com/photo-1645862755924-9f4e7f200b83?w=600&q=80",
    "SKU_079": "https://images.unsplash.com/photo-1620025466661-1c02f465df0d?w=600&q=80",
    "SKU_080": "https://images.unsplash.com/photo-1766763846106-321b0ef369c2?w=600&q=80",
    "SKU_081": "https://images.unsplash.com/photo-1756483511246-12ae36997a1b?w=600&q=80",
    "SKU_082": "https://images.unsplash.com/photo-1760613129745-418b15f91d56?w=600&q=80",
    "SKU_083": "https://images.unsplash.com/photo-1756483510831-34a18c266b93?w=600&q=80",
    "SKU_084": "https://images.unsplash.com/photo-1756483515151-468b4b5ca1ba?w=600&q=80",
    "SKU_085": "https://images.unsplash.com/photo-1756483500430-0c1234c1a782?w=600&q=80",
    "SKU_086": "https://images.unsplash.com/photo-1641382158662-b6ef03d53f53?w=600&q=80",
    "SKU_087": "https://images.unsplash.com/photo-1760461804244-09a95b4d8d8c?w=600&q=80",
    "SKU_088": "https://images.unsplash.com/photo-1736849854779-ba3b106c149c?w=600&q=80",
    "SKU_089": "https://images.unsplash.com/photo-1621143814870-d28ef0bb3844?w=600&q=80",
    "SKU_090": "https://images.unsplash.com/photo-1656284518334-710b60cd63a0?w=600&q=80",
    "SKU_091": "https://images.unsplash.com/photo-1765229278212-9ffe0c0eff1a?w=600&q=80",
    "SKU_092": "https://images.unsplash.com/photo-1630769265901-9c131a95678b?w=600&q=80",
    "SKU_093": "https://images.unsplash.com/photo-1602010069450-0a62034f235c?w=600&q=80",
    "SKU_094": "https://images.unsplash.com/photo-1612878569417-a62601be8d7d?w=600&q=80",
    "SKU_095": "https://images.unsplash.com/photo-1601266249346-f416f2c23e5a?w=600&q=80",
    "SKU_096": "https://images.unsplash.com/photo-1609357605129-26f69add5d6e?w=600&q=80",
    "SKU_097": "https://images.unsplash.com/photo-1629686064165-71e6f1fb1763?w=600&q=80",
    "SKU_098": "https://images.unsplash.com/photo-1596783074918-c84cb06531ca?w=600&q=80",
    "SKU_099": "https://images.unsplash.com/photo-1624278268398-7068ead78872?w=600&q=80",
    "SKU_100": "https://images.unsplash.com/photo-1780581058508-1464a278b570?w=600&q=80",
}
for _p in MOCK_PRODUCTS:
    if _p["product_id"] in VERIFIED_IMAGE_URLS:
        _p["base_image_url"] = VERIFIED_IMAGE_URLS[_p["product_id"]]

def main():
    print("=== SAKHI DATABASE SEEDING ENGINE ===")

    # Validation check
    if not SUPABASE_URL or "YOUR_SUPABASE_URL_HERE" in SUPABASE_URL:
        print("[WARNING] Supabase URL is not set or is using placeholder. Skipping database seeding.")
        sys.exit(0)
    if not SUPABASE_SERVICE_KEY or "YOUR_SUPABASE_SERVICE_KEY" in SUPABASE_SERVICE_KEY:
        print("[WARNING] Supabase Service Key is not set or is using placeholder. Skipping database seeding.")
        sys.exit(0)
    if not GEMINI_API_KEY or "YOUR_GEMINI_API_KEY" in GEMINI_API_KEY:
        print("[WARNING] Gemini API Key is not set or is using placeholder. Skipping database seeding.")
        sys.exit(0)

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"[ERROR] Failed to load/configure Google Generative AI: {e}")
        sys.exit(1)

    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    except Exception as e:
        print(f"[ERROR] Failed to connect to Supabase: {e}")
        sys.exit(1)

    print("Supabase connection established successfully.")

    # Empty table first to prevent key duplication
    try:
        print("Cleaning up old catalog entries...")
        supabase.table("product_embeddings").delete().neq("product_id", "").execute()
    except Exception as e:
        print(f"[WARNING] Database table might not exist or failed to clear: {e}")
        print("Please ensure you ran supabase_schema.sql first inside your Supabase SQL Editor.")
        sys.exit(1)

    total = len(MOCK_PRODUCTS)
    print(f"Starting seeding of {total} products...")

    failures = []
    for i, prod in enumerate(MOCK_PRODUCTS, start=1):
        try:
            print(f"[{i}/{total}] Generating embedding for {prod['product_id']} ({prod['name']})...")
            # Smart embedding string: heavily weights the visual/stylistic
            # elements (category, material, colors) ahead of the free-text
            # description, since those are what customer queries like "yellow
            # saree for haldi" actually key off.
            text_to_embed = (
                f"Category: {prod['category']} | Name: {prod['name']} | Material: {prod['material']} | "
                f"Colors Available: {', '.join(prod['colors'])} | Description: {prod['description']}"
            )

            response = genai.embed_content(
                model="models/gemini-embedding-001",
                content=text_to_embed,
                task_type="retrieval_document",
                output_dimensionality=768
            )
            embedding = response["embedding"]

            payload = {
                "product_id": prod["product_id"],
                "name": prod["name"],
                "category": prod["category"],
                "suggested_selling_price_inr": prod["suggested_selling_price_inr"],
                "meesho_cost_inr": prod["meesho_cost_inr"],
                "return_window_days": prod["return_window_days"],
                "cod_available": prod["cod_available"],
                "description": prod["description"],
                "sizes": prod["sizes"],
                "colors": prod["colors"],
                "material": prod["material"],
                "base_image_url": prod["base_image_url"],
                "embedding": embedding
            }

            supabase.table("product_embeddings").insert(payload).execute()
            print(f"[SUCCESS] Uploaded {prod['product_id']}")
        except Exception as e:
            print(f"[FAILED] Failed to process product {prod['product_id']}: {e}")
            failures.append(prod["product_id"])

        # Small delay between calls to stay well under the free-tier
        # requests-per-minute limit on the embedding endpoint.
        time.sleep(0.5)

    print("=== SEEDING COMPLETED ===")
    print(f"Uploaded: {total - len(failures)}/{total}")
    if failures:
        print(f"Failed SKUs: {', '.join(failures)}")

if __name__ == "__main__":
    main()
