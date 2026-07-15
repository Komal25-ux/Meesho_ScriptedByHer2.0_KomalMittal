# SAKHI — Product Requirements Document (PRD)
## Version 2.5 | ScriptedBy{Her} 2.0 — Round 3 Prototype Build (React UI Edition)
### Prepared by: Team Orchestrator | Build Window: 13–19 July 2026
**Target:** Grand Finale Submission — High Impact, Flawless UX, and Complete End-to-End AI Multi-Agent Flow.

---

## TABLE OF CONTENTS

1. [Product Overview & Hackathon Strategy](#1-product-overview--hackathon-strategy)
2. [Technical Architecture & State Flow](#2-technical-architecture--state-flow)
3. [Repository Structure (Monorepo)](#3-repository-structure-monorepo)
4. [Environment Setup & Configuration](#4-environment-setup--configuration)
5. [Database & Vector Schema](#5-database--vector-schema)
6. [Core Modules — Detailed Specs](#6-core-modules--detailed-specs)
7. [Agent Personas & System Prompts](#7-agent-personas--system-prompts)
8. [API Endpoints & WebSocket (Live Tracing)](#8-api-endpoints--websocket-live-tracing)
9. [Edge Cases & Error Handling Strategy](#9-edge-cases--error-handling-strategy)
10. [End-to-End Flow — Step by Step](#10-end-to-end-flow--step-by-step)
11. [Demo Scenarios (Judge-Ready)](#11-demo-scenarios-judge-ready)
12. [Open-Source Attribution (Mandatory Checklist)](#12-open-source-attribution-mandatory-checklist)
13. [Deployment Guide](#13-deployment-guide)
14. [README Submission Template](#14-readme-submission-template)
15. [Day-by-Day Build Plan (13–19 July)](#15-day-by-day-build-plan-1319-july)
16. [Hackathon Submission Checklist](#16-hackathon-submission-checklist)

---

## 1. PRODUCT OVERVIEW & HACKATHON STRATEGY

### 1.1 What is Sakhi?
Sakhi is an **agentic AI co-pilot** that acts as a Meesho reseller's business manager. Built as a **Progressive Web App (PWA)**, it mimics a familiar WhatsApp-like chat interface where the reseller communicates purely through **Hindi voice notes**. 

### 1.2 The Hackathon Strategy (Why React?)
To maximize our score on **Usability & UX** and **Technical Excellence**, we have deprecated the 3rd-party Twilio Sandbox in favor of a **Custom React Frontend**. 
* **For the User (Left Pane):** It provides a flawless, branded, WhatsApp-like mobile view.
* **For the Judges (Right Pane):** A **Split-Screen "Judge Dashboard"**. While the chat interface runs on the left, the right side will display a real-time visualization of the LangGraph state machine, agent routing, API latencies, and tool calls. This proves the system is not hardcoded and highlights the *Architecture & Innovation*.

### 1.3 Target User Persona
**Persona:** Sunita, 34, Kanpur. Sells sarees to 200+ WhatsApp customers. Spends 4 hours/day on manual reseller tasks. Low digital literacy but high WhatsApp fluency. Sakhi operates in her dialect (Hindi) and voice.

### 1.4 Success Criteria for Round 3 Evaluators
- [ ] **Working Prototype:** Fully functioning React frontend + FastAPI backend without mock/hardcoded responses.
- [ ] **Code Quality:** Modular agent architecture, clean separation of concerns, exhaustive inline comments.
- [ ] **Usability & UX:** Intuitive hold-to-record voice feature, responsive design (Tailwind CSS), zero-latency optimistic UI.
- [ ] **Completeness:** All 4 Specialist Agents (Catalog, Customer, Growth, Returns) work end-to-end.
- [ ] **Transparency:** Full Open-Source attributions documented strictly as per instructions.

---

## 2. TECHNICAL ARCHITECTURE & STATE FLOW

### 2.1 System Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                          REACT FRONTEND (Vite/Tailwind)                 │
│                                                                         │
│  ┌───────────────────────┐           ┌──────────────────────────────┐   │
│  │   Mobile Chat View    │           │    Judge / Analytics View    │   │
│  │ (WhatsApp-like UI)    │           │ (Real-time Agent Trace Log)  │   │
│  │  - Web Audio API      │ ◄───────► │  - Active Listings           │   │
│  │  - Hold-to-Talk       │  (WSS://) │  - Weekly Sales Charts       │   │
│  └──────────┬────────────┘           └──────────────────────────────┘   │
└─────────────┼───────────────────────────────────────────────────────────┘
              │ HTTP POST (Audio Blob / Text) + WebSocket (Live logs)
┌─────────────▼───────────────────────────────────────────────────────────┐
│                         FASTAPI BACKEND                                 │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                     VAANI LAYER (Media Engine)                    │  │
│  │  Browser WebM → FFmpeg (WAV) → Sarvam Saarika (ASR) → Text       │  │
│  │  Text → Sarvam Bulbul (TTS) → MP3 URL → Browser Playback         │  │
│  └─────────────────────────────────┬─────────────────────────────────┘  │
│                                    │                                    │
│  ┌─────────────────────────────────▼─────────────────────────────────┐  │
│  │                  ORCHESTRATOR (LangGraph FSM)                     │  │
│  │         Gemini 2.5 Flash | Supabase Memory Context                │  │
│  └───────┬───────────┬──────────────┬───────────────┬───────────┬────┘  │
│          │           │              │               │           │       │
│  ┌───────▼──┐ ┌──────▼───┐ ┌────────▼──┐ ┌──────────▼──┐ ┌──────▼───┐   │
│  │ CATALOG  │ │ CUSTOMER │ │  GROWTH   │ │   RETURNS   │ │ CHAT LOG │   │
│  │  AGENT   │ │  AGENT   │ │   AGENT   │ │    AGENT    │ │ WEBSOCKET│   │
│  └───────┬──┘ └──────┬───┘ └────────┬──┘ └──────────┬──┘ └──────────┘   │
└──────────┼───────────┼──────────────┼───────────────┼───────────────────┘
           │           │              │               │
┌──────────▼───────────▼──────────────▼───────────────▼───────────────────┐
│                           DATA INFRASTRUCTURE                           │
│  ┌───────────────────────────┐  ┌────────────────────────────────────┐  │
│  │    Mock Meesho Catalog    │  │          Supabase (PgSQL)          │  │
│  │          (JSON)           │  │ (Memory, Auth, Storage, pgvector)  │  │
│  └───────────────────────────┘  └────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Core Tech Stack Breakdown
| Layer | Primary Tool | Description & Fallback Strategy |
|---|---|---|
| **Frontend Framework** | React (Vite) | Fast UI development. Optimistic UI updates. |
| **Styling & UI** | Tailwind CSS + Lucide | Mobile-first, responsive chat interface. |
| **Backend API** | FastAPI (Python 3.11) | Async API, WebSocket streaming capabilities. |
| **Agent Orchestration**| LangGraph + Gemini | Complex state routing. Fallback to general LLM if routing fails. |
| **Voice Processing** | Sarvam AI API + FFmpeg | High-accuracy Indic ASR/TTS. Local Whisper fallback for demo resilience. |
| **Databases** | Supabase (with pgvector) | Memory (PostgreSQL) and Vector Search (using pgvector + Gemini embeddings). |

---

## 3. REPOSITORY STRUCTURE (MONOREPO)

```text
sakhi-prototype/
├── README.md                          # Comprehensive Hackathon setup guide
├── requirements.txt                   # Backend dependencies
├── .env.example                       # Shared environment variables
├── .gitignore
│
├── frontend/                          # React PWA UI
│   ├── package.json
│   ├── vite.config.js
│   ├── src/
│   │   ├── main.jsx
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── chat/                  # Mobile-like chat interface
│   │   │   │   ├── MessageBubble.jsx
│   │   │   │   └── VoiceRecorder.jsx  # Web Audio API + MediaRecorder
│   │   │   ├── dashboard/             # Judge View
│   │   │   │   ├── AgentTraceLog.jsx  # WebSocket listener for LangGraph
│   │   │   │   └── SalesCharts.jsx    # Chart.js/Recharts implementation
│   │   ├── services/
│   │   │   ├── api.js                 # Axios calls to FastAPI
│   │   │   └── websocket.js           # WSS connection manager
│
├── backend/                           # FastAPI Application
│   ├── main.py                        # App entry & routing
│   ├── config.py                      
│   ├── api/
│   │   ├── chat_router.py             # Replaces Twilio webhook
│   │   └── ws_router.py               # WebSocket broadcaster for events
│   ├── core/
│   │   ├── vaani_audio.py             # FFmpeg conversion, Sarvam API wrapper
│   │   └── orchestrator/              # LangGraph definitions
│   ├── agents/
│   │   ├── catalog_agent.py
│   │   ├── customer_agent.py
│   │   ├── growth_agent.py
│   │   └── returns_agent.py
│   ├── db/
│   │   └── supabase_client.py         # Handles both relational & pgvector operations
│
└── scripts/
    ├── seed_catalog.py                # Seeds mock catalog and embeds items into Supabase
    └── test_end_to_end.py             # Pytest suite
```

---

## 4. ENVIRONMENT SETUP & CONFIGURATION

### 4.1 Required Environment Variables (`.env`)

```env
# ── SYSTEM CONFIGURATION ──────────────────────────────────
PORT=8000
ENVIRONMENT=development
FRONTEND_URL=http://localhost:5173
WS_HEARTBEAT_INTERVAL=30

# ── SARVAM AI & GOOGLE GEMINI ─────────────────────────────
SARVAM_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GEMINI_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GEMINI_MODEL=gemini-2.5-flash
GEMINI_IMAGE_MODEL=imagen-3.0-generate-001

# ── SUPABASE CONFIGURATION ────────────────────────────────
SUPABASE_URL=https://xxxxxxxxxxx.supabase.co
SUPABASE_SERVICE_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 4.2 Start-up Commands (Run Locally)

**Terminal 1 (Backend):**
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Ensure ffmpeg is installed locally! (brew install ffmpeg / apt install ffmpeg)
python scripts/seed_catalog.py
cd backend
uvicorn main:app --reload --port 8000
```

**Terminal 2 (Frontend):**
```bash
cd frontend
npm install
npm run dev
# App running at http://localhost:5173
```

---

## 5. DATABASE & VECTOR SCHEMA

### 5.1 Supabase Schema (PostgreSQL)

*   `resellers`: Core user data (id, phone, name, region for dialect).
*   `listings`: Products active in the reseller's catalog (margin, price, auto-caption).
*   `orders` & `returns`: Transactional data for Growth and Returns agents.
*   `conversations`: Chat history (User vs System).

**Crucial Upgrade: Agent Events Table (For Judge Dashboard):**
Table `agent_events` is actively streamed via WebSocket to the React Frontend.
```sql
CREATE TABLE agent_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(100),
    event_type VARCHAR(50),      -- e.g., "intent_detected", "rag_retrieval", "tts_generated"
    agent_name VARCHAR(50),      -- "Orchestrator", "CatalogAgent", "CustomerAgent"
    latency_ms INTEGER,
    payload JSONB,               -- Conf scores, RAG context matched, tool parameters
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 5.2 Supabase Vector Schema (pgvector)
We use the `pgvector` extension in Supabase to keep vector search fully cloud-native, avoiding local model loads and memory overhead:
* **Table name:** `product_embeddings`
* **Embeddings Model:** Google Gemini `text-embedding-004` (768 dimensions)
* **Metadata Fields:** Stored alongside embeddings (`category`, `suggested_selling_price_inr`, `meesho_cost_inr`, `material`, `sizes`, `colors`, `return_window_days`).
* **Query Matcher:** Custom database RPC function `match_products` calculates Cosine distance (`<=>` operator) and retrieves similar SKUs.

---

## 6. CORE MODULES — DETAILED SPECS

### 6.1 React Web App (Reseller UI & Judge Dashboard)
**Location:** `frontend/src/`

*   **Responsive Grid:** On Mobile screens (< 768px), shows *only* the Chat UI. On Desktop, divides into a `grid-cols-2`. Left: Chat UI. Right: Live System Tracing & Analytics.
*   **Voice Recorder (`VoiceRecorder.jsx`):** Uses the `MediaRecorder` API. Captures audio as `.webm`. Uploads as `FormData` to backend. Includes visual audio waves to show recording state.
*   **Audio Player:** Auto-plays the TTS file when Sakhi responds.
*   **Judge View (`AgentTraceLog.jsx`):** Listens on WebSocket. When Sakhi processes a query, this window auto-scrolls showing raw JSON inputs, detected intents, and tool executions.

### 6.2 API Gateway & Media Processing (Vaani Layer)
**Location:** `backend/api/chat_router.py` & `backend/core/vaani_audio.py`

Browsers natively record in `.webm` or `.mp4` (Safari). Sarvam AI strictly requires `16kHz mono .wav`. 
```python
# In backend/core/vaani_audio.py
async def convert_to_wav(input_file_path: str) -> str:
    """Uses ffmpeg-python to strip video, convert to 1 channel, 16000Hz"""
    output_path = input_file_path.replace(".webm", ".wav")
    stream = ffmpeg.input(input_file_path)
    stream = ffmpeg.output(stream, output_path, acodec='pcm_s16le', ac=1, ar='16k')
    ffmpeg.run(stream, overwrite_output=True, quiet=True)
    return output_path
```

---

## 7. AGENT PERSONAS & SYSTEM PROMPTS

To ensure zero-hallucination and a perfectly dialed "Didi" persona, Gemini must be configured with exact prompts.

### 7.1 Orchestrator (Intent Router)
```text
SYSTEM: You are the Orchestrator for Sakhi, an AI business manager for a Hindi-speaking Meesho reseller.
Your only job is to analyze the user's input and route it to EXACTLY ONE of the following agents:
1. CATALOG: User wants to list a product, set prices, or create a WhatsApp promotional post.
2. CUSTOMER: User is relaying a question a buyer asked (e.g., about size, material, delivery).
3. GROWTH: User is asking for sales advice, performance metrics, or what to sell this week.
4. RETURNS: User is complaining about a product, wants to return, or exchange.
5. GENERAL: General greetings or questions about your capabilities.

Output ONLY valid JSON: {"intent": "AGENT_NAME", "confidence": 0.0-1.0}
```

### 7.2 Catalog Agent (WhatsApp Creator)
```text
SYSTEM: You are 'Catalog Didi'. The reseller wants to list the provided product.
Context provided: [Retrieved Product Details from Supabase Vector RAG] and [Reseller's Price].
Task: Write a highly engaging WhatsApp promotional message in Hindi (written in English script/Hinglish).
Include: Emojis, FOMO (Fear Of Missing Out), Key features, and the Final Price.
Do NOT exceed 5 lines. End with "Order karne ke liye mujhe message karein!"
```

### 7.3 Customer Agent (Strict RAG)
```text
SYSTEM: You are 'Customer Didi'. Answer the buyer's query based ONLY on the provided context.
Context: [Supabase Vector Product Metadata].
Rules:
- If the context does not contain the answer (e.g., they ask for a color not listed), you MUST say: "Maaf kijiyega, mere pas abhi iski detail nahi hai. Mai Didi se puch kar batati hu."
- NEVER hallucinate facts.
- Respond in polite conversational Hindi.
```

---

## 8. API ENDPOINTS & WEBSOCKET (LIVE TRACING)

| Method | Endpoint | Payload / Protocol | Description |
|---|---|---|---|
| `POST` | `/api/v1/chat/send` | `multipart/form-data` | Accepts text/audio. Converts -> ASR -> LLM -> TTS. Returns text + audio URL. |
| `GET` | `/api/v1/chat/history`| `?user_id=123` | Fetch previous N chat turns for the UI on initial load. |
| `WS` | `/ws/agent-logs` | `WebSocket` | **[CRITICAL FOR JUDGES]** Broadcasts internal state changes from LangGraph to the React dashboard in real-time. |
| `POST`| `/api/v1/system/growth`| `{"user_id": "123"}` | Manually trigger the Sunday Weekly Growth Note for live demo purposes. |

### WebSocket Trace Example Payload:
```json
{
  "timestamp": "2026-07-15T10:14:00Z",
  "agent": "Orchestrator",
  "action": "Intent Routing",
  "latency_ms": 350,
  "data": {
    "detected_intent": "CATALOG",
    "confidence": 0.98,
    "trigger_text": "is blue kurti ko 499 me add kardo"
  }
}
```

---

## 9. EDGE CASES & ERROR HANDLING STRATEGY

To secure points in the "Working Prototype" and "Robustness" criteria, we must implement fallbacks:

1.  **Sarvam AI ASR Timeout/Rate Limit:** 
    *   *Action:* Backend traps `503/429` error.
    *   *Fallback:* Fails gracefully. React UI shows standard message: "Network slow hai didi, kripya type karke bhejien." (Network is slow, please type).
2.  **No RAG Match Found (Supabase Vector search returns low similarity):**
    *   *Action:* LangGraph short-circuits the LLM generation. 
    *   *Fallback:* Returns standard voice note: "Mujhe ye product catalog me nahi mila." (I couldn't find this in the catalog).
3.  **UI Latency / TTS Generation Delay:**
    *   *Action:* Optimistic UI update. The moment the LLM generates the text response, it displays in the chat bubble instantly. A loading spinner appears next to a "Speaker" icon while the MP3 is generated and fetched in the background.

---

## 10. END-TO-END FLOW — STEP BY STEP

**Scenario:** Reseller holds mic, speaks: *"Is blue cotton saree ko meri list me daal, price 599"*

1.  **React UI:** `MediaRecorder` captures `.webm` -> POSTs to `/api/v1/chat/send`.
2.  **Audio Prep:** `vaani_audio.py` runs FFmpeg -> `.wav`.
3.  **ASR:** Sarvam Saarika transcribes audio to Hindi text.
4.  **Orchestrator Node:** Gemini detects `Intent: Catalog`. *Emits WS event to Judge Dashboard.*
5.  **Catalog Agent Node:** 
    *   Searches Supabase Vector DB for "blue cotton saree". Matches `SKU_088` (Cost: 350).
    *   Sets reseller price: 599 (Margin: 249).
    *   Gemini generates WhatsApp caption.
    *   Imagen 3.0 generates composite image (if applicable).
    *   *Emits WS event with DB query results.*
6.  **DB Save:** Inserts into Supabase `listings` table.
7.  **TTS:** Hindi text sent to Sarvam Bulbul -> uploaded to Supabase Storage -> gets `.mp3` public URL.
8.  **Response:** JSON returns to frontend. Chat bubble updates, MP3 auto-plays.

*(Total Execution Target: < 4.5 seconds end-to-end)*

---

## 11. DEMO SCENARIOS (JUDGE-READY)

*Team Orchestrator: Practice these exact flows for the final video/pitch submission.*

| Demo ID | Persona Setup | Input Action | Expected Output | Highlight to Judges |
| :--- | :--- | :--- | :--- | :--- |
| **D1: Onboarding** | New Reseller | "Hi, main Sunita, Sakhi kya hai?" | Warm welcome audio, explains she can handle catalog and returns. | Multi-modal output (Voice + Text). |
| **D2: Catalog** | Reseller wants to post | Voice: "Blue kurti list kardo, 499 me" | AI creates Hindi caption + product photo + saves listing. | Auto-margin calc. Trace logs UI update. |
| **D3: Customer RAG**| Buyer asks question | Text: "Kya ye kurti L size me hai?" | "Ji, L size available hai." (Answers strictly from DB context). | *Zero Hallucination RAG.* |
| **D4: Growth Coach**| Trigger manual event | Click "Send Weekly Note" in UI | "Sunita didi, last week 10 kurti biki..." | Scheduled AI triggers & localized business empathy. |
| **D5: Returns FSM** | Buyer unhappy | Text: "Saree choti pad rahi hai" | Apologizes, maps issue to Size mismatch, offers free exchange. | Context-aware memory & sympathetic agent state machine. |

---

## 12. OPEN-SOURCE ATTRIBUTION (MANDATORY CHECKLIST)

As per **Round 3 Instructions (Section 7)**, here is the exact attribution table to be placed directly in the `README.md`.

| Library/Tool | Version | License | Role in Build | Source Link |
|---|---|---|---|---|
| **React** | 18.2.0 | MIT | Frontend Web Framework UI | [facebook/react](https://github.com/facebook/react) |
| **Vite** | 5.2.0 | MIT | Frontend Build Tool | [vitejs/vite](https://github.com/vitejs/vite) |
| **Tailwind CSS** | 3.4.1 | MIT | Styling & Responsive UI | [tailwindlabs/tailwindcss](https://github.com/tailwindlabs/tailwindcss) |
| **FastAPI** | 0.111.0| MIT | Python Backend & API router | [tiangolo/fastapi](https://github.com/tiangolo/fastapi) |
| **LangGraph** | 0.1.19 | MIT | Orchestrator State Machine FSM | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) |
| **LangChain** | 0.2.6 | MIT | AI Agent integrations | [langchain-ai/langchain](https://github.com/langchain-ai/langchain) |
| **Supabase (Python)**| 2.5.0 | MIT | App DB (Users, Logs, Memory, pgvector) | [supabase/supabase-py](https://github.com/supabase-community/supabase-py) |
| **FFmpeg-Python** | 0.2.0 | MIT | Audio transcoding (WebM to WAV) | [kkroening/ffmpeg-python](https://github.com/kkroening/ffmpeg-python) |

*Note: Free APIs used for AI endpoints include Google Gemini 2.5 (Flash/Imagen) and Sarvam AI (Saarika/Bulbul).*

---

## 13. DEPLOYMENT GUIDE

**Backend (Render.com - Web Service)**
1.  Connect GitHub repo. Build command: `pip install -r requirements.txt`.
2.  Start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
3.  Add all `.env` vars in Render Dashboard. Ensure Render environment supports `ffmpeg` buildpacks.

**Frontend (Vercel.com)**
1.  Connect GitHub repo. Set Framework Preset to **Vite**.
2.  Root Directory: `frontend/`.
3.  Environment Variable: `VITE_API_URL` -> Output URL from Render deployment (e.g. `https://sakhi-api.onrender.com`).

---

## 14. README SUBMISSION TEMPLATE

*Use this exact structure for the root `README.md` to guarantee maximum points on Completeness & Documentation.*

```markdown
# 🌸 SAKHI — The AI Business Didi for Meesho Resellers
**ScriptedBy{Her} 2.0 | Round 3 Prototype Submission | Team Orchestrator**

Sakhi is an agentic AI co-pilot designed specifically for Tier 2/3 female resellers. Built with LangGraph, FastAPI, and React, Sakhi manages cataloging, customer queries, growth tracking, and returns via seamless voice interactions.

## 🔗 Critical Hackathon Links
- **Pitch Deck / Concept Doc:** [Insert Link]
- **Live Interactive Demo:** [Insert Vercel Deployment URL]
- **Demo Video Walkthrough:** [Insert YouTube Link]

## 🛠 Features (Fully Functional Prototype)
1. **Voice-Native Interface:** Speak in Hindi, get Hindi voice replies (Powered by Sarvam AI).
2. **LangGraph Multi-Agent System:** Intelligently routes between Catalog, Customer, Growth, and Returns agents.
3. **Zero Hallucination RAG:** Cloud-native vector search (Supabase pgvector) strictly linked to a Mock Meesho Catalog database.
4. **Judge View Dashboard:** Real-time WebSocket streaming of AI state transitions for complete architectural transparency.

## 🚀 Run Locally
### Prerequisites
- Node.js (v18+) & Python (v3.11+)
- FFmpeg installed locally (`brew install ffmpeg` / `sudo apt install ffmpeg`)

### 1. Setup Backend
\`\`\`bash
git clone https://github.com/your-repo/sakhi-prototype.git
cd sakhi-prototype
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env # Add API keys
cd backend
uvicorn main:app --reload
\`\`\`

### 2. Setup Frontend
\`\`\`bash
cd frontend
npm install
npm run dev
\`\`\`

## ⚖️ Open-Source Attribution
[Insert Table from PRD Section 12 here]
```

---

## 15. DAY-BY-DAY BUILD PLAN (13–19 JULY)

*   **Day 1 (July 13): Scaffold & DB.** Setup monorepo. Create Supabase tables with pgvector extension. Seed Supabase mock catalog with generated embeddings.
*   **Day 2 (July 14): React UI Foundation.** Build chat UI using Tailwind. Implement Web Audio API for recording. Test dummy API connections.
*   **Day 3 (July 15): Core Backend & Voice.** Build FastAPI endpoints. Implement FFmpeg audio conversion. Integrate Sarvam ASR + TTS.
*   **Day 4 (July 16): Orchestrator & Catalog.** Build LangGraph setup. Integrate Gemini Intent routing. Build Catalog tool (DB listing + Gemini image generation). Wire WebSocket base.
*   **Day 5 (July 17): Specialists (Customer, Growth, Returns).** Setup RAG logic for Customer Agent. Complete Returns State Machine. Ensure all agents emit WS events to React Judge Dashboard.
*   **Day 6 (July 18): Integration & Edge Cases.** E2E testing of the 4 core Demo Scenarios. Implement fallback handling (timeouts, empty RAG results). Fix UI bugs. 
*   **Day 7 (July 19): Deployment & Video.** Deploy to Vercel/Render. Record the 3-minute pitch video. Ensure all Checklist items are met. Submit!

---

## 16. HACKATHON SUBMISSION CHECKLIST

*This checklist maps perfectly to the evaluation criteria of the competition provided in the instructions.*

- [ ] **Working Prototype:** Deployed Frontend + Backend live (URLs working).
- [ ] **Core Features Hand-coded:** All 4 AI agents logic is fully implemented, not mocked.
- [ ] **Presentation Deck:** Business model, target user, and tech architecture clearly mapped.
- [ ] **Source Code Repo:** Public GitHub link added to submission form.
- [ ] **Setup Guide (README.md):** Complete steps included.
- [ ] **Attribution (README.md):** Open-source licensing grid filled properly.
- [ ] **Tested Scenarios:** Ran through Demos 1-5 without crashing.
- [ ] **Mobile Responsive & UX:** Verified the chat UI looks excellent on mobile viewports for UX points.

---
*End of PRD. Team Orchestrator: Stick to this blueprint strictly during the 7-day build to ensure delivery against the exact scoring rubric of ScriptedBy{Her} Round 3.*