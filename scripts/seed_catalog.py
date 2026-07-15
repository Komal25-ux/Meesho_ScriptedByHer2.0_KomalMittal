import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# Load variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MOCK_PRODUCTS = [
    {
        "product_id": "SKU_001",
        "name": "Red Banarasi Silk Saree",
        "category": "sarees",
        "suggested_selling_price_inr": 599,
        "meesho_cost_inr": 420,
        "return_window_days": 7,
        "cod_available": True,
        "description": "Elegant red Banarasi silk saree with gold zari borders. Perfect for wedding season, festivals, and traditional family occasions."
    },
    {
        "product_id": "SKU_002",
        "name": "Blue Georgette Designer Kurti",
        "category": "kurtis",
        "suggested_selling_price_inr": 399,
        "meesho_cost_inr": 280,
        "return_window_days": 7,
        "cod_available": True,
        "description": "Lightweight georgette kurti in deep blue. Features beautiful white embroidery around the neckline, suitable for daily and office wear."
    },
    {
        "product_id": "SKU_003",
        "name": "Pink Cotton Anarkali Suit",
        "category": "suits",
        "suggested_selling_price_inr": 899,
        "meesho_cost_inr": 650,
        "return_window_days": 10,
        "cod_available": True,
        "description": "Flared pink cotton Anarkali suit set with a floral print dupatta. Comfortable for summer wear, casual outings, and daytime functions."
    },
    {
        "product_id": "SKU_004",
        "name": "Yellow Chanderi Saree",
        "category": "sarees",
        "suggested_selling_price_inr": 699,
        "meesho_cost_inr": 480,
        "return_window_days": 7,
        "cod_available": True,
        "description": "Vibrant yellow Chanderi cotton saree with silver border. Ideal for religious rituals, Haldi ceremonies, and daytime celebrations."
    },
    {
        "product_id": "SKU_005",
        "name": "Green Embroidered Kurta Set",
        "category": "kurtis",
        "suggested_selling_price_inr": 549,
        "meesho_cost_inr": 380,
        "return_window_days": 7,
        "cod_available": True,
        "description": "Traditional green straight-fit kurta set with solid color matching trousers. Features delicate zari embroidery detailing."
    },
    {
        "product_id": "SKU_006",
        "name": "Floral Organza Saree Pink",
        "category": "sarees",
        "suggested_selling_price_inr": 799,
        "meesho_cost_inr": 550,
        "return_window_days": 7,
        "cod_available": False,
        "description": "Trending lightweight organza saree in pastel pink with large floral prints. Highly popular among younger buyers for evening parties."
    },
    {
        "product_id": "SKU_007",
        "name": "Black Cotton Kurti and Pant Set",
        "category": "kurtis",
        "suggested_selling_price_inr": 499,
        "meesho_cost_inr": 350,
        "return_window_days": 7,
        "cod_available": True,
        "description": "Classic black regular wear kurti with straight pants. Made of breathable cotton material, ideal for hot Indian summers."
    },
    {
        "product_id": "SKU_008",
        "name": "Multicolor Bandhani Saree",
        "category": "sarees",
        "suggested_selling_price_inr": 499,
        "meesho_cost_inr": 320,
        "return_window_days": 7,
        "cod_available": True,
        "description": "Traditional Rajasthani tie-dye Bandhani saree in red and yellow shades. Ideal for festive pujas, Karwa Chauth, and cultural events."
    },
    {
        "product_id": "SKU_009",
        "name": "Cotton Silk Zari Suit Material",
        "category": "suits",
        "suggested_selling_price_inr": 599,
        "meesho_cost_inr": 410,
        "return_window_days": 10,
        "cod_available": True,
        "description": "Unstitched cotton-silk suit material with self-design and zari weave borders. Custom stitchable to fit any size specifications."
    },
    {
        "product_id": "SKU_010",
        "name": "Casual Cotton Chikankari Kurti",
        "category": "kurtis",
        "suggested_selling_price_inr": 450,
        "meesho_cost_inr": 310,
        "return_window_days": 7,
        "cod_available": True,
        "description": "Lucknowi Chikankari work georgette-cotton kurti in white and mint green shades. Very breezy, breathable, and pairs perfectly with denims."
    }
]

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

    print(f"Starting seeding of {len(MOCK_PRODUCTS)} products...")
    
    for prod in MOCK_PRODUCTS:
        try:
            print(f"Generating embedding vector for SKU: {prod['product_id']} ({prod['name']})...")
            # Build search string containing name, category, and description
            text_to_embed = f"Product: {prod['name']}. Category: {prod['category']}. Description: {prod['description']}"
            
            response = genai.embed_content(
                model="models/text-embedding-004",
                content=text_to_embed,
                task_type="retrieval_document"
            )
            embedding = response['embedding']
            
            # Prepare payload
            payload = {
                "product_id": prod["product_id"],
                "name": prod["name"],
                "category": prod["category"],
                "suggested_selling_price_inr": prod["suggested_selling_price_inr"],
                "meesho_cost_inr": prod["meesho_cost_inr"],
                "return_window_days": prod["return_window_days"],
                "cod_available": prod["cod_available"],
                "description": prod["description"],
                "embedding": embedding
            }
            
            # Insert into Supabase
            supabase.table("product_embeddings").insert(payload).execute()
            print(f"[SUCCESS] Uploaded {prod['product_id']}")
        except Exception as e:
            print(f"[FAILED] Failed to process product {prod['product_id']}: {e}")
            
    print("=== SEEDING COMPLETED ===")

if __name__ == "__main__":
    main()
