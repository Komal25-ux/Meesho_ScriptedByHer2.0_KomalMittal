<div align="center">

# 🌸 Sakhi — Agentic AI for Bharat

### The AI Business Didi for every Meesho reseller.

*An agentic AI co-pilot that runs a reseller's entire business — sourcing, selling, customer
chats, and growth — through a voice-first, vernacular-first conversational experience.*

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agent%20Orchestration-1C1C1C)](https://www.langchain.com/langgraph)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)](https://vitejs.dev/)
[![Gemini](https://img.shields.io/badge/Google%20Gemini-LLM-4285F4?logo=google&logoColor=white)](https://ai.google.dev/)
[![Supabase](https://img.shields.io/badge/Supabase-pgvector-3ECF8E?logo=supabase&logoColor=white)](https://supabase.com/)

</div>

---

## 📋 Table of Contents
1. [Theme Alignment](#-theme-alignment--building-for-bharat-with-the-power-of-agentic-ai)
2. [Originality Declaration](#-originality-declaration)
3. [Prototype Showcase](#-prototype-showcase)
4. [Open-Source Attribution](#-open-source--third-party-attribution)
5. [Local Setup Guide](#-foolproof-local-setup-guide)

---

## 🇮🇳 Theme Alignment — "Building for Bharat with the Power of Agentic AI"

Sakhi is built for the reseller the mainstream Indian internet still leaves behind: a woman
running her Meesho business out of Tier‑2/3/4 Bharat, in Hindi, often with limited formal
digital literacy — someone for whom a dashboard full of English text and forms was never
actually designed. Sakhi replaces that dashboard with a conversation. She talks to Sakhi the way
she already talks to her customers — by **voice, in her own language** — and instead of a single
chatbot giving generic replies, **four coordinated specialist agents** (Catalog, Customer,
Growth, and Returns), routed by a LangGraph orchestrator, actually run the parts of her business
that used to eat her entire day: drafting a WhatsApp-ready product listing with her real margin
spelled out, answering a buyer's question from her real catalog instead of guessing, coaching her
weekly on what's selling, and turning a return request into a saved sale — all grounded in real
data, never hallucinated, and all narrated back to her in natural, correctly‑pronounced Hindi
speech. This **is** agentic AI for Bharat: not a smarter search box, but a genuine AI operating
layer built around voice, vernacular language, and zero-literacy-barrier trust, for the country's
1.7 crore Meesho resellers — 80% of whom are exactly this woman.

## ✅ Originality Declaration

> **This project — all code, prompts, architecture, and UI in this repository — is original
> work, conceived and developed entirely within the official hackathon submission period.**
> It has not been submitted, in whole or in part, to any other hackathon, competition, or
> commercial product prior to this submission. All third-party tools used are limited to the
> open-source libraries and API services explicitly listed and attributed in the
> [Open-Source Attribution](#-open-source--third-party-attribution) section below.

---

## 🚀 Prototype Showcase

| | |
|---|---|
| 🌐 **Deployed App Link** | `https://meesho-sakhi-komal25.vercel.app/` |
| 💻 **Source-code Repository** | `https://github.com/Komal25-ux/Meesho_ScriptedByHer2.0_KomalMittal` |

> 💡 **For Judges:** The deployed app link is a real, publicly hosted instance (frontend on
> Vercel, backend on Render) — not a localhost recording. The Reseller ↔ Customer toggle inside
> the app lets you simulate both sides of a real WhatsApp conversation in a single session, and
> the **"Orchestrator's Brain"** panel streams the live LangGraph agent trace in real time so you
> can watch the routing decisions happen as you interact with it.

---

## 📦 Open-Source & Third-Party Attribution

In strict compliance with the submission checklist, every core library and service this
prototype depends on is declared below.

| Library Name & Version | License Type | Role in Build | Source Link |
|---|---|---|---|
| **LangGraph** `1.2.9` | MIT | Multi-agent orchestration state machine — routes intent across the Catalog, Customer, Growth, and Returns agents and manages human-in-the-loop approval states. | [github.com/langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) |
| **FastAPI** `0.139.0` **/ Python** `3.13` | MIT | High-performance async backend API — serves chat, TTS/ASR, and the WebSocket agent-trace stream. | [github.com/fastapi/fastapi](https://github.com/fastapi/fastapi) |
| **React** `18.3.1` **/ Vite** `5.3.1` | MIT | Frontend PWA UI — the split-screen chat + judge-dashboard interface. | [github.com/facebook/react](https://github.com/facebook/react) · [github.com/vitejs/vite](https://github.com/vitejs/vite) |
| **Tailwind CSS** `3.4.4` | MIT | Utility-first styling and the "Denim & Industrial Craft" design system. | [github.com/tailwindlabs/tailwindcss](https://github.com/tailwindlabs/tailwindcss) |
| **Recharts** `2.12.7` | MIT | Growth & Sales data visualization — Area, Pie/Donut charts on the Growth Dashboard. | [github.com/recharts/recharts](https://github.com/recharts/recharts) |
| **Supabase** (`supabase-py` `2.31.0`) | MIT / Apache-2.0 (client SDK) | PostgreSQL database & `pgvector` similarity search — reseller/catalog data and RAG product retrieval. | [github.com/supabase/supabase-py](https://github.com/supabase/supabase-py) |
| **Google Gemini SDK** (`google-generativeai` `0.8.6`) | Apache 2.0 | Core LLM for agent reasoning, structured-output intent routing, embeddings, and dual-language (Hinglish/Devanagari) response generation. | [github.com/google-gemini/generative-ai-python](https://github.com/google-gemini/generative-ai-python) |
| **Sarvam AI** (Saarika ASR / Bulbul TTS) | Commercial API (Proprietary SaaS — no bundled OSS license; accessed via REST under Sarvam's API Terms) | Regional Hindi/Hinglish Speech-to-Text and Text-to-Speech — the voice layer that lets a reseller speak to and hear from Sakhi in natural Hindi. | [sarvam.ai](https://www.sarvam.ai/) |

> ℹ️ **Note on versions:** Frontend versions are pinned exactly via `package.json`/`package-lock.json`.
> Backend versions above reflect the actual resolved versions in this project's development
> environment; `requirements.txt` itself does not pin exact versions, so a fresh `pip install`
> will resolve the latest compatible releases at install time. The full transitive dependency
> list for both stacks is available in `requirements.txt` and `frontend/package.json` for
> complete transparency.

---

## 🛠️ Foolproof Local Setup Guide

> Written for a judge on a **completely fresh machine** — no `venv`, no `node_modules`, nothing
> pre-installed beyond the prerequisites below.

### ✅ Prerequisites

| Requirement | Version | Why |
|---|---|---|
| 🐍 **Python** | `3.10+` (developed on 3.13) | Runs the FastAPI + LangGraph backend |
| 🟢 **Node.js** | `18+` | Runs the React + Vite frontend |
| 🎞️ **ffmpeg** (system binary, not a pip package) | any recent version | Required to transcode browser-recorded voice notes before sending them to Sarvam's ASR — install via `brew install ffmpeg` (macOS), `sudo apt install ffmpeg` (Linux), or [ffmpeg.org/download.html](https://ffmpeg.org/download.html) (Windows) |

> 🟢 **Good news for judges in a hurry:** every API key below is optional at boot. The backend is
> designed to **degrade gracefully with zero keys configured** — every config value defaults
> safely so the app starts and the UI is fully browsable even before you plug in a single key.
> You only need real keys to see live Gemini reasoning, real Sarvam voice, and real Supabase
> data instead of mock fallbacks.

---

### 1️⃣ Clone the Repository

```bash
git clone <repository-url>
cd Meesho_ScriptedbyHer2.0
```

---

### 2️⃣ Backend Setup (Python — FastAPI + LangGraph)

> ⚠️ **Important:** Run every command below from the **project root**, not from inside
> `backend/` — `requirements.txt` lives at the root, and the backend's own code imports itself as
> the `backend` package (e.g. `from backend.core... import ...`), so it must be launched from one
> level above.

**a. Create and activate a virtual environment** (at the project root):

```bash
python -m venv venv
```

<table>
<tr><td>

**macOS / Linux**
```bash
source venv/bin/activate
```

</td><td>

**Windows (Command Prompt)**
```bat
venv\Scripts\activate.bat
```

**Windows (PowerShell)**
```powershell
venv\Scripts\Activate.ps1
```

</td></tr>
</table>

**b. Install dependencies:**

```bash
pip install -r requirements.txt
```

**c. Set up your environment file** — copy the template and fill in your keys:

```bash
cp .env.example .env      # macOS / Linux
copy .env.example .env    # Windows
```

At minimum, the following keys unlock full functionality (all others in `.env.example` are
optional fallback/rotation keys — see the file's inline comments):

```env
# Google Gemini — LLM reasoning, structured routing, embeddings
GEMINI_API_KEY=your_gemini_api_key_here

# Sarvam AI — Hindi/Hinglish ASR + TTS
SARVAM_API_KEY=your_sarvam_api_key_here

# Supabase — PostgreSQL + pgvector RAG store
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_KEY=your_supabase_service_role_key
```

> 🗄️ **Optional but recommended:** run `backend/db/supabase_schema.sql` in your Supabase
> project's SQL editor once, then seed the demo catalog with `python scripts/seed_catalog.py`, to
> see real RAG-grounded product search instead of the built-in mock fallback.

**d. Run the backend server** (still from the project root):

```bash
uvicorn backend.main:app --reload --port 8000
```

You should see Uvicorn confirm it's running at `http://127.0.0.1:8000` — visit
`http://127.0.0.1:8000/docs` to confirm the API is live.

> 💡 A convenience script is also available: `npm run backend:dev` (from the root
> `package.json`) runs this exact same command.

---

### 3️⃣ Frontend Setup (React + Vite)

**a. Open a new terminal** (keep the backend running in the first one), then:

```bash
cd frontend
npm install
```

**b. Set up your environment file** (optional for local development):

```bash
cp .env.example .env.production   # only needed if pointing at a non-default backend
```

```env
# Only required if your backend is NOT running on http://localhost:8000
VITE_API_URL=http://localhost:8000
```

> ℹ️ You can safely **skip this step for local development** — the frontend already defaults to
> `http://localhost:8000` if `VITE_API_URL` isn't set, which matches the backend command above
> exactly. It's only required if you're pointing the frontend at a different/deployed backend.

**c. Run the frontend dev server:**

```bash
npm run dev
```

Vite will print a local URL (typically `http://localhost:5173`) — open it in your browser. The
app should load with Sakhi's greeting already visible, backend fully connected. 🌸

---

<div align="center">

**That's it — Sakhi is running end-to-end on your machine.**

Made by Komal Mittal with 🩷 for Bharat's 1.7 crore Meesho resellers.

</div>
