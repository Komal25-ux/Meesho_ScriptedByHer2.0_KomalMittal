-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Resellers Table
CREATE TABLE IF NOT EXISTS resellers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    whatsapp_number VARCHAR(30) UNIQUE NOT NULL,  -- e.g. "whatsapp:+919876543210" or "whatsapp:+123456"
    name VARCHAR(100) NOT NULL,
    location VARCHAR(100),                         -- e.g. "Kanpur, UP"
    language VARCHAR(10) DEFAULT 'hi',             -- ISO language code (default hi)
    dialect VARCHAR(50) DEFAULT 'hindi',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Reseller Profiles Table
CREATE TABLE IF NOT EXISTS reseller_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reseller_id UUID REFERENCES resellers(id) ON DELETE CASCADE UNIQUE,
    monthly_target_inr INTEGER DEFAULT 10000,
    preferred_categories TEXT[],                   -- e.g. ["sarees", "kurtis"]
    customer_base_size INTEGER DEFAULT 0,
    total_listings INTEGER DEFAULT 0,
    active_since DATE DEFAULT CURRENT_DATE,
    last_growth_note_sent TIMESTAMPTZ
);

-- 4. Listings Table (Reseller-specific listings)
CREATE TABLE IF NOT EXISTS listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reseller_id UUID REFERENCES resellers(id) ON DELETE CASCADE,
    product_id VARCHAR(50) NOT NULL,               -- References SKU in catalog
    product_name TEXT NOT NULL,
    category VARCHAR(100),
    selling_price_inr INTEGER NOT NULL,
    cost_price_inr INTEGER NOT NULL,
    margin_inr INTEGER GENERATED ALWAYS AS (selling_price_inr - cost_price_inr) STORED,
    whatsapp_caption TEXT,                         -- Generated Hinglish caption
    image_url TEXT,                                -- Imagen 3 image URL
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Orders Table
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reseller_id UUID REFERENCES resellers(id) ON DELETE CASCADE,
    listing_id UUID REFERENCES listings(id) ON DELETE SET NULL,  -- NULL when the product wasn't yet listed by this reseller at order time
    buyer_whatsapp VARCHAR(30) NOT NULL,  -- matches resellers.whatsapp_number's width - "whatsapp:+91XXXXXXXXXX" is 22+ chars, VARCHAR(20) truncated/rejected real inserts
    quantity INTEGER DEFAULT 1,
    total_amount_inr INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'confirmed',        -- confirmed | returned | exchanged
    -- Denormalized product snapshot AT THE MOMENT OF CONFIRMATION. This is
    -- deliberate duplication, not an oversight: listing_id/product_embeddings
    -- data can change later (price renegotiated, listing deactivated) or may
    -- not exist at all yet (unlisted-product purchase, listing_id NULL above),
    -- so the reseller notification and any later audit must read the exact
    -- product identity/price/variant options that were true AT CHECKOUT from
    -- this row directly - never re-derived via a join or re-fetched from
    -- mutable session/catalog state after the fact.
    product_id VARCHAR(50),
    product_name TEXT,
    unit_price_inr INTEGER,
    available_sizes TEXT[],
    available_colors TEXT[],
    ordered_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Migration safety net: CREATE TABLE IF NOT EXISTS above is a no-op against an
-- orders table that already existed before the product-snapshot columns were
-- added, so re-running this file alone would silently NOT backfill them on an
-- existing database. These are idempotent and safe to re-run.
ALTER TABLE orders ADD COLUMN IF NOT EXISTS product_id VARCHAR(50);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS product_name TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS unit_price_inr INTEGER;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS available_sizes TEXT[];
ALTER TABLE orders ADD COLUMN IF NOT EXISTS available_colors TEXT[];
-- Pre-existing bug, unrelated to the columns above: buyer_whatsapp was
-- VARCHAR(20), too narrow for this app's "whatsapp:+91XXXXXXXXXX" format
-- (22+ chars) - every real insert was rejected with "value too long for
-- type character varying(20)". Safe to re-run even if already widened.
ALTER TABLE orders ALTER COLUMN buyer_whatsapp TYPE VARCHAR(30);

-- 6. Returns Table
CREATE TABLE IF NOT EXISTS returns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID REFERENCES orders(id) ON DELETE CASCADE,
    reason VARCHAR(50) NOT NULL,                   -- size_issue | color | expectation | defect | other
    resolution VARCHAR(20) DEFAULT 'pending',      -- exchange | refund | saved | pending
    conversation_log JSONB,                        -- Full multi-turn conversation logs
    resolved_at TIMESTAMPTZ
);

-- 7. Conversations Table (History buffer for agents)
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reseller_id UUID REFERENCES resellers(id) ON DELETE CASCADE,
    session_id VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL,                     -- user | assistant | system
    content TEXT NOT NULL,
    agent_used VARCHAR(50),                        -- catalog | customer | growth | returns | orchestrator
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 8. Agent Events Table (Broadcasting logs to Judge UI)
CREATE TABLE IF NOT EXISTS agent_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(50) NOT NULL,               -- intent_detected | rag_retrieval | tts_generated
    agent_name VARCHAR(50) NOT NULL,               -- Orchestrator | CatalogAgent | etc.
    latency_ms INTEGER,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 9. Product Embeddings Table (Master catalog with vector support)
CREATE TABLE IF NOT EXISTS product_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id VARCHAR(50) UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category VARCHAR(100),
    suggested_selling_price_inr INTEGER,
    meesho_cost_inr INTEGER,
    return_window_days INTEGER DEFAULT 7,
    cod_available BOOLEAN DEFAULT true,
    description TEXT,
    sizes TEXT[],                                  -- e.g. ARRAY['S','M','L','XL'] or ARRAY['Free Size']
    colors TEXT[],                                 -- e.g. ARRAY['Yellow','Gold']
    material VARCHAR(100),                         -- e.g. "Chanderi Cotton"
    base_image_url TEXT,                           -- real stock photo of the product (not AI-generated)
    embedding VECTOR(768)                          -- Gemini text-embedding-004 has 768 dimensions
);

-- 10. Vector Similarity Search Function (RPC)
CREATE OR REPLACE FUNCTION match_products (
  query_embedding VECTOR(768),
  match_threshold FLOAT,
  match_count INT
)
RETURNS TABLE (
  product_id VARCHAR(50),
  name TEXT,
  category VARCHAR(100),
  suggested_selling_price_inr INTEGER,
  meesho_cost_inr INTEGER,
  return_window_days INTEGER,
  cod_available BOOLEAN,
  description TEXT,
  sizes TEXT[],
  colors TEXT[],
  material VARCHAR(100),
  base_image_url TEXT,
  similarity FLOAT
)
LANGUAGE sql STABLE
AS $$
  SELECT
    product_id,
    name,
    category,
    suggested_selling_price_inr,
    meesho_cost_inr,
    return_window_days,
    cod_available,
    description,
    sizes,
    colors,
    material,
    base_image_url,
    1 - (product_embeddings.embedding <=> query_embedding) as similarity
  FROM product_embeddings
  WHERE 1 - (product_embeddings.embedding <=> query_embedding) > match_threshold
  ORDER BY product_embeddings.embedding <=> query_embedding
  LIMIT match_count;
$$;

-- 11. Row-Level Security
-- The backend only ever talks to Supabase via SUPABASE_SERVICE_KEY
-- (backend/db/supabase_client.py), and the service_role key bypasses RLS
-- entirely - so enabling RLS here has no effect on the app. Without it,
-- every table below is readable/writable by anyone holding the project's
-- anon key via the PostgREST API, which is what Supabase's linter flags as
-- "Table publicly accessible" / "Sensitive data publicly accessible"
-- (resellers.whatsapp_number, orders.buyer_whatsapp, etc. are PII).
-- No policies are created, so RLS defaults to deny-all for anon/authenticated.
ALTER TABLE resellers ENABLE ROW LEVEL SECURITY;
ALTER TABLE reseller_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE listings ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE returns ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE product_embeddings ENABLE ROW LEVEL SECURITY;

-- 12. Performance Indexes
-- Every table's own UUID PK and any UNIQUE constraint above (whatsapp_number,
-- product_id) already have an implicit index - these are the additional ones
-- backend/db/supabase_client.py's actual query patterns need but don't get
-- for free. Idempotent/safe to re-run.

-- get_listing filters
-- listings by (reseller_id, is_active) together - a composite index matches
-- that WHERE shape directly (and still serves reseller_id-only lookups via
-- the leftmost-prefix rule).
CREATE INDEX IF NOT EXISTS idx_listings_reseller_active
  ON listings(reseller_id, is_active);

-- A reseller's orders are looked up by reseller_id (sales reporting).
CREATE INDEX IF NOT EXISTS idx_orders_reseller_id
  ON orders(reseller_id);

-- Reading a reseller's recent turns (newest first, with a LIMIT) filters by
-- reseller_id AND sorts by created_at DESC - the composite index matches both
-- the filter and the sort. The app itself only writes this table today.
CREATE INDEX IF NOT EXISTS idx_conversations_reseller_created
  ON conversations(reseller_id, created_at DESC);

-- match_products' RPC does a `<=>` (cosine distance) ORDER BY over every row
-- with no index today, i.e. a full sequential scan + distance calc per
-- query - fine at this catalog's current size, but grows linearly worse as
-- it does. HNSW (vector_cosine_ops, matching the `<=>` operator used in the
-- RPC) needs no upfront training step unlike ivfflat, so it's safe to create
-- even on a small/empty table and stays effective as the catalog grows.
CREATE INDEX IF NOT EXISTS idx_product_embeddings_embedding_hnsw
  ON product_embeddings USING hnsw (embedding vector_cosine_ops);

-- 13. Conversation State Between Turns
-- Each /chat/send call runs the agent graph from scratch, so whatever the next
-- turn must know (a draft awaiting approval, a return in progress, the product
-- under discussion) is stored here - see backend/core/session.py. One row per
-- (conversation, slot); session_key is "<browser session uuid>::<mode>".
-- Keeping it in Postgres instead of process memory means it survives restarts
-- and redeploys and is shared by every backend instance.
CREATE TABLE IF NOT EXISTS session_state (
    session_key TEXT NOT NULL,
    slot VARCHAR(50) NOT NULL,                     -- pending_listings | pending_returns | ...
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,               -- reads ignore expired rows
    PRIMARY KEY (session_key, slot)
);

-- Lets expired rows be swept cheaply, e.g. from a scheduled job:
--   DELETE FROM session_state WHERE expires_at < NOW();
CREATE INDEX IF NOT EXISTS idx_session_state_expires_at
  ON session_state(expires_at);

-- Same reasoning as section 11: only the service-role backend touches it.
ALTER TABLE session_state ENABLE ROW LEVEL SECURITY;

-- 14. Filtered Vector Similarity Search (RPC)
-- Same search as match_products, plus the category and "already shown" filters
-- that category-strict pagination needs ("aur saree dikhao"), applied here so
-- the database returns exactly match_count matching rows. Before this existed
-- the backend over-fetched 100 rows and filtered them in Python.
CREATE OR REPLACE FUNCTION match_products_filtered (
  query_embedding VECTOR(768),
  match_threshold FLOAT,
  match_count INT,
  category_filter VARCHAR(100) DEFAULT NULL,
  exclude_ids VARCHAR(50)[] DEFAULT '{}'
)
RETURNS TABLE (
  product_id VARCHAR(50),
  name TEXT,
  category VARCHAR(100),
  suggested_selling_price_inr INTEGER,
  meesho_cost_inr INTEGER,
  return_window_days INTEGER,
  cod_available BOOLEAN,
  description TEXT,
  sizes TEXT[],
  colors TEXT[],
  material VARCHAR(100),
  base_image_url TEXT,
  similarity FLOAT
)
LANGUAGE sql STABLE
AS $$
  SELECT
    p.product_id,
    p.name,
    p.category,
    p.suggested_selling_price_inr,
    p.meesho_cost_inr,
    p.return_window_days,
    p.cod_available,
    p.description,
    p.sizes,
    p.colors,
    p.material,
    p.base_image_url,
    1 - (p.embedding <=> query_embedding) AS similarity
  FROM product_embeddings p
  WHERE (category_filter IS NULL OR p.category = category_filter)
    AND NOT (p.product_id = ANY (exclude_ids))
    AND 1 - (p.embedding <=> query_embedding) > match_threshold
  ORDER BY p.embedding <=> query_embedding
  LIMIT match_count;
$$;

-- Lets the planner narrow to one category before ranking by distance. At a
-- much larger catalog, an HNSW scan with a WHERE clause can return fewer than
-- match_count rows (it only looks at ef_search candidates, then filters);
-- pgvector 0.8+ fixes that with SET hnsw.iterative_scan = relaxed_order.
CREATE INDEX IF NOT EXISTS idx_product_embeddings_category
  ON product_embeddings(category);

-- 15. Duplicate-Order Protection
-- client_message_id is the frontend's id for one chat message, resent
-- unchanged when the request is retried; unique, so a replay can never insert
-- a second order (backend save_order upserts with ignore-duplicates on it).
-- session_id lets a re-typed confirmation of the same product be matched to
-- the order already placed a few minutes earlier (find_recent_order).
ALTER TABLE orders ADD COLUMN IF NOT EXISTS session_id TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS client_message_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS orders_client_message_id_key
  ON orders(client_message_id);
CREATE INDEX IF NOT EXISTS idx_orders_session_product_recent
  ON orders(session_id, product_id, ordered_at DESC);
