# SAKHI — Product Requirements Document (PRD)
## Version 1.0 | ScriptedBy{Her} 2.0 — Round 3 Prototype Build
### Prepared by: Team Orchestrator | Build Window: 13–19 July 2026

---

## TABLE OF CONTENTS

1. [Product Overview](#1-product-overview)
2. [Technical Architecture](#2-technical-architecture)
3. [Repository Structure](#3-repository-structure)
4. [Environment Setup](#4-environment-setup)
5. [Database Schema](#5-database-schema)
6. [Core Modules — Detailed Specs](#6-core-modules--detailed-specs)
   - 6.1 [WhatsApp Gateway (Twilio)](#61-whatsapp-gateway-twilio)
   - 6.2 [Voice Layer — Vaani (ASR + TTS)](#62-voice-layer--vaani-asr--tts)
   - 6.3 [Orchestrator Agent](#63-orchestrator-agent)
   - 6.4 [Catalog Agent](#64-catalog-agent)
   - 6.5 [Customer Agent](#65-customer-agent)
   - 6.6 [Growth Agent](#66-growth-agent)
   - 6.7 [Returns Agent](#67-returns-agent)
   - 6.8 [Mock Meesho Catalog](#68-mock-meesho-catalog)
   - 6.9 [Memory Layer (Supabase + ChromaDB)](#69-memory-layer-supabase--chromadb)
7. [API Endpoints](#7-api-endpoints)
8. [Streamlit Dashboard (Backup Demo)](#8-streamlit-dashboard-backup-demo)
9. [End-to-End Flow — Step by Step](#9-end-to-end-flow--step-by-step)
10. [Demo Scenarios (Judge-Ready)](#10-demo-scenarios-judge-ready)
11. [Open-Source Attribution](#11-open-source-attribution)
12. [Deployment Guide](#12-deployment-guide)
13. [README Template](#13-readme-template)
14. [Day-by-Day Build Plan](#14-day-by-day-build-plan)
15. [Testing Checklist](#15-testing-checklist)

---

## 1. PRODUCT OVERVIEW

### 1.1 What is Sakhi?

Sakhi is an **agentic AI co-pilot** that runs a Meesho reseller's entire business through WhatsApp — in her own language (Hindi/Indic) and her own voice. It is a **multi-agent system** with four specialist agents coordinated by a central orchestrator, each with long-term memory of the reseller's business.

### 1.2 The Core Promise

> "No app to download. No English to learn. She just talks to Sakhi like a friend."

A reseller sends a **voice note in Hindi** on WhatsApp. Within **~5 seconds**, Sakhi responds — also in a Hindi voice note — having understood the intent, routed it to the right specialist agent, executed the appropriate tool, and drafted a warm, vernacular reply.

### 1.3 The Four Specialist Agents

| Agent | Friendly Name | Primary Job |
|---|---|---|
| Catalog Agent | Catalog Didi | Product link/photo → vernacular WhatsApp post + auto-priced listing |
| Customer Agent | Customer Didi | Answers buyer queries 24×7 in their language via RAG |
| Growth Agent | Growth Didi | Weekly Hindi voice note coaching on sales, trends, festival calendar |
| Returns Agent | Returns Didi | Converts returns into exchanges via kind vernacular conversation |

### 1.4 Target User

**Primary:** Meesho reseller — female, Tier 2/3/4 town, Hindi-speaking, low-to-moderate digital literacy, earns ₹4,000–₹10,000/month, sells via WhatsApp groups.

**Persona:** Sunita, 34, Kanpur. Meesho reseller since 2022. Sells sarees to 200+ WhatsApp customers. Earns ₹6,200/month. Spends 4 hours/day on manual reseller tasks.

### 1.5 Success Criteria for Round 3

- [ ] End-to-end voice note round-trip works (Sunita speaks → Sakhi replies in voice)
- [ ] Catalog Agent produces a real WhatsApp-ready Hindi post from a product input
- [ ] Customer Agent answers a product query using RAG (not hallucination)
- [ ] Growth Agent sends a pre-scheduled weekly Hindi voice note with real sales insight
- [ ] Returns Agent runs a sympathetic returns conversation flow
- [ ] Streamlit dashboard shows live agent activity (backup demo)
- [ ] GitHub repo is public with a complete README
- [ ] Live deployment URL accessible to judges
- [ ] Open-source attribution declared for every dependency

---

## 2. TECHNICAL ARCHITECTURE

### 2.1 System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER LAYER                                   │
│  Sunita (WhatsApp) ←──────────────────→ Buyer (WhatsApp)           │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ HTTP Webhook
┌─────────────────────────▼───────────────────────────────────────────┐
│                     GATEWAY LAYER                                   │
│                  Twilio WhatsApp Sandbox                            │
│         (receives audio/text, sends audio/text/media)               │
└─────────────────────────┬───────────────────────────────────────────┘
                          │ POST /webhook
┌─────────────────────────▼───────────────────────────────────────────┐
│                     BACKEND LAYER                                   │
│                   FastAPI Application                               │
│              (Render / Railway free tier)                           │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    VAANI LAYER (Voice)                       │  │
│  │  Audio In → Sarvam Saarika (ASR) → Text                     │  │
│  │  Text → Sarvam Bulbul (TTS) → Audio Out                     │  │
│  │  Fallback ASR: OpenAI Whisper (local)                       │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                          │                                          │
│  ┌───────────────────────▼──────────────────────────────────────┐  │
│  │                  ORCHESTRATOR AGENT                          │  │
│  │         Gemini 2.5 Flash + LangGraph State Machine          │  │
│  │  • Intent Detection                                         │  │
│  │  • Reseller Memory Load (Supabase)                         │  │
│  │  • Agent Routing                                            │  │
│  │  • Response Assembly                                        │  │
│  └───────┬───────────┬──────────────┬───────────────┬──────────┘  │
│          │           │              │               │              │
│  ┌───────▼──┐ ┌──────▼───┐ ┌───────▼──┐ ┌──────────▼──┐         │
│  │ CATALOG  │ │ CUSTOMER │ │  GROWTH  │ │   RETURNS   │         │
│  │  AGENT   │ │  AGENT   │ │  AGENT   │ │    AGENT    │         │
│  └───────┬──┘ └──────┬───┘ └───────┬──┘ └──────────┬──┘         │
│          │           │              │               │              │
└──────────┼───────────┼──────────────┼───────────────┼──────────────┘
           │           │              │               │
┌──────────▼───────────▼──────────────▼───────────────▼──────────────┐
│                        DATA LAYER                                   │
│  ┌─────────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Mock Meesho    │  │  ChromaDB    │  │      Supabase        │  │
│  │  Catalog (JSON) │  │  (RAG/Vector)│  │  (Memory + Sales)    │  │
│  │  ~500 SKUs      │  │              │  │                      │  │
│  └─────────────────┘  └──────────────┘  └──────────────────────┘  │
│  ┌─────────────────┐                                               │
│  │  Gemini Imagen  │                                               │
│  │  (Creatives)    │                                               │
│  └─────────────────┘                                               │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Tech Stack Summary

| Layer | Primary Tool | Fallback | License | Cost |
|---|---|---|---|---|
| WhatsApp Interface | Twilio Sandbox | — | Proprietary (free tier) | ₹0 |
| ASR (Voice→Text) | Sarvam Saarika API | OpenAI Whisper (local) | Proprietary / MIT | ₹0 |
| TTS (Text→Voice) | Sarvam Bulbul API | gTTS | Proprietary / Apache 2.0 | ₹0 |
| LLM / Reasoning | Gemini 2.5 Flash | Groq + Llama-3.1-8B | Proprietary (free tier) | ₹0 |
| Agent Orchestration | LangGraph | Raw Python FSM | MIT | ₹0 |
| Vector DB / RAG | ChromaDB (local) | Pinecone free tier | Apache 2.0 | ₹0 |
| Relational DB | Supabase (PostgreSQL) | SQLite (local) | Apache 2.0 | ₹0 |
| Image Generation | Gemini Imagen | Stability AI free | Proprietary (free) | ₹0 |
| Backend Framework | FastAPI | Flask | MIT | ₹0 |
| Hosting | Render free tier | Railway $5 credit | — | ₹0 |
| Backup Demo UI | Streamlit | — | Apache 2.0 | ₹0 |
| Tunneling (dev) | ngrok | localtunnel | MIT | ₹0 |

---

## 3. REPOSITORY STRUCTURE

```
sakhi/
├── README.md                          # Full setup + run guide
├── requirements.txt                   # All Python dependencies + versions
├── .env.example                       # All required environment variables
├── .gitignore
├── app/
│   ├── __init__.py
│   ├── main.py                        # FastAPI app entry point
│   ├── config.py                      # Environment config loader
│   ├── models.py                      # Pydantic models / schemas
│   │
│   ├── gateway/
│   │   ├── __init__.py
│   │   ├── twilio_handler.py          # Webhook receiver + Twilio send utils
│   │   └── media_utils.py            # Audio download, format conversion
│   │
│   ├── vaani/
│   │   ├── __init__.py
│   │   ├── asr.py                     # Sarvam Saarika ASR + Whisper fallback
│   │   └── tts.py                     # Sarvam Bulbul TTS + gTTS fallback
│   │
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── graph.py                   # LangGraph state machine definition
│   │   ├── intent.py                  # Intent classification prompt + parser
│   │   ├── router.py                  # Routes intent → correct agent
│   │   └── memory.py                  # Load/save reseller memory from Supabase
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── catalog_agent.py           # Catalog Didi
│   │   ├── customer_agent.py          # Customer Didi
│   │   ├── growth_agent.py            # Growth Didi
│   │   └── returns_agent.py           # Returns Didi
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── catalog_search.py          # Search mock catalog by query
│   │   ├── rag_engine.py              # ChromaDB RAG for customer agent
│   │   ├── image_gen.py               # Gemini Imagen creative generation
│   │   ├── sales_analytics.py         # Sales summary + trend detection
│   │   └── festival_calendar.py       # Indian festival calendar utility
│   │
│   ├── data/
│   │   ├── mock_catalog.json          # ~500 Meesho-style product SKUs
│   │   └── festival_calendar.json     # Indian festival dates 2025–2026
│   │
│   └── db/
│       ├── __init__.py
│       ├── supabase_client.py         # Supabase connection + CRUD
│       └── chroma_client.py           # ChromaDB setup + ingestion
│
├── dashboard/
│   ├── app.py                         # Streamlit backup demo dashboard
│   └── components/
│       ├── agent_status.py            # Live agent activity panel
│       ├── chat_simulator.py          # WhatsApp chat UI simulator
│       └── analytics.py              # Reseller sales charts
│
├── scripts/
│   ├── seed_catalog.py                # Seeds mock catalog into ChromaDB
│   ├── seed_reseller.py               # Creates test reseller in Supabase
│   └── test_flow.py                   # End-to-end test runner
│
└── tests/
    ├── test_asr.py
    ├── test_tts.py
    ├── test_orchestrator.py
    ├── test_catalog_agent.py
    ├── test_customer_agent.py
    ├── test_growth_agent.py
    └── test_returns_agent.py
```

---

## 4. ENVIRONMENT SETUP

### 4.1 Required Environment Variables (.env)

```env
# ── TWILIO ──────────────────────────────────────────────
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
TWILIO_SANDBOX_NUMBER=whatsapp:+14155238886

# ── SARVAM AI ───────────────────────────────────────────
SARVAM_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SARVAM_ASR_URL=https://api.sarvam.ai/speech-to-text
SARVAM_TTS_URL=https://api.sarvam.ai/text-to-speech
SARVAM_ASR_LANGUAGE=hi-IN
SARVAM_TTS_LANGUAGE=hi-IN
SARVAM_TTS_SPEAKER=meera          # Options: meera, pavithra, maitreyi

# ── GOOGLE GEMINI ───────────────────────────────────────
GEMINI_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GEMINI_MODEL=gemini-2.5-flash
GEMINI_IMAGE_MODEL=imagen-3.0-generate-001

# ── GROQ (FALLBACK LLM) ─────────────────────────────────
GROQ_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GROQ_MODEL=llama-3.1-8b-instant

# ── SUPABASE ────────────────────────────────────────────
SUPABASE_URL=https://xxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SUPABASE_SERVICE_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ── CHROMADB ────────────────────────────────────────────
CHROMA_PERSIST_DIR=./chroma_db
CHROMA_COLLECTION_NAME=meesho_catalog

# ── APP CONFIG ──────────────────────────────────────────
APP_ENV=development                  # development | production
APP_HOST=0.0.0.0
APP_PORT=8000
WEBHOOK_BASE_URL=https://your-ngrok-url.ngrok.io  # update for prod

# ── FEATURE FLAGS ───────────────────────────────────────
USE_VOICE_INPUT=true
USE_VOICE_OUTPUT=true
USE_IMAGE_GEN=true
FALLBACK_TO_WHISPER=true
FALLBACK_TO_GROQ=true
```

### 4.2 Installation

```bash
# Clone the repo
git clone https://github.com/yourusername/sakhi.git
cd sakhi

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and fill environment variables
cp .env.example .env
# → Fill in all API keys in .env

# Seed the database
python scripts/seed_catalog.py      # Loads mock catalog into ChromaDB
python scripts/seed_reseller.py     # Creates test reseller (Sunita) in Supabase

# Start ngrok tunnel (dev only)
ngrok http 8000

# Update WEBHOOK_BASE_URL in .env with your ngrok URL

# Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# In a separate terminal — start Streamlit dashboard
streamlit run dashboard/app.py
```

### 4.3 requirements.txt (with versions)

```
fastapi==0.111.0
uvicorn==0.30.1
python-multipart==0.0.9
httpx==0.27.0
pydantic==2.7.3
pydantic-settings==2.3.1
python-dotenv==1.0.1

# Twilio
twilio==9.2.3

# LangGraph + LangChain
langgraph==0.1.19
langchain==0.2.6
langchain-google-genai==1.0.6
langchain-groq==0.1.6

# Google Gemini
google-generativeai==0.7.2

# Sarvam (REST calls via httpx — no SDK needed)
# OpenAI Whisper fallback
openai-whisper==20231117
torch==2.3.0

# ChromaDB
chromadb==0.5.3
sentence-transformers==3.0.1

# Supabase
supabase==2.5.0

# Audio processing
pydub==0.25.1
ffmpeg-python==0.2.0

# Image generation
pillow==10.3.0

# Utilities
schedule==1.2.1
pytz==2024.1
requests==2.32.3

# Dashboard
streamlit==1.36.0
plotly==5.22.0
pandas==2.2.2

# Testing
pytest==8.2.2
pytest-asyncio==0.23.7
```

---

## 5. DATABASE SCHEMA

### 5.1 Supabase Tables (PostgreSQL)

#### Table: `resellers`
```sql
CREATE TABLE resellers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    whatsapp_number VARCHAR(20) UNIQUE NOT NULL,  -- e.g. "whatsapp:+919876543210"
    name VARCHAR(100),
    location VARCHAR(100),                         -- e.g. "Kanpur, UP"
    language VARCHAR(10) DEFAULT 'hi',             -- ISO language code
    dialect VARCHAR(50) DEFAULT 'hindi',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### Table: `reseller_profiles`
```sql
CREATE TABLE reseller_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reseller_id UUID REFERENCES resellers(id) ON DELETE CASCADE,
    monthly_target_inr INTEGER DEFAULT 10000,
    preferred_categories TEXT[],                   -- ["sarees","kurtis"]
    customer_base_size INTEGER DEFAULT 0,
    total_listings INTEGER DEFAULT 0,
    active_since DATE,
    last_growth_note_sent TIMESTAMPTZ,
    UNIQUE(reseller_id)
);
```

#### Table: `listings`
```sql
CREATE TABLE listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reseller_id UUID REFERENCES resellers(id) ON DELETE CASCADE,
    product_id VARCHAR(50),                        -- from mock catalog
    product_name TEXT NOT NULL,
    category VARCHAR(100),
    selling_price_inr INTEGER NOT NULL,
    cost_price_inr INTEGER,
    margin_inr INTEGER GENERATED ALWAYS AS (selling_price_inr - cost_price_inr) STORED,
    whatsapp_caption TEXT,                         -- generated Hindi caption
    image_url TEXT,                               -- generated creative URL
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### Table: `orders`
```sql
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reseller_id UUID REFERENCES resellers(id) ON DELETE CASCADE,
    listing_id UUID REFERENCES listings(id),
    buyer_whatsapp VARCHAR(20),
    quantity INTEGER DEFAULT 1,
    total_amount_inr INTEGER,
    status VARCHAR(20) DEFAULT 'confirmed',        -- confirmed | returned | exchanged
    ordered_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### Table: `returns`
```sql
CREATE TABLE returns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID REFERENCES orders(id),
    reason VARCHAR(50),                            -- size_issue | color | expectation | defect | other
    resolution VARCHAR(20),                        -- exchange | refund | saved
    conversation_log JSONB,                        -- full returns agent conversation
    resolved_at TIMESTAMPTZ
);
```

#### Table: `conversations`
```sql
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reseller_id UUID REFERENCES resellers(id) ON DELETE CASCADE,
    session_id VARCHAR(100),
    role VARCHAR(20),                              -- user | assistant | system
    content TEXT,
    agent_used VARCHAR(50),                        -- catalog | customer | growth | returns | orchestrator
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### Table: `agent_events`
```sql
CREATE TABLE agent_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reseller_id UUID REFERENCES resellers(id),
    event_type VARCHAR(50),                        -- intent_detected | agent_routed | tool_called | reply_sent
    agent_name VARCHAR(50),
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 5.2 ChromaDB Collection Schema

**Collection name:** `meesho_catalog`

Each document represents one product SKU:

```python
{
    "id": "SKU_001",
    "document": "Red Banarasi Saree, silk material, free size, festive wear, zari border, 6.3 meters",
    "metadata": {
        "product_id": "SKU_001",
        "name": "Red Banarasi Silk Saree",
        "category": "sarees",
        "sub_category": "silk_sarees",
        "material": "silk",
        "color": "red",
        "size": "free_size",
        "occasion": "festive",
        "meesho_cost_inr": 420,
        "suggested_selling_price_inr": 599,
        "weight_grams": 650,
        "cod_available": True,
        "return_window_days": 7,
        "tags": ["banarasi", "silk", "red", "festive", "saree"]
    }
}
```

---

## 6. CORE MODULES — DETAILED SPECS

---

### 6.1 WhatsApp Gateway (Twilio)

**File:** `app/gateway/twilio_handler.py`

#### Webhook Handler

```
POST /webhook
```

Receives ALL incoming WhatsApp messages. Logic:

```
1. Parse Twilio webhook payload
2. Extract:
   - From number (reseller's WhatsApp)
   - Message body (if text)
   - Media URL (if voice note / image)
   - Media content type
3. Determine message type:
   - audio/ogg or audio/mpeg → voice note → download → send to ASR
   - image/jpeg or image/png → product image → send to Catalog Agent
   - text/plain → text message → send to Orchestrator directly
4. Load/create reseller record from Supabase using From number
5. Pass to Orchestrator
6. Get reply from Orchestrator
7. Send reply via Twilio:
   - If reply has audio → send as voice note
   - If reply has image → send as media message
   - Always send text caption alongside
```

#### Key Functions

```python
def send_whatsapp_message(to: str, body: str, media_url: str = None) -> None:
    """Send text or media message via Twilio WhatsApp"""

def download_twilio_media(media_url: str, auth: tuple) -> bytes:
    """Download audio/image from Twilio's media URL (requires Twilio auth)"""

def parse_webhook(form_data: dict) -> dict:
    """Parse raw Twilio webhook form data into structured dict"""
```

#### Important Notes

- Twilio sandbox requires joining: text "join <keyword>" to the sandbox number
- Audio files from WhatsApp come as `.ogg` (opus codec) — must convert to `.wav` before sending to Sarvam ASR
- Use `pydub` + `ffmpeg` for audio conversion
- Twilio expects webhook response in < 15 seconds — run agent processing async or use background tasks
- Always respond with 200 OK immediately, process in background via `BackgroundTasks`

---

### 6.2 Voice Layer — Vaani (ASR + TTS)

**Files:** `app/vaani/asr.py`, `app/vaani/tts.py`

#### ASR — Speech to Text

**Primary:** Sarvam Saarika API

```python
async def transcribe_audio(audio_bytes: bytes, language: str = "hi-IN") -> str:
    """
    Send audio to Sarvam Saarika for transcription.
    
    Request:
        POST https://api.sarvam.ai/speech-to-text
        Headers: {"api-subscription-key": SARVAM_API_KEY}
        Body: multipart/form-data
            - file: audio file (wav format, 16kHz mono)
            - language_code: "hi-IN"
            - model: "saarika:v1"
    
    Returns: transcribed text string
    
    Fallback: if Sarvam fails or rate-limits → use Whisper locally
    """
```

**Fallback:** OpenAI Whisper (runs locally, no API call)

```python
def transcribe_with_whisper(audio_path: str) -> str:
    """
    Local Whisper transcription as fallback.
    Model: "medium" for best Hindi accuracy.
    Load model once at startup, cache globally.
    """
```

**Audio preprocessing before ASR:**

```python
def preprocess_audio(audio_bytes: bytes) -> bytes:
    """
    1. Load .ogg file from bytes using pydub
    2. Convert to WAV format
    3. Set sample rate to 16000 Hz (required by Sarvam)
    4. Set channels to 1 (mono)
    5. Return WAV bytes
    """
```

#### TTS — Text to Speech

**Primary:** Sarvam Bulbul API

```python
async def synthesize_speech(text: str, language: str = "hi-IN", speaker: str = "meera") -> bytes:
    """
    Send text to Sarvam Bulbul for voice synthesis.
    
    Request:
        POST https://api.sarvam.ai/text-to-speech
        Headers: {"api-subscription-key": SARVAM_API_KEY}
        Body: {
            "inputs": [text],
            "target_language_code": "hi-IN",
            "speaker": "meera",        # warm female voice
            "model": "bulbul:v1",
            "pitch": 0,
            "pace": 1.0,
            "loudness": 1.5,
            "enable_preprocessing": true
        }
    
    Returns: audio bytes (WAV)
    """
```

**Fallback:** gTTS (Google Text-to-Speech, free, no API key)

```python
def synthesize_with_gtts(text: str, lang: str = "hi") -> bytes:
    """gTTS fallback — lower quality but always works"""
```

**Upload audio for Twilio:**

```python
async def upload_audio_for_twilio(audio_bytes: bytes) -> str:
    """
    Twilio requires a publicly accessible URL to send audio.
    Options:
    1. Upload to Supabase Storage → get public URL (preferred)
    2. Upload to tmpfiles.org (free, no auth)
    3. Upload to file.io (free, self-destructs after download)
    
    Returns: public URL string
    """
```

---

### 6.3 Orchestrator Agent

**Files:** `app/orchestrator/graph.py`, `app/orchestrator/intent.py`, `app/orchestrator/router.py`, `app/orchestrator/memory.py`

#### LangGraph State Definition

```python
from typing import TypedDict, Optional, List
from langgraph.graph import StateGraph, END

class SakhiState(TypedDict):
    # Input
    reseller_id: str
    reseller_number: str
    raw_input: str                    # transcribed text or raw text message
    input_type: str                   # "voice" | "text" | "image"
    image_url: Optional[str]

    # Reseller context
    reseller_name: str
    reseller_language: str
    reseller_location: str
    reseller_profile: dict            # full profile from Supabase

    # Orchestration
    detected_intent: str              # "catalog" | "customer" | "growth" | "returns" | "general"
    intent_confidence: float
    routed_to_agent: str

    # Agent output
    agent_response_text: str          # Hindi text response
    agent_response_data: dict         # structured data from agent (listing, analytics etc)
    
    # Output
    reply_text: str                   # final reply in reseller's language
    reply_audio_url: Optional[str]    # Sarvam Bulbul audio URL
    reply_image_url: Optional[str]    # generated creative image URL
    
    # History
    conversation_history: List[dict]  # last 10 turns
    error: Optional[str]
```

#### LangGraph Graph Definition

```python
def build_sakhi_graph() -> StateGraph:
    graph = StateGraph(SakhiState)
    
    # Nodes
    graph.add_node("load_memory", load_reseller_memory)
    graph.add_node("detect_intent", detect_intent)
    graph.add_node("route", route_to_agent)
    graph.add_node("catalog_agent", run_catalog_agent)
    graph.add_node("customer_agent", run_customer_agent)
    graph.add_node("growth_agent", run_growth_agent)
    graph.add_node("returns_agent", run_returns_agent)
    graph.add_node("general_handler", run_general_handler)
    graph.add_node("assemble_reply", assemble_final_reply)
    graph.add_node("save_conversation", save_to_memory)
    
    # Edges
    graph.set_entry_point("load_memory")
    graph.add_edge("load_memory", "detect_intent")
    graph.add_edge("detect_intent", "route")
    graph.add_conditional_edges("route", route_condition, {
        "catalog": "catalog_agent",
        "customer": "customer_agent",
        "growth": "growth_agent",
        "returns": "returns_agent",
        "general": "general_handler"
    })
    graph.add_edge("catalog_agent", "assemble_reply")
    graph.add_edge("customer_agent", "assemble_reply")
    graph.add_edge("growth_agent", "assemble_reply")
    graph.add_edge("returns_agent", "assemble_reply")
    graph.add_edge("general_handler", "assemble_reply")
    graph.add_edge("assemble_reply", "save_conversation")
    graph.add_edge("save_conversation", END)
    
    return graph.compile()
```

#### Intent Detection Prompt

```python
INTENT_DETECTION_PROMPT = """
You are Sakhi's intent detection system. A Meesho reseller has sent you a message in Hindi.
Classify the intent into EXACTLY one of these categories:

- "catalog": Reseller wants to add/list a product, set a price, create a WhatsApp post, 
             or mentions a product link/name they want to sell.
             Examples: "is saree ko list kar", "ye product add kar 599 mein", "post bana do"

- "customer": A buyer/customer has asked a question about a product the reseller sells.
             Could be size, material, colour, delivery, COD, return policy.
             Examples: "size kya hai?", "red mein aata hai?", "COD hai?", "kitne din mein aayega?"

- "growth": Reseller wants sales advice, analytics, trending products, what to stock.
            Examples: "is hafte kya sell karna chahiye", "kya trend chal raha hai", "mujhe advice do"
            Also triggered automatically every Sunday for scheduled growth notes.

- "returns": A buyer wants to return or exchange a product.
             Examples: "customer wapas karna chahta hai", "exchange chahiye", "return aaya hai"

- "general": Greetings, questions about Sakhi, or anything not covered above.
             Examples: "hello", "sakhi kya kar sakti ho", "shukriya"

Message from reseller: {message}

Respond with ONLY a JSON object:
{{"intent": "<category>", "confidence": <0.0-1.0>, "reason": "<one line reason>"}}
"""
```

#### Memory Functions

```python
async def load_reseller_memory(state: SakhiState) -> SakhiState:
    """
    1. Query Supabase resellers table by whatsapp_number
    2. If not found → create new reseller record (onboarding)
    3. Load reseller_profiles record
    4. Load last 10 conversations
    5. Inject into state
    """

async def save_to_memory(state: SakhiState) -> SakhiState:
    """
    1. Save user message to conversations table
    2. Save agent reply to conversations table
    3. Log agent_event to agent_events table
    4. Update reseller_profiles.updated_at
    """
```

---

### 6.4 Catalog Agent

**File:** `app/agents/catalog_agent.py`

#### Trigger Conditions
- Reseller sends a product name + price: *"ye kurti 399 mein list kar"*
- Reseller sends a Meesho-style product link
- Reseller sends a product image with a price mention

#### Input
```python
{
    "reseller_id": str,
    "reseller_name": str,
    "reseller_location": str,           # used for dialect tuning
    "raw_input": str,                   # transcribed message
    "image_url": Optional[str],         # if reseller sent a product image
    "selling_price": Optional[int],     # extracted from message
}
```

#### Processing Steps

```
Step 1: Product Extraction
    → If image provided: use Gemini Vision to extract product details from image
    → If text only: use Gemini to extract product name, category, color, material from text
    → Search mock catalog (ChromaDB) for closest matching SKU
    → Get cost_price_inr from matched SKU

Step 2: Price Validation
    → If reseller mentioned a price → use it
    → If not → suggest (cost_price * 1.4) as default margin
    → Calculate margin = selling_price - cost_price

Step 3: Caption Generation
    → Call Gemini with caption generation prompt (see below)
    → Generate a 3-4 line WhatsApp caption in Hindi
    → Include: product highlights, price, COD availability, reseller contact CTA

Step 4: Creative Generation (if USE_IMAGE_GEN=true)
    → Call Gemini Imagen with product image + overlay text prompt
    → Generate a WhatsApp-ready product creative (1:1 ratio, 1080x1080)
    → Upload to Supabase Storage → get public URL

Step 5: Save Listing
    → Insert into listings table in Supabase
    → Return listing_id

Step 6: Compose Reply
    → "Didi, maine [product_name] ₹[selling_price] mein list kar di hai.
       Margin: ₹[margin]. Ye post aapke WhatsApp groups mein share kar sakti hain:"
    → Attach caption text + creative image
```

#### Caption Generation Prompt

```python
CAPTION_GENERATION_PROMPT = """
You are Sakhi, a friendly Hindi-speaking business assistant for Meesho resellers.
Create a WhatsApp product caption in Hindi for a reseller named {reseller_name} from {location}.

Product Details:
- Name: {product_name}
- Category: {category}
- Color: {color}
- Material: {material}
- Price: ₹{price}
- COD Available: {cod}
- Key features: {features}

Instructions:
1. Write in conversational, warm Hindi (not formal)
2. Use 3-4 lines maximum
3. Include 2-3 relevant emojis naturally
4. End with a call-to-action ("order karne ke liye message karein 💌")
5. Mention FREE delivery or COD if available
6. Match the excitement level to the product (festive item → more enthusiastic)
7. Use common WhatsApp seller language style

Example style:
"✨ Navratri special georgette saree aa gayi! 
💃 Beautiful red colour, soft fabric, perfect for pooja and celebration
💰 Sirf ₹599 mein – COD available hai!
Order ke liye message karein 💌"

Now write the caption for the above product:
"""
```

#### Gemini Vision Prompt (for product images)

```python
IMAGE_EXTRACTION_PROMPT = """
Look at this product image and extract the following details in JSON format:
{
    "product_name": "descriptive name",
    "category": "sarees|kurtis|dresses|tops|leggings|accessories|other",
    "color": "primary color(s)",
    "material": "fabric/material if visible",
    "occasion": "casual|festive|formal|party|daily",
    "key_features": ["feature1", "feature2"],
    "estimated_type": "womens_clothing|mens_clothing|accessories|home_decor|other"
}
Only respond with the JSON object, nothing else.
"""
```

---

### 6.5 Customer Agent

**File:** `app/agents/customer_agent.py`

#### Trigger Conditions
- A buyer sends a query about a product the reseller sells
- Questions about size, material, color, COD, delivery time, return policy

#### The RAG Pipeline

```
Step 1: Query Understanding
    → Use Gemini to extract the query intent and key search terms
    → Identify which product is being asked about (from conversation context)

Step 2: RAG Retrieval
    → Embed the query using sentence-transformers (all-MiniLM-L6-v2)
    → Query ChromaDB collection "meesho_catalog" with top-k=3
    → Get matching product documents with metadata

Step 3: Context Assembly
    → Load reseller's active listings from Supabase
    → Cross-reference retrieved products with reseller's actual listings
    → Prefer reseller's own listed products for answers

Step 4: Answer Generation
    → Use Gemini with retrieved context to generate accurate Hindi answer
    → NEVER hallucinate — if answer not in context, say "didi se poochh lo"
    → Keep answer conversational and buyer-friendly

Step 5: Escalation Check
    → Detect sentiment: angry/frustrated buyer → flag for reseller to step in
    → If query is beyond RAG scope → generate handoff message
```

#### RAG Answer Prompt

```python
RAG_ANSWER_PROMPT = """
You are Sakhi, a customer service assistant for a Meesho reseller named {reseller_name}.
A buyer has asked a question about a product. Answer it using ONLY the provided product information.

Buyer's question: {buyer_query}

Product information from catalog:
{retrieved_context}

Instructions:
1. Answer in conversational Hindi (match the buyer's language style)
2. Use ONLY the facts from the product information — never guess or make up details
3. If the answer is not in the product information, say: "Ye detail ke liye didi se seedha poochh sakte hain 😊"
4. Keep the answer to 2-3 sentences maximum
5. End with a gentle nudge toward purchase if appropriate
6. Use 1-2 emojis naturally

Answer:
"""
```

#### Escalation Detection Prompt

```python
ESCALATION_PROMPT = """
Read this buyer message and determine if it needs human intervention (the reseller to step in).
Escalate if: angry tone, complaint, payment issue, wrong product received, defective item, 
urgent problem, or any situation requiring human judgment.

Message: {message}

Respond with JSON: {{"escalate": true/false, "reason": "brief reason"}}
"""
```

---

### 6.6 Growth Agent

**File:** `app/agents/growth_agent.py`

#### Two Trigger Modes

1. **On-demand:** Reseller asks for advice/analytics
2. **Scheduled:** Every Sunday at 8:00 PM (configurable) → auto-send growth note

#### Sales Analytics Pipeline

```python
async def generate_sales_analytics(reseller_id: str) -> dict:
    """
    Query Supabase for:
    1. orders this week vs last week → calculate % change
    2. top 3 selling products by quantity
    3. total earnings this week
    4. return rate this week
    5. best performing day of the week
    
    Returns structured analytics dict
    """

async def get_trending_recommendations(
    reseller_location: str,
    reseller_categories: list,
    analytics: dict
) -> list:
    """
    1. Check festival_calendar.json for upcoming festivals (next 14 days)
    2. Map festival → trending product categories
       e.g., Karwa Chauth → red/maroon sarees, mehendi accessories
       e.g., Diwali → ethnic wear, home decor, diyas
       e.g., Eid → kurta sets, sherwani, ittars
    3. Cross-reference with reseller's current catalog
    4. Suggest 3-5 specific products to stock/promote
    5. Return recommendations list
    """
```

#### Growth Note Generation Prompt

```python
GROWTH_NOTE_PROMPT = """
You are Sakhi, a warm and encouraging business coach for a Meesho reseller.
Write a friendly, motivating weekly business update in Hindi for {reseller_name} from {location}.

This week's data:
- Orders this week: {orders_this_week}
- Orders last week: {orders_last_week}
- Change: {change_percent}% ({up/down})
- Top selling product: {top_product}
- Total earnings: ₹{earnings}
- Return rate: {return_rate}%
- Upcoming festival (next 14 days): {festival_name} on {festival_date}
- Recommended products to stock: {recommendations}

Instructions:
1. Start with a warm greeting using their name
2. Give a BRIEF summary of this week's performance (1-2 sentences)
3. If performance improved → celebrate it warmly
4. If performance dropped → be encouraging, not discouraging
5. Mention the upcoming festival and specific products to push (actionable)
6. End with one motivating sentence
7. Keep total length under 150 words
8. Use warm, didi-like Hindi — not corporate or formal
9. Include 2-3 emojis

Example tone: "Sunita didi, is hafte aapne bahut achha kiya! 14 sarees bik gayi — 
pichle hafte se 20% zyada. Karwa Chauth aa raha hai 10 din mein, 
red aur maroon sarees ka stock badhao didi — yahi trend hai abhi. 
Aap bahut achha kar rahi hain! 💪✨"

Now write the growth note:
"""
```

#### Scheduler Setup

```python
import schedule
import threading

def start_growth_scheduler():
    """
    Run in a background thread.
    Every Sunday at 20:00 IST → fetch all resellers → send growth notes.
    """
    schedule.every().sunday.at("20:00").do(send_weekly_growth_notes_all)
    
    def run_scheduler():
        while True:
            schedule.run_pending()
            time.sleep(60)
    
    thread = threading.Thread(target=run_scheduler, daemon=True)
    thread.start()
```

---

### 6.7 Returns Agent

**File:** `app/agents/returns_agent.py`

#### Trigger Conditions
- Reseller informs Sakhi about an incoming return
- Buyer messages about wanting to return/exchange

#### Conversation Flow (State Machine)

```
State 0: INITIATED
    → Sakhi greets the buyer warmly
    → "Namaste ji! Sunita didi ki taraf se main Sakhi bol rahi hoon. 
       Aapne return request ki hai — kya hua thoda batayein?"

State 1: REASON_COLLECTION
    → Listen for buyer's reason
    → Classify reason:
        - SIZE_ISSUE: "size chhota/bada hai", "fit nahi hua"
        - COLOR_MISMATCH: "colour alag tha", "photo se match nahi kiya"
        - QUALITY_ISSUE: "kapda achha nahi tha", "defective"
        - EXPECTATION_GAP: "waisa nahi tha jaisa socha tha"
        - OTHER: anything else

State 2: RESOLUTION_OFFER
    → SIZE_ISSUE → offer exchange in correct size
    → COLOR_MISMATCH → offer exchange in preferred color if available
    → QUALITY_ISSUE → apologize, offer full exchange or refund (escalate to reseller)
    → EXPECTATION_GAP → show more product details, offer exchange
    
    → "Koi baat nahi ji! Hum aapko same product ka [size X / color Y] 
       exchange de sakte hain bilkul free mein. Kya yeh theek rahega?"

State 3: RESOLUTION_CONFIRMATION
    → If buyer accepts exchange → mark as EXCHANGED in DB
       → Teach Catalog Agent: add size/color note to this listing
    → If buyer declines → escalate to reseller with full conversation log
    → Thank buyer warmly regardless of outcome

State 4: COMPLETED
    → Log conversation to returns table in Supabase
    → Notify reseller of outcome via WhatsApp
    → Update order status in DB
```

#### Returns Conversation Prompt

```python
RETURNS_SYSTEM_PROMPT = """
You are Sakhi, a warm and empathetic customer care representative for a Meesho reseller.
Your job is to handle product return requests kindly and try to convert them into exchanges.

Reseller: {reseller_name}
Product in question: {product_name}
Available exchanges: {available_exchanges}

Current conversation stage: {stage}
Conversation so far: {history}

Buyer's latest message: {buyer_message}

Rules:
1. Always be warm, empathetic, and patient — never defensive
2. Speak in simple Hindi matching the buyer's language style
3. Try to offer an exchange before accepting a return
4. If the buyer is upset → acknowledge their feelings first before offering solutions
5. Never promise what you can't deliver — stick to available_exchanges list
6. If the situation is beyond your scope → say you'll have didi call them personally
7. Keep responses concise — 2-3 sentences maximum per turn
8. Use 1 emoji per message for warmth

Respond naturally as Sakhi:
"""
```

---

### 6.8 Mock Meesho Catalog

**File:** `app/data/mock_catalog.json`

Generate ~500 SKUs across these categories. Each SKU must have:

```json
{
  "product_id": "SAR_001",
  "name": "Red Banarasi Silk Saree",
  "category": "sarees",
  "sub_category": "silk_sarees",
  "description": "Beautiful handwoven Banarasi silk saree with zari border, perfect for weddings and festivals. Comes with matching blouse piece.",
  "color": ["red", "maroon"],
  "material": "silk",
  "size": "free_size",
  "weight_grams": 650,
  "occasion": ["festive", "wedding", "pooja"],
  "meesho_cost_inr": 420,
  "suggested_selling_price_inr": 599,
  "suggested_margin_inr": 179,
  "cod_available": true,
  "return_window_days": 7,
  "delivery_days_estimate": 5,
  "tags": ["banarasi", "silk", "red", "festive", "wedding", "saree", "zari"],
  "image_description": "Red silk saree with gold zari border on white background"
}
```

**Category distribution (500 SKUs):**
- Sarees: 120 (silk, cotton, georgette, chiffon, synthetic)
- Kurtis: 100 (straight, anarkali, A-line, short)
- Salwar suits: 80
- Leggings/churidaar: 60
- Tops/tunics: 50
- Dresses: 40
- Accessories (dupattas, stoles): 30
- Kids wear: 20

**Script to generate catalog:** Use Gemini to generate realistic product data, then save as JSON. See `scripts/seed_catalog.py`.

---

### 6.9 Memory Layer (Supabase + ChromaDB)

#### Supabase Client

```python
# app/db/supabase_client.py

from supabase import create_client

class SupabaseDB:
    def __init__(self):
        self.client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    
    async def get_or_create_reseller(self, whatsapp_number: str) -> dict:
        """Upsert reseller by WhatsApp number"""
    
    async def get_reseller_profile(self, reseller_id: str) -> dict:
        """Get full reseller profile with listings + recent orders"""
    
    async def save_listing(self, listing_data: dict) -> str:
        """Insert new listing, return listing_id"""
    
    async def get_active_listings(self, reseller_id: str) -> list:
        """Get all active listings for a reseller"""
    
    async def save_order(self, order_data: dict) -> str:
        """Insert new order"""
    
    async def get_weekly_analytics(self, reseller_id: str) -> dict:
        """Aggregate orders for current week vs last week"""
    
    async def save_conversation_turn(self, turn_data: dict) -> None:
        """Append a conversation turn"""
    
    async def get_conversation_history(self, reseller_id: str, limit: int = 10) -> list:
        """Get last N conversation turns"""
    
    async def save_return(self, return_data: dict) -> str:
        """Log a return/exchange event"""
    
    async def log_agent_event(self, event_data: dict) -> None:
        """Log agent routing/tool events for dashboard"""
```

#### ChromaDB Client

```python
# app/db/chroma_client.py

import chromadb
from sentence_transformers import SentenceTransformer

class CatalogRAG:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        self.collection = self.client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
    
    def ingest_catalog(self, products: list) -> None:
        """Bulk ingest all 500 SKUs into ChromaDB"""
    
    def search(self, query: str, n_results: int = 3, 
               filters: dict = None) -> list:
        """
        Semantic search over catalog.
        filters: {"category": "sarees"} — filter by metadata
        Returns list of (product_metadata, similarity_score)
        """
    
    def search_by_reseller_listings(
        self, query: str, listing_ids: list, n_results: int = 3
    ) -> list:
        """Search only within reseller's own listed products"""
```

---

## 7. API ENDPOINTS

```
FastAPI app — all routes defined in app/main.py
```

| Method | Path | Description |
|---|---|---|
| `POST` | `/webhook` | Twilio WhatsApp webhook receiver |
| `POST` | `/webhook/status` | Twilio message status callback |
| `GET` | `/health` | Health check — returns status of all services |
| `GET` | `/reseller/{number}` | Get reseller profile by WhatsApp number |
| `GET` | `/reseller/{id}/listings` | Get all active listings for reseller |
| `GET` | `/reseller/{id}/analytics` | Get weekly analytics |
| `POST` | `/reseller/{id}/growth-note` | Manually trigger a growth note |
| `GET` | `/agent/events` | Get recent agent events (for dashboard) |
| `POST` | `/demo/simulate` | Simulate a message without WhatsApp (for testing) |
| `GET` | `/` | Root — returns API info |

### Health Check Response

```json
{
  "status": "healthy",
  "services": {
    "database": "connected",
    "chromadb": "connected",
    "sarvam_asr": "available",
    "sarvam_tts": "available",
    "gemini": "available",
    "twilio": "connected"
  },
  "version": "1.0.0",
  "timestamp": "2026-07-14T10:30:00Z"
}
```

### Demo Simulate Endpoint (critical for judges)

```json
POST /demo/simulate
{
  "reseller_number": "whatsapp:+919876543210",
  "message_text": "Sakhi, is saree ko meri list mein daal, 599 rakh",
  "message_type": "text"
}

Response:
{
  "intent": "catalog",
  "agent_used": "catalog_agent",
  "reply_text": "Ho gaya didi! ...",
  "reply_audio_url": "https://...",
  "reply_image_url": "https://...",
  "listing_created": {"id": "...", "margin": 179},
  "processing_time_ms": 3240
}
```

---

## 8. STREAMLIT DASHBOARD (BACKUP DEMO)

**File:** `dashboard/app.py`

### Dashboard Layout

```
┌─────────────────────────────────────────────────────────┐
│  🌸 SAKHI — Live Agent Dashboard                        │
│  The AI Business Didi for Meesho Resellers              │
├──────────────────┬──────────────────┬───────────────────┤
│  AGENT STATUS    │  CHAT SIMULATOR  │  ANALYTICS        │
│                  │                  │                   │
│  🟢 Orchestrator │  [WhatsApp UI]   │  Orders this week │
│  🟢 Catalog Didi │                  │  ████████ 14      │
│  🟢 Customer Didi│  Sunita: [input] │                   │
│  🟡 Growth Didi  │                  │  vs last week     │
│  🟢 Returns Didi │  Sakhi: [reply]  │  ████████ 11      │
│                  │                  │                   │
│  Last event:     │  [Send Message]  │  Top product:     │
│  Catalog Agent   │  [Record Voice]  │  Red Saree        │
│  called at 14:23 │                  │                   │
├──────────────────┴──────────────────┴───────────────────┤
│  AGENT EVENT LOG (real-time)                            │
│  14:23:01 → Intent: catalog (conf: 0.94)               │
│  14:23:02 → Routed to: Catalog Agent                   │
│  14:23:03 → Tool: search_catalog → "Red Banarasi Saree" │
│  14:23:04 → Tool: generate_caption → success           │
│  14:23:05 → Tool: generate_image → success             │
│  14:23:06 → Reply sent in 3.2 seconds                  │
└─────────────────────────────────────────────────────────┘
```

### Key Dashboard Features

1. **Chat Simulator:** Type or paste messages in the dashboard → calls `/demo/simulate` → shows Sakhi's response. Judges can test without a WhatsApp number.
2. **Agent Status Panel:** Real-time green/yellow/red indicators per agent.
3. **Event Log:** Live stream of agent events from `agent_events` table (auto-refreshes every 2 seconds).
4. **Analytics Charts:** Plotly bar charts for weekly orders, top products, return rate.
5. **Voice Playback:** If reply has audio, embed an audio player in the dashboard.

---

## 9. END-TO-END FLOW — STEP BY STEP

### Full Request Lifecycle (Catalog Example)

```
T+0ms    Sunita records a 8-second Hindi voice note on WhatsApp:
         "Sakhi, ye saree ko meri list mein daal, price 599 rakh"

T+50ms   Twilio receives the voice note, POSTs webhook to /webhook
         Payload includes: From, NumMedia, MediaUrl0, MediaContentType0

T+60ms   FastAPI receives webhook, immediately returns 200 OK
         Spawns BackgroundTask: process_message(payload)

T+100ms  download_twilio_media() downloads .ogg audio file (~25KB)

T+150ms  preprocess_audio() converts .ogg → .wav, 16kHz mono

T+600ms  transcribe_audio() calls Sarvam Saarika:
         Result: "Sakhi, ye saree ko meri list mein daal, price 599 rakh"

T+650ms  load_reseller_memory() loads Sunita's profile from Supabase

T+900ms  detect_intent() calls Gemini:
         Result: {"intent": "catalog", "confidence": 0.96}

T+950ms  route_to_agent() → CatalogAgent.run()

T+1100ms search_catalog() queries ChromaDB with "saree 599"
         Returns: 3 matching SKUs, top match: "Red Georgette Saree" (cost: ₹399)

T+1200ms generate_caption() calls Gemini:
         Returns: Hindi WhatsApp caption (3 lines)

T+1800ms generate_image() calls Gemini Imagen:
         Returns: 1080x1080 product creative

T+2000ms upload_to_supabase_storage() → public image URL

T+2100ms save_listing() inserts listing into Supabase DB

T+2200ms assemble_reply() composes final Hindi response text:
         "Ho gaya didi! Maine ye saree ₹599 mein list kar di.
          Margin ₹200 ka hai. Caption aur photo ready hai, 
          abhi share kar sakti hain! 💗"

T+2500ms synthesize_speech() calls Sarvam Bulbul:
         Returns: .wav audio of the reply (8 seconds)

T+2700ms upload_audio_for_twilio() → public audio URL

T+3000ms send_whatsapp_message() calls Twilio:
         Sends: voice note + caption text + product creative image

T+3200ms save_conversation() logs everything to Supabase

T+3200ms log_agent_event() logs to agent_events for dashboard

TOTAL:   ~3.2 seconds end-to-end ✅
```

---

## 10. DEMO SCENARIOS (JUDGE-READY)

Prepare these exact scenarios as scripted demos. Each should work live.

### Demo 1: Catalog — "List this saree"
```
Input (text): "Sakhi, red banarasi saree ko meri list mein daal, 599 rakh"
Expected output:
  - Hindi text reply: "Ho gaya didi! Maine Red Banarasi Saree ₹599 mein list kar di. 
    Margin ₹179 ka hai. Ye caption aur photo share karein apne groups mein 💗"
  - WhatsApp caption (Hindi, 3-4 lines, emojis)
  - Product creative image
  - Listing saved in Supabase
```

### Demo 2: Customer — "Size question from buyer"
```
Input (text): "size kya hai is kurti ka? free size hai?"
Expected output:
  - Hindi reply: "Ji haan, ye kurti free size hai aur waist 28 se 38 tak fit aati hai. 
    Soft rayon material hai, bahut comfortable. Order karna ho toh batayein! 😊"
  - Source: ChromaDB RAG (not hallucination)
```

### Demo 3: Growth — "What should I sell?"
```
Input (text): "Sakhi, is hafte kya sell karna chahiye?"
Expected output:
  - Hindi reply with: this week's performance, Karwa Chauth recommendations 
    (if within 14 days), specific 3 products to stock
  - Voice note reply
```

### Demo 4: Returns — "Customer wants to return"
```
Input (text): "Sakhi, ek customer saree wapas karna chahti hai, size chhhota tha"
Expected output:
  - Multi-turn conversation
  - Sakhi offers exchange in correct size
  - Resolution saved in DB
  - Reseller notified of outcome
```

### Demo 5: Voice Round-Trip
```
Input: actual Hindi voice note (pre-recorded .ogg file)
Expected output: Hindi voice note reply
This is the wow moment — play both audio files back-to-back for judges
```

---

## 11. OPEN-SOURCE ATTRIBUTION

*Declare all tools exactly as follows in the GitHub README:*

| Library | Version | License | Role in Build | Source |
|---|---|---|---|---|
| FastAPI | 0.111.0 | MIT | Backend web framework, API routes, webhook handler | https://github.com/tiangolo/fastapi |
| LangGraph | 0.1.19 | MIT | Multi-agent state machine orchestration | https://github.com/langchain-ai/langgraph |
| LangChain | 0.2.6 | MIT | LLM integration utilities | https://github.com/langchain-ai/langchain |
| langchain-google-genai | 1.0.6 | MIT | Gemini integration for LangChain | https://github.com/langchain-ai/langchain-google-genai |
| google-generativeai | 0.7.2 | Apache 2.0 | Gemini 2.5 Flash + Imagen API | https://github.com/google/generative-ai-python |
| chromadb | 0.5.3 | Apache 2.0 | Vector database for RAG (catalog lookup) | https://github.com/chroma-core/chroma |
| sentence-transformers | 3.0.1 | Apache 2.0 | Text embeddings for ChromaDB | https://github.com/UKPLab/sentence-transformers |
| supabase | 2.5.0 | MIT | PostgreSQL database client (reseller memory) | https://github.com/supabase-community/supabase-py |
| twilio | 9.2.3 | MIT | WhatsApp gateway (send/receive messages) | https://github.com/twilio/twilio-python |
| pydub | 0.25.1 | MIT | Audio format conversion (.ogg → .wav) | https://github.com/jiaaro/pydub |
| openai-whisper | 20231117 | MIT | Local ASR fallback for Hindi | https://github.com/openai/whisper |
| gTTS | 2.5.1 | MIT | TTS fallback if Sarvam rate-limits | https://github.com/pndurette/gTTS |
| streamlit | 1.36.0 | Apache 2.0 | Backup demo dashboard | https://github.com/streamlit/streamlit |
| plotly | 5.22.0 | MIT | Analytics charts in dashboard | https://github.com/plotly/plotly.py |
| pandas | 2.2.2 | BSD-3 | Data manipulation for analytics | https://github.com/pandas-dev/pandas |
| schedule | 1.2.1 | MIT | Growth Agent weekly scheduler | https://github.com/dbader/schedule |
| httpx | 0.27.0 | BSD-3 | Async HTTP client for Sarvam API calls | https://github.com/encode/httpx |
| pydantic | 2.7.3 | MIT | Data validation and settings management | https://github.com/pydantic/pydantic |
| pytest | 8.2.2 | MIT | Test framework | https://github.com/pytest-dev/pytest |
| uvicorn | 0.30.1 | BSD-3 | ASGI server for FastAPI | https://github.com/encode/uvicorn |
| python-dotenv | 1.0.1 | BSD-3 | Environment variable loading | https://github.com/theskumar/python-dotenv |
| pillow | 10.3.0 | HPND | Image processing for creatives | https://github.com/python-pillow/Pillow |

**AI APIs used (not open-source, free tier):**
- **Sarvam AI Saarika** — Indic ASR — https://sarvam.ai (free tier)
- **Sarvam AI Bulbul** — Indic TTS — https://sarvam.ai (free tier)
- **Google Gemini 2.5 Flash** — LLM reasoning — https://ai.google.dev (free tier)
- **Google Gemini Imagen** — Image generation — https://ai.google.dev (free tier)
- **Twilio WhatsApp Sandbox** — Messaging gateway — https://twilio.com (free sandbox)

---

## 12. DEPLOYMENT GUIDE

### Option A: Render (Recommended)

```yaml
# render.yaml
services:
  - type: web
    name: sakhi-api
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.0
      # Add all .env variables here as Render environment variables
```

Steps:
1. Push code to GitHub
2. Connect GitHub repo to Render
3. Add all environment variables from .env to Render dashboard
4. Deploy → get a `https://sakhi-api.onrender.com` URL
5. Update Twilio webhook URL to `https://sakhi-api.onrender.com/webhook`
6. Update `WEBHOOK_BASE_URL` environment variable on Render

### Option B: Railway

```bash
railway init
railway add
railway up
# Set env vars: railway variables set KEY=VALUE
```

### Streamlit Dashboard Deployment (Streamlit Cloud)

1. Push `dashboard/` folder to GitHub
2. Go to https://share.streamlit.io
3. Connect repo → set `dashboard/app.py` as main file
4. Add all env variables in Streamlit Cloud secrets
5. Deploy → get a `https://sakhi-dashboard.streamlit.app` URL

### Twilio Webhook Configuration

```
Twilio Console → Messaging → WhatsApp Sandbox
→ "When a message comes in": https://your-render-url.onrender.com/webhook
→ Method: POST
→ "Status Callback URL": https://your-render-url.onrender.com/webhook/status
```

---

## 13. README TEMPLATE

```markdown
# Sakhi 🌸 — The AI Business Didi for Meesho Resellers

> An agentic AI co-pilot that runs a Meesho reseller's entire business 
> through WhatsApp, in her own language and her own voice.

**ScriptedBy{Her} 2.0 — Round 3 Prototype | Team Orchestrator**

## Demo Links
- 🌐 **Live API:** https://sakhi-api.onrender.com
- 🎯 **Try the demo:** https://sakhi-dashboard.streamlit.app
- 🎥 **Demo video:** [Watch here](YOUR_VIDEO_LINK)
- 📊 **Health check:** https://sakhi-api.onrender.com/health

## What is Sakhi?

[Brief description — 2-3 lines]

## Architecture

[Paste ASCII architecture diagram from Section 2.1]

## Setup & Run Locally

### Prerequisites
- Python 3.11+
- ffmpeg installed (`brew install ffmpeg` / `apt install ffmpeg`)
- API keys for: Twilio, Sarvam AI, Google Gemini, Supabase

### Installation
\`\`\`bash
git clone https://github.com/yourusername/sakhi.git
cd sakhi
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in your API keys in .env
python scripts/seed_catalog.py
python scripts/seed_reseller.py
uvicorn app.main:app --reload
\`\`\`

### Running the Dashboard
\`\`\`bash
streamlit run dashboard/app.py
\`\`\`

### Running Tests
\`\`\`bash
pytest tests/ -v
\`\`\`

## API Documentation
[FastAPI auto-docs available at: https://sakhi-api.onrender.com/docs]

## Open-Source Attribution
[Full table from Section 11]
```

---

## 14. DAY-BY-DAY BUILD PLAN

Given **13–19 July 2026** (7 days):

### Day 1 — 13 July (Today): Foundation & Plumbing
- [ ] Initialize repo, set up folder structure as per Section 3
- [ ] Create `.env.example`, `requirements.txt`
- [ ] Set up Supabase: create all tables from Section 5.1
- [ ] Test Supabase connection (`supabase_client.py`)
- [ ] Set up Twilio sandbox, test basic send/receive
- [ ] `twilio_handler.py`: basic webhook receiver (text messages only)
- [ ] `config.py`: environment loader
- [ ] Deploy skeleton to Render, verify webhook URL works
- **End of day checkpoint:** Twilio sends "hello" → app receives it → logs to console ✅

### Day 2 — 14 July: Voice Layer (Vaani)
- [ ] `vaani/asr.py`: Sarvam Saarika integration
- [ ] Audio preprocessing: .ogg → .wav conversion with pydub
- [ ] Test ASR with a sample Hindi voice note
- [ ] `vaani/tts.py`: Sarvam Bulbul integration
- [ ] Audio upload to Supabase Storage for public URL
- [ ] Whisper fallback implementation
- [ ] gTTS fallback implementation
- [ ] End-to-end voice echo test: receive voice → transcribe → re-synthesize → send back
- **End of day checkpoint:** Sunita sends voice note → Sakhi echoes back in voice ✅

### Day 3 — 15 July: Orchestrator + Catalog Agent
- [ ] `orchestrator/intent.py`: intent detection with Gemini
- [ ] `orchestrator/memory.py`: load/save reseller memory
- [ ] `orchestrator/graph.py`: LangGraph state machine (all nodes, routing)
- [ ] `data/mock_catalog.json`: generate 500 SKUs (use Gemini to generate)
- [ ] `scripts/seed_catalog.py`: ingest catalog into ChromaDB
- [ ] `db/chroma_client.py`: ChromaDB setup + search
- [ ] `agents/catalog_agent.py`: full Catalog Agent
- [ ] `tools/catalog_search.py`: ChromaDB search utility
- [ ] `tools/image_gen.py`: Gemini Imagen creative generation
- **End of day checkpoint:** "is saree ko list kar" → Hindi reply + listing saved + creative image ✅

### Day 4 — 16 July: Customer Agent + Returns Agent
- [ ] `agents/customer_agent.py`: RAG pipeline
- [ ] `tools/rag_engine.py`: ChromaDB RAG search
- [ ] Test Customer Agent: buyer queries answered from catalog
- [ ] `agents/returns_agent.py`: multi-turn returns flow
- [ ] `db/supabase_client.py`: save_return, update_order_status
- [ ] Returns conversation state machine
- **End of day checkpoint:** Buyer query answered from RAG ✅ + Returns flow saves to DB ✅

### Day 5 — 17 July: Growth Agent + Scheduler + Analytics
- [ ] `tools/sales_analytics.py`: Supabase query for weekly stats
- [ ] `tools/festival_calendar.py`: festival calendar lookup
- [ ] `agents/growth_agent.py`: growth note generation
- [ ] Weekly scheduler: background thread
- [ ] Analytics endpoint: `/reseller/{id}/analytics`
- [ ] Test growth note: generates Hindi voice note with real data
- **End of day checkpoint:** Growth note sent in Hindi voice with festival recommendation ✅

### Day 6 — 18 July: Dashboard + Integration Polish
- [ ] `dashboard/app.py`: Streamlit dashboard
- [ ] Chat simulator component
- [ ] Agent status + event log panel
- [ ] Analytics charts
- [ ] `/demo/simulate` endpoint: lets judges test without WhatsApp
- [ ] Full end-to-end integration test (all 4 demo scenarios from Section 10)
- [ ] Fix any bugs from integration testing
- [ ] Deploy updated backend to Render
- [ ] Deploy dashboard to Streamlit Cloud
- **End of day checkpoint:** All 4 demo scenarios work live ✅ Dashboard shows agent activity ✅

### Day 7 — 19 July: Polish + Submission
- [ ] Write comprehensive README (Section 13 template)
- [ ] Run all tests (`pytest tests/ -v`)
- [ ] Verify all submission checklist items (Section 15)
- [ ] Record final demo video (if required)
- [ ] Double-check all open-source attributions (Section 11)
- [ ] Make GitHub repo public
- [ ] Verify live deployment URL is accessible
- [ ] Submit on HackerEarth before deadline
- **End of day checkpoint:** Submission complete ✅

---

## 15. TESTING CHECKLIST

### Functional Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_catalog_agent.py -v
```

**test_asr.py**
- [ ] Hindi voice note transcribed correctly
- [ ] .ogg to .wav conversion works
- [ ] Whisper fallback triggers when Sarvam unavailable
- [ ] Empty audio handled gracefully

**test_tts.py**
- [ ] Sarvam Bulbul generates audio for Hindi text
- [ ] Audio uploaded to Supabase Storage
- [ ] Public URL returned and accessible
- [ ] gTTS fallback triggers when Sarvam unavailable

**test_orchestrator.py**
- [ ] "list this saree 599" → intent: catalog
- [ ] "size kya hai?" → intent: customer
- [ ] "kya bechun?" → intent: growth
- [ ] "return aaya" → intent: returns
- [ ] "hello" → intent: general
- [ ] Reseller memory loaded correctly
- [ ] Conversation saved after each turn

**test_catalog_agent.py**
- [ ] Product extracted from text input
- [ ] Product matched from ChromaDB catalog
- [ ] Hindi caption generated (3-4 lines, emojis)
- [ ] Image generated and URL returned
- [ ] Listing saved in Supabase
- [ ] Margin calculated correctly

**test_customer_agent.py**
- [ ] Buyer query answered using RAG (not hallucination)
- [ ] Size questions answered correctly from product metadata
- [ ] Escalation triggered for angry/frustrated buyer
- [ ] Unknown product handled gracefully ("didi se poochho")

**test_growth_agent.py**
- [ ] Sales analytics queried correctly from Supabase
- [ ] Festival calendar returns correct upcoming festival
- [ ] Growth note generated in warm Hindi
- [ ] Voice note synthesized and URL returned
- [ ] Scheduler fires correctly

**test_returns_agent.py**
- [ ] Return reason classified correctly
- [ ] Exchange offer generated appropriately
- [ ] Multi-turn conversation state maintained
- [ ] Resolution saved to DB
- [ ] Reseller notified of outcome

### Submission Checklist

- [ ] GitHub repository is **public**
- [ ] README is complete with setup instructions
- [ ] All env variables documented in `.env.example`
- [ ] `requirements.txt` has all dependencies with versions
- [ ] Live API URL is accessible: health check returns 200
- [ ] Streamlit dashboard is live and accessible
- [ ] `/demo/simulate` endpoint works for judge testing
- [ ] All 4 demo scenarios produce correct output
- [ ] Voice round-trip works end-to-end
- [ ] Open-source attribution table complete in README
- [ ] All agent events logged and visible in dashboard
- [ ] Tests pass: `pytest tests/ -v`
- [ ] No hardcoded API keys in code (all via .env)
- [ ] `.gitignore` excludes .env, __pycache__, chroma_db

---

*This PRD is the single source of truth for the Sakhi prototype build.*
*Any agent or developer reading this document should be able to build the complete system from scratch.*
*Build window: 13 July → 19 July 2026 | Target: Grand Finale of ScriptedBy{Her} 2.0*
