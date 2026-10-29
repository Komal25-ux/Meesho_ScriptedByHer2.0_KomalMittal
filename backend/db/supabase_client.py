import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from supabase import create_client, Client
from backend.config import settings
from backend.errors import DependencyUnavailable

logger = logging.getLogger("sakhi-backend")

PRODUCT_COLUMNS = (
    "product_id,name,category,suggested_selling_price_inr,meesho_cost_inr,return_window_days,"
    "cod_available,description,sizes,colors,material,base_image_url"
)

def _unavailable(operation: str, error: Exception) -> DependencyUnavailable:
    logger.error(f"Supabase {operation} failed: {error}")
    return DependencyUnavailable(f"Supabase {operation} failed")


class SupabaseDB:
    """Every method below either returns real data or raises
    DependencyUnavailable - except the two telemetry writes
    (save_conversation_turn, log_agent_event), which only log, since a lost
    trace line must never fail a user's turn. With no credentials the client
    runs in mock mode for local development; production refuses to start in
    that state rather than serve demo data as if it were real."""

    def __init__(self):
        self.url = settings.SUPABASE_URL
        self.key = settings.SUPABASE_SERVICE_KEY
        self.client = None
        self._mock_orders = []  # mock mode only, so local runs dedupe orders too

        # Safe initialization
        if self.url and self.key and "YOUR_SUPABASE" not in self.url and "YOUR_SUPABASE" not in self.key:
            try:
                self.client: Client = create_client(self.url, self.key)
                logger.info("[SUCCESS] Supabase Client Initialized.")
            except Exception as e:
                logger.error(f"[ERROR] Failed to initialize Supabase client: {e}")
        else:
            logger.warning("[WARNING] Supabase credentials missing or set to placeholder. Database will run in MOCK mode.")

        if self.client is None and settings.ENVIRONMENT == "production":
            raise RuntimeError(
                "ENVIRONMENT=production but Supabase is not configured or failed to initialise; "
                "refusing to start on mock data"
            )

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
            raise _unavailable("get_or_create_reseller", e) from e

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
            raise _unavailable("get_reseller_profile", e) from e

    def save_listing(self, listing_data: dict) -> dict:
        """Insert a new listing and return it."""
        if self.is_mock():
            return {"id": "mock-listing-id", **listing_data}
        try:
            res = self.client.table("listings").insert(listing_data).execute()
        except Exception as e:
            raise _unavailable("save_listing", e) from e
        if not res.data:
            raise DependencyUnavailable("Supabase save_listing returned no row")
        return res.data[0]

    def get_listing(self, reseller_id: str, product_id: str) -> Optional[dict]:
        """This reseller's live listing of a product - {"id", "selling_price_inr"}
        - or None if she hasn't listed it. A confirmed order can legitimately
        come before the listing does, so None is a normal answer, not an
        error. The newest listing wins if the product was listed twice."""
        if self.is_mock():
            return {"id": "mock-listing-id", "selling_price_inr": 599} if product_id == "SKU_001" else None
        try:
            res = (
                self.client.table("listings").select("id,selling_price_inr")
                .eq("reseller_id", reseller_id).eq("product_id", product_id).eq("is_active", True)
                .order("created_at", desc=True).limit(1).execute()
            )
        except Exception as e:
            raise _unavailable("get_listing", e) from e
        return res.data[0] if res.data else None

    def find_recent_order(self, session_id: str, product_id: str, within: timedelta) -> Optional[dict]:
        """The newest order this conversation placed for this product within
        `within`, if any. A second "order kar do" for the same product soon
        after the first - typically re-typed after an error - is the same
        order, not a new one."""
        cutoff = datetime.now(timezone.utc) - within
        if self.is_mock():
            matches = [
                o for o in self._mock_orders
                if o.get("session_id") == session_id and o.get("product_id") == product_id and o["ordered_at"] >= cutoff
            ]
            return dict(matches[-1]) if matches else None
        try:
            res = (
                self.client.table("orders").select("*")
                .eq("session_id", session_id).eq("product_id", product_id).gte("ordered_at", cutoff.isoformat())
                .order("ordered_at", desc=True).limit(1).execute()
            )
        except Exception as e:
            raise _unavailable("find_recent_order", e) from e
        return res.data[0] if res.data else None

    def save_order(self, order_data: dict) -> dict:
        """Insert an order and return the stored row. With a client_message_id
        the write is idempotent: orders.client_message_id is unique, so a
        replay of the same request - even one racing the original - gets the
        order that request already created instead of a second one."""
        if self.is_mock():
            key = order_data.get("client_message_id")
            existing = next((o for o in self._mock_orders if key and o.get("client_message_id") == key), None)
            if existing:
                return dict(existing)
            row = {"id": f"mock-order-{len(self._mock_orders) + 1}", "ordered_at": datetime.now(timezone.utc), **order_data}
            self._mock_orders.append(row)
            return dict(row)
        key = order_data.get("client_message_id")
        try:
            if not key:
                res = self.client.table("orders").insert(order_data).execute()
            else:
                res = self.client.table("orders").upsert(
                    order_data, on_conflict="client_message_id", ignore_duplicates=True
                ).execute()
                if not res.data:  # a duplicate: nothing inserted, return the original
                    res = self.client.table("orders").select("*").eq("client_message_id", key).limit(1).execute()
        except Exception as e:
            raise _unavailable("save_order", e) from e
        if not res.data:
            raise DependencyUnavailable("Supabase save_order returned no row")
        return res.data[0]

    def save_conversation_turn(self, turn_data: dict) -> None:
        """Log conversation turn for history."""
        if self.is_mock():
            return
        try:
            self.client.table("conversations").insert(turn_data).execute()
        except Exception as e:
            logger.error(f"Error in save_conversation_turn: {e}")

    def save_return(self, return_data: dict) -> dict:
        """Save a return request."""
        if self.is_mock():
            return {"id": "mock-return-id", **return_data}
        try:
            res = self.client.table("returns").insert(return_data).execute()
        except Exception as e:
            raise _unavailable("save_return", e) from e
        if not res.data:
            raise DependencyUnavailable("Supabase save_return returned no row")
        return res.data[0]

    def log_agent_event(self, event_data: dict) -> None:
        """Save telemetry updates to agent_events table."""
        if self.is_mock():
            return
        try:
            self.client.table("agent_events").insert(event_data).execute()
        except Exception as e:
            logger.error(f"Error in log_agent_event: {e}")

    def get_product_by_name(self, product_name: str) -> Optional[dict]:
        """Exact (case-insensitive) name lookup. Used to resolve a reseller's/
        customer's tap on a ProductGrid option deterministically - the frontend
        sends the option's exact name back as the next message (see
        check_pending_selection / run_catalog_agent / run_customer_agent in
        orchestrator.py) - instead of re-running an ambiguous vector search
        that could resurface the same cluster of similarly-named SKUs."""
        if not product_name:
            return None
        if self.is_mock():
            for p in self.match_products([], limit=10):
                if p.get("name", "").strip().lower() == product_name.strip().lower():
                    return p
            return None
        try:
            # Every column except the 768-float embedding, which nothing reads
            # and which would otherwise be copied into session state with the
            # product (see LAST_VIEWED_PRODUCT).
            res = self.client.table("product_embeddings").select(PRODUCT_COLUMNS).ilike("name", product_name.strip()).limit(1).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            raise _unavailable("get_product_by_name", e) from e

    def match_products(
        self,
        query_embedding: list,
        threshold: float = 0.3,
        limit: int = 3,
        category_filter: Optional[str] = None,
        exclude_ids: Optional[list] = None,
    ) -> list:
        """Semantic search over the product vector catalog in Supabase.

        category_filter/exclude_ids power category-strict pagination (see
        run_customer_agent/run_catalog_agent's "show more" handling). They are
        applied inside Postgres by match_products_filtered (supabase_schema.sql
        section 14), so the database returns exactly `limit` rows that pass
        the filters. This used to over-fetch up to 100 candidates and filter
        them in Python, which only worked because the catalog is small.
        """
        exclude_set = set(exclude_ids or [])

        def _apply_filters(items: list) -> list:
            filtered = [
                p for p in items
                if p.get("product_id") not in exclude_set
                and (category_filter is None or p.get("category") == category_filter)
            ]
            return filtered[:limit]

        if not self.is_mock() and not query_embedding:
            # No query to search with (an empty message). This used to fall
            # into the mock branch below and return the demo catalog as if
            # it were a real search result.
            return []
        if self.is_mock():
            # Return static fallback catalog items matching RAG
            logger.warning("[RAG] Supabase connection is mock, returning static catalog mock values.")
            mock_catalog = [
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
                    "material": "Banarasi Silk",
                    "base_image_url": "https://images.unsplash.com/photo-1654764746225-e63f5e90facd?w=600&q=80"
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
                    "material": "Georgette",
                    "base_image_url": "https://images.unsplash.com/photo-1769063382706-8156b3b33eac?w=600&q=80"
                }
            ]
            return _apply_filters(mock_catalog)
        # A category browse ("aur saree dikhao") drops the similarity threshold:
        # a generic "show more" phrase barely resembles any one product, and
        # every item in the category is a valid answer, so the threshold
        # would only end the browse early with items still unseen.
        params = {
            "query_embedding": query_embedding,
            "match_threshold": 0.0 if category_filter else threshold,
            "match_count": limit,
        }
        if category_filter or exclude_set:
            rpc_name = "match_products_filtered"
            params["category_filter"] = category_filter
            params["exclude_ids"] = sorted(exclude_set)
        else:
            rpc_name = "match_products"
        try:
            res = self.client.rpc(rpc_name, params).execute()
            return res.data or []
        except Exception as e:
            raise _unavailable("match_products", e) from e

db_client = SupabaseDB()
