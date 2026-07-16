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
    listing_id UUID REFERENCES listings(id) ON DELETE SET NULL,
    buyer_whatsapp VARCHAR(20) NOT NULL,
    quantity INTEGER DEFAULT 1,
    total_amount_inr INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'confirmed',        -- confirmed | returned | exchanged
    ordered_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

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
