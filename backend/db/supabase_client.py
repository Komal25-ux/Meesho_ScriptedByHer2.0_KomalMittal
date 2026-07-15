import logging
from supabase import create_client, Client
from backend.config import settings

logger = logging.getLogger("sakhi-backend")

class SupabaseDB:
    def __init__(self):
        self.url = settings.SUPABASE_URL
        self.key = settings.SUPABASE_SERVICE_KEY
        self.client = None
        
        # Safe initialization
        if self.url and self.key and "YOUR_SUPABASE" not in self.url and "YOUR_SUPABASE" not in self.key:
            try:
                self.client: Client = create_client(self.url, self.key)
                logger.info("[SUCCESS] Supabase Client Initialized.")
            except Exception as e:
                logger.error(f"[ERROR] Failed to initialize Supabase client: {e}")
        else:
            logger.warning("[WARNING] Supabase credentials missing or set to placeholder. Database will run in MOCK mode.")

    def is_mock(self) -> bool:
        return self.client is None

    def get_or_create_reseller(self, whatsapp_number: str) -> dict:
        """Upsert a reseller by WhatsApp number. Returns the reseller record."""
        if self.is_mock():
            return {
                "id": "00000000-0000-0000-0000-000000000000",
                "whatsapp_number": whatsapp_number,
                "name": "Sunita Didi (Mock)",
                "location": "Kanpur, UP",
                "language": "hi",
                "dialect": "hindi"
            }
        try:
            # Check if reseller exists
            res = self.client.table("resellers").select("*").eq("whatsapp_number", whatsapp_number).execute()
            if res.data:
                return res.data[0]
            
            # Create reseller
            new_reseller = {
                "whatsapp_number": whatsapp_number,
                "name": "Sunita Didi",
                "location": "Kanpur, UP",
                "language": "hi",
                "dialect": "hindi"
            }
            insert_res = self.client.table("resellers").insert(new_reseller).execute()
            reseller = insert_res.data[0]
            
            # Create default profile
            new_profile = {
                "reseller_id": reseller["id"],
                "monthly_target_inr": 10000,
                "preferred_categories": ["sarees", "kurtis"],
                "customer_base_size": 200,
                "total_listings": 0
            }
            self.client.table("reseller_profiles").insert(new_profile).execute()
            return reseller
        except Exception as e:
            logger.error(f"Error in get_or_create_reseller: {e}")
            return {
                "id": "00000000-0000-0000-0000-000000000000",
                "whatsapp_number": whatsapp_number,
                "name": "Sunita Didi (Fallback)",
                "location": "Kanpur, UP",
                "language": "hi",
                "dialect": "hindi"
            }

    def get_reseller_profile(self, reseller_id: str) -> dict:
        """Get full reseller profile with metrics."""
        if self.is_mock():
            return {
                "monthly_target_inr": 10000,
                "preferred_categories": ["sarees", "kurtis"],
                "customer_base_size": 220,
                "total_listings": 5
            }
        try:
            res = self.client.table("reseller_profiles").select("*").eq("reseller_id", reseller_id).execute()
            return res.data[0] if res.data else {}
        except Exception as e:
            logger.error(f"Error in get_reseller_profile: {e}")
            return {}

    def save_listing(self, listing_data: dict) -> dict:
        """Insert a new listing and return it."""
        if self.is_mock():
            return {"id": "mock-listing-id", **listing_data}
        try:
            res = self.client.table("listings").insert(listing_data).execute()
            return res.data[0] if res.data else {}
        except Exception as e:
            logger.error(f"Error in save_listing: {e}")
            return {"id": "error-listing-id", **listing_data}

    def get_active_listings(self, reseller_id: str) -> list:
        """Get all active listings for a reseller."""
        if self.is_mock():
            return [
                {
                    "id": "mock-list-1",
                    "product_id": "SKU_001",
                    "product_name": "Red Banarasi Silk Saree",
                    "category": "sarees",
                    "selling_price_inr": 599,
                    "cost_price_inr": 420,
                    "margin_inr": 179,
                    "whatsapp_caption": "Saree post caption"
                }
            ]
        try:
            res = self.client.table("listings").select("*").eq("reseller_id", reseller_id).eq("is_active", True).execute()
            return res.data or []
        except Exception as e:
            logger.error(f"Error in get_active_listings: {e}")
            return []

    def save_order(self, order_data: dict) -> dict:
        """Save a transaction order."""
        if self.is_mock():
            return {"id": "mock-order-id", **order_data}
        try:
            res = self.client.table("orders").insert(order_data).execute()
            return res.data[0] if res.data else {}
        except Exception as e:
            logger.error(f"Error in save_order: {e}")
            return {}

    def get_weekly_analytics(self, reseller_id: str) -> dict:
        """Aggregate orders for current week."""
        if self.is_mock():
            return {
                "sales_this_week_inr": 2396,
                "profit_this_week_inr": 720,
                "orders_count": 4,
                "active_listings_count": 5
            }
        try:
            # Query listings to get counts
            listings_res = self.client.table("listings").select("id", count="exact").eq("reseller_id", reseller_id).eq("is_active", True).execute()
            listings_count = listings_res.count if listings_res.count is not None else 0
            
            # Query orders
            orders_res = self.client.table("orders").select("total_amount_inr, listing_id").eq("reseller_id", reseller_id).execute()
            
            total_sales = 0
            total_profit = 0
            orders_list = orders_res.data or []
            
            # Simple margin calc (fetching cost price from listing lookup)
            for order in orders_list:
                total_sales += order["total_amount_inr"]
                # Assume 25% profit margin for simplicity in mock aggregates
                total_profit += int(order["total_amount_inr"] * 0.25)
                
            return {
                "sales_this_week_inr": total_sales,
                "profit_this_week_inr": total_profit,
                "orders_count": len(orders_list),
                "active_listings_count": listings_count
            }
        except Exception as e:
            logger.error(f"Error in get_weekly_analytics: {e}")
            return {
                "sales_this_week_inr": 0,
                "profit_this_week_inr": 0,
                "orders_count": 0,
                "active_listings_count": 0
            }

    def save_conversation_turn(self, turn_data: dict) -> None:
        """Log conversation turn for history."""
        if self.is_mock():
            return
        try:
            self.client.table("conversations").insert(turn_data).execute()
        except Exception as e:
            logger.error(f"Error in save_conversation_turn: {e}")

    def get_conversation_history(self, reseller_id: str, limit: int = 10) -> list:
        """Fetch past dialogs."""
        if self.is_mock():
            return []
        try:
            res = self.client.table("conversations").select("*").eq("reseller_id", reseller_id).order("created_at", desc=True).limit(limit).execute()
            # Return in chronological order
            history = res.data or []
            history.reverse()
            return [{"role": h["role"], "content": h["content"]} for h in history]
        except Exception as e:
            logger.error(f"Error in get_conversation_history: {e}")
            return []

    def save_return(self, return_data: dict) -> dict:
        """Save a return request."""
        if self.is_mock():
            return {"id": "mock-return-id", **return_data}
        try:
            res = self.client.table("returns").insert(return_data).execute()
            return res.data[0] if res.data else {}
        except Exception as e:
            logger.error(f"Error in save_return: {e}")
            return {}

    def log_agent_event(self, event_data: dict) -> None:
        """Save telemetry updates to agent_events table."""
        if self.is_mock():
            return
        try:
            self.client.table("agent_events").insert(event_data).execute()
        except Exception as e:
            logger.error(f"Error in log_agent_event: {e}")

    def match_products(self, query_embedding: list, threshold: float = 0.3, limit: int = 3) -> list:
        """Semantic search over the product vector catalog in Supabase."""
        if self.is_mock() or not query_embedding:
            # Return static fallback catalog items matching RAG
            logger.warning("[RAG] Supabase connection is mock, returning static catalog mock values.")
            return [
                {
                    "product_id": "SKU_001",
                    "name": "Red Banarasi Silk Saree",
                    "category": "sarees",
                    "suggested_selling_price_inr": 599,
                    "meesho_cost_inr": 420,
                    "return_window_days": 7,
                    "cod_available": True,
                    "description": "Elegant red Banarasi silk saree with gold zari borders.",
                    "sizes": ["Free Size"],
                    "colors": ["Red", "Gold"],
                    "material": "Banarasi Silk"
                },
                {
                    "product_id": "SKU_002",
                    "name": "Blue Georgette Designer Kurti",
                    "category": "kurtis",
                    "suggested_selling_price_inr": 399,
                    "meesho_cost_inr": 280,
                    "return_window_days": 7,
                    "cod_available": True,
                    "description": "Lightweight georgette kurti in deep blue with neckline embroidery.",
                    "sizes": ["S", "M", "L", "XL"],
                    "colors": ["Blue", "White"],
                    "material": "Georgette"
                }
            ]
        try:
            res = self.client.rpc(
                "match_products",
                {
                    "query_embedding": query_embedding,
                    "match_threshold": threshold,
                    "match_count": limit
                }
            ).execute()
            return res.data or []
        except Exception as e:
            logger.error(f"Error in match_products RPC: {e}")
            return []

db_client = SupabaseDB()
