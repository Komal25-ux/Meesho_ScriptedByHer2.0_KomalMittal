# How Sakhi is tested

560 automated tests run in about 2.5 seconds on every push. The method behind them, written as rules that a person or an AI assistant follows, is in [skills/test-design/SKILL.md](skills/test-design/SKILL.md). A mutation run
measures whether those tests would actually catch bugs, and a separate
evaluation measures the part no automated test can: whether Gemini makes the
right call.

```bash
pip install -r requirements-dev.txt
pytest                                   # everything
pytest backend/tests/unit                # one level
HYPOTHESIS_PROFILE=ci pytest             # property tests with CI's fixed seed
mutmut run && mutmut results             # mutation testing (setup.cfg)
python scripts/run_llm_eval.py --check   # is the LLM evaluation current? (never calls Gemini)
```

## 1. What could go wrong, and where it is covered

Testing effort follows risk. These are ranked by the harm to a reseller or
buyer if they slipped through.

| # | Risk | What a failure looks like | Covered in |
|---|---|---|---|
| 1 | A wrong price reaches a buyer or a WhatsApp group | Listing posted at a price she never set; buyer quoted ₹1 after an injection | `unit/test_pricing.py`, `components/test_customer_agent.py`, `components/test_injection_defences.py`, `components/test_approval_gate.py` |
| 2 | An order is lost, or placed twice | "Order confirmed" with no order row; a retry creates a second order | `components/test_customer_agent.py` (failed save, duplicate orders), `adapters/test_database_client.py`, `journeys/test_customer_journeys.py` |
| 3 | One visitor's conversation leaks into another's | Tab B's "yes" posts tab A's draft; traces show someone else's messages | `journeys/test_conversation_isolation.py`, `api/test_security.py` |
| 4 | The model is talked into something | A buyer reaches reseller-only agents; a reply states a fake price | `components/test_intent_router.py`, `components/test_injection_defences.py`, `unit/test_prompt_safety.py`, LLM eval |
| 5 | A failure is presented as an answer | Database down reads as "we don't sell that" | `adapters/test_database_client.py`, `api/test_chat_endpoint.py` (503), `adapters/test_gemini_client.py` |
| 6 | State is lost mid-conversation | A restart forgets the draft or the return in progress | `journeys/test_restart_survival.py`, `adapters/test_session_store.py` |
| 7 | The service is abused | Scripted requests drain quota; a huge upload fills the disk; a filename writes outside the upload folder | `api/test_limits.py`, `unit/test_rate_limiter.py`, `unit/test_body_size_limit.py`, `api/test_uploads.py` |
| 8 | Business figures are wrong | Coaching names the wrong category as most profitable | `unit/test_sales_metrics.py`, `components/test_growth_agent.py` |
| 9 | A decision flow takes the wrong branch | Returns funnel offers nothing, or loops; picker never resolves | `components/test_returns_funnel.py`, `components/test_selection_gate.py`, `components/test_context_lock.py` |
| 10 | The model simply decides wrongly | "saree leni hai" treated as a confirmed order | LLM eval (`backend/evals/`) |

## 2. Levels

Each behaviour is tested at the lowest level that can show it.

| Level | Tests | What it covers | What stands in for the outside world |
|---|---:|---|---|
| `unit/` | 267 | Pure rules: pricing, price parsing, keyword matching, verdict parsing, prompt fencing, rate and size limits, sales metrics, timing, the eval runner's own rules | Nothing; plain inputs and outputs |
| `components/` | 121 | One agent or graph gate at a time | `support/` fakes |
| `journeys/` | 14 | Whole conversations through the compiled LangGraph graph, message by message | `support/` fakes |
| `adapters/` | 70 | The edges: session store, Supabase client, Gemini client, audio, startup guards | Hand-written fakes of each SDK |
| `api/` | 88 | HTTP: response contract, validation, uploads, limits, CORS and WebSocket security, concurrency | `support/` fakes behind the real FastAPI app |

### Test doubles: fakes, not patch stacks

The previous suite mostly stacked 5–10 `patch()` calls on import paths per
test, so any refactor broke tests that weren't about it, and many tests only
proved a mocked value came back unchanged. Agents now run against three
hand-written fakes in `backend/tests/support/`:

- **`ScriptedGemini`**: replies are queued per response type, and every
  prompt is recorded, so a test can check what the model was *told*. An
  empty script returns `None`, exactly like the real client after every
  model and key has failed, so "Gemini is down" needs no special setup.
- **`Classifiers`**: fixes each small yes/no or category decision, so a test
  chooses the branch it wants. The classifiers themselves are tested in
  `unit/`.
- **`FakeSupabase`**: in-memory catalog, listings, orders and returns, with
  `fail("save_order")` for fault injection and a clock for time-based rules.

The harness installs them wherever the app imported the real thing, so no
test names an import path. Tests assert **outcomes**: rows saved, prompts
sent, replies returned.

## 3. Techniques, and where to see them

| Technique | Where it is used |
|---|---|
| **Boundary values** | Pricing crossover at cost 349/350/351 (`test_pricing.py`); price above cost 499/500/501 (`test_approval_gate.py`, `test_catalog_agent.py`); message length 999/1000/1001 and request body 999/1000/1001 bytes; repeat-order window at 9.99/10/10.01 minutes; rate window at 59.999/60/60.001 s; a limit of zero |
| **Equivalence classes** | Price formats (₹599, Rs.899, 599/-, 5,999, 1,00,000); numbers that are *not* prices (sizes, days, percentages); valid vs malformed session IDs; filenames with paths |
| **Decision tables** | Approval gate (classifier verdict × price present × above cost); each classifier's outage fallback (refusal × agreement × price); buyer price (listed × catalog price) |
| **State transitions** | The returns funnel, every transition from `awaiting_grievance` and `awaiting_confirmation` (`test_returns_funnel.py`); the session store's per-turn cache (`test_session_store.py`) |
| **Property-based (Hypothesis)** | 12 properties, e.g. "no cost ever yields less than ₹150 profit or a 30% margin", "any text produces exactly one fenced block", "no window ever admits more than the limit", "a longer sales window never shows less" |
| **Negative and adversarial** | Prompt injection (typed closing tags, fake SYSTEM lines, "price ₹1"); path traversal; forged origins; malformed IDs |
| **Fault injection** | Database down at each critical call; Gemini down; model returns broken JSON; transcription fails; Sarvam returns no audio |
| **Concurrency** | A slow turn must not block `/health`; two voice notes must be generated in parallel. Both use events rather than sleeps, so they are deterministic. |
| **Regression** | Every defect in section 4 has a test that pins the fix. The fallback-table regressions and the upload, concurrency and listing-retry tests were also run against the pre-fix code, and failed there |
| **Known limitation** | `test_last_month_is_thirty_days` is a strict `xfail`: it documents that "pichle mahine" isn't parsed, and fails loudly the day it is |
| **Mutation testing** | Section 5 |
| **Model evaluation** | Section 6 |

## 4. Defects found

Defects found while hardening the backend and rewriting these tests. Each
one has a test that pins the fix.

| # | Defect | Found by | Pinned by |
|---|---|---|---|
| 1 | Upload filename used as a path: `../../main.py` wrote outside the upload folder, then the cleanup deleted it | Code review; reproduced | `api/test_uploads.py::test_a_path_in_the_client_filename_never_reaches_the_disk` |
| 2 | Every browser uploaded `reseller_recording.webm`, so simultaneous voice notes overwrote each other | Code review | `api/test_uploads.py::test_two_uploads_with_the_same_name_never_share_a_file` |
| 3 | The frontend sent one hard-coded number and conversations were keyed on it, so every visitor shared one conversation | Code review | `journeys/test_conversation_isolation.py::test_over_http_two_tabs_with_the_same_number_are_two_conversations` |
| 4 | Agent traces (with the user's words and number) went to every open dashboard | Code review | `api/test_security.py::test_a_turns_traces_reach_its_own_dashboard_and_no_other` |
| 5 | `GET /chat/history` returned any reseller's chats to whoever knew the number | Code review | `api/test_system_endpoints.py::test_the_old_chat_history_endpoint_is_gone` |
| 6 | Conversation state lived in process memory and vanished on restart | Code review | `journeys/test_restart_survival.py` |
| 7 | The synchronous graph ran on the event loop, so one slow turn froze the server | Code review | `api/test_concurrency.py::test_a_slow_turn_does_not_stop_the_server_answering_others` |
| 8 | Database errors became empty or placeholder results ("order confirmed" with no order saved) | Code review | `adapters/test_database_client.py::test_an_unreachable_database_is_raised_on_the_critical_path` |
| 9 | A failed embedding made search return the two hard-coded demo products as real results | Code review | `adapters/test_database_client.py::test_a_real_search_with_no_query_returns_nothing_rather_than_demo_products` |
| 10 | The Gemini speech-to-text fallback used an audio format the SDK rejects, so it could never work | Code review; confirmed against the SDK | `adapters/test_audio.py::test_when_sarvam_is_unavailable_gemini_hears_the_audio_in_a_form_its_sdk_accepts` |
| 11 | An unrecognised voice note was answered as if the user had said "hello" | Code review | `api/test_chat_endpoint.py::test_a_voice_note_with_no_recognisable_speech_is_rejected` |
| 12 | A failed listing save threw the draft away | Test | `components/test_finalize_listing.py::test_a_failed_save_keeps_the_draft_and_announces_nothing` |
| 13 | The pricing rule truncated, leaving the margin just under the promised 30% for most costs | Property test | `unit/test_pricing.py::test_suggested_price_always_keeps_the_minimum_margin` |
| 14 | "5,999" was read as 999, "size 42 wali 599" as 42, and "₹599" was ignored by the catalog agent | Equivalence-class tests | `unit/test_pricing.py::test_requested_price_reads_the_ways_resellers_write_prices` |
| 15 | Outage fallbacks matched inside words ("ok" in "book", "dress" in "address") and checked agreement before refusal ("kal confirm karungi, abhi ruko" approved a draft) | Decision-table tests | `unit/test_classifier_fallbacks.py`, rows marked *regression* |
| 16 | Buyers were quoted the catalog price, not the price the reseller had listed at | Component test | `components/test_customer_agent.py::test_a_listed_product_is_quoted_at_the_resellers_own_price` |
| 17 | **A regression from the persistence change (#6):** a second read of the on-screen product discarded its buyer price, so orders went in at the catalog price | Component test | `components/test_customer_agent.py::test_an_order_records_whether_the_reseller_had_listed_the_product` |
| 18 | Growth coaching named the top-*revenue* category as the most *profitable* | Component test | `components/test_growth_agent.py::test_with_gemini_down_the_report_states_the_figures_and_the_real_profit_leader` |
| 19 | The rate limiter crashed with a limit of zero | Boundary test | `unit/test_rate_limiter.py::test_a_limit_of_zero_admits_nothing` |
| 20 | User text sat inside plain quotes in every prompt, and nothing checked the prices in replies | Code review | `components/test_injection_defences.py` |
| 21 | A retried request or a re-typed confirmation could create a second order | Code review | `components/test_customer_agent.py`, "duplicate orders" section |
| 22 | No limits on request rate, body size or message length | Code review | `api/test_limits.py`, `unit/test_body_size_limit.py` |

The LLM evaluation (section 6) found no further defects.

## 5. Mutation testing: do the tests catch bugs?

Coverage shows a line ran, not that a test would notice it breaking.
[mutmut](https://github.com/boxed/mutmut) plants small bugs ("mutants") in the
deterministic modules (an `<` turned into `<=`, a `150` into `151`, a branch
removed) and runs the tests against each one. Configuration: `setup.cfg`.

| Run | Killed | Survived | No test reached it |
|---|---:|---:|---:|
| First | 259 / 415 | 21 | 135 |
| Final | **406 / 414** | 8 | 0 |

The first run's survivors showed weaknesses in the tests, not just gaps:

- A fake clock starting at **0** hid a sign error, because `now − 0 = now + 0`.
- Every price test happened to have the marked price as the first number, so
  a parser that ignored "₹" still passed.
- No test summed one item across several rows.
- The limiter's memory cap and the 413 response body were never checked.

The 8 that remain are **equivalent mutants**: they can't change behaviour.
Examples: starting every running total at 1 instead of 0 shifts all totals
equally and the winner never changes; an upper-cased pattern under a
case-insensitive regex; `False` vs `None` for a flag. So every mutant that
*can* be killed is killed.

## 6. Evaluating the model itself

Every test above scripts Gemini's answers. That proves what the code does
*with* an answer, but not whether Gemini gives the right one.
`scripts/run_llm_eval.py` sends 89 labelled cases (`backend/evals/cases.json`)
to the real model, through the real routing and agent code:

- the intent router;
- the six small classifiers;
- the customer agent end to end, with the in-memory catalog.

The cases include Devanagari, English, typos, the "saree leni hai"
browsing-vs-buying trap, negations, and four prompt-injection attempts.

**Last run (`backend/evals/RESULTS.md`): 89 / 89 correct; all 4 injection
attempts held.** Every call was answered by the primary model,
`gemini-flash-lite-latest`.

Reading that result honestly:

- **A perfect score on a first run is a reason to look harder.** I read
  every customer-agent reply rather than trusting the judge. Each one was
  right: the real price, the refusal for a missing attribute, a clarifying
  question when "ye lena hai" had no referent, and the returns opener for a
  complaint.
- **In the injection case the model refused on its own.** It stated the real
  ₹599, so the output price guard never had to act. The guard is there for
  the run where the model does fall for it.
- **The cases were written by the same person as the prompts, and there is
  no held-out set.** 89 cases is a smoke test that catches regressions and
  gross failures; it is not an accuracy estimate. The next step is cases
  written from real conversation logs.
- **Latency:** for the first 67 single-decision calls, p50 was 1.36 s and
  p95 7.0 s (a few slow outliers). From about the 80th call on, single calls
  took 5–14 s with no errors reaching our code, which looks like free-tier
  throttling absorbed by retries inside the SDK. So the customer-agent
  numbers in `RESULTS.md` (2–3 calls each, all from that later stretch)
  overstate a normal turn. `scripts/measure_latency.py` measures real turns
  against the deployed backend (DEPLOY.md, step 5).

**When it runs.** It spends quota, so the results are pinned to a
fingerprint of everything that shapes model behaviour: the prompts and
routing code, the agents, the cases, and the model names (never the keys).

- A plain run with current results prints them and calls nothing.
- CI runs `--check`, which never calls Gemini and annotates the build with a
  warning when core logic has changed since the last evaluation.
- Re-run it once after such a change, not after every edit.

## 7. Not covered, and why

- **The real database and pgvector in CI.** Tests use fakes. The new SQL
  (session state, filtered search, duplicate-order index) was run on a real
  Postgres 17 with a stand-in for the vector type. pgvector-specific
  behaviour is unchanged from the original function and is not tested here.
  A CI job with a pgvector container is the next step.
- **The frontend.** No automated tests; it was checked by hand in a browser
  (separate sessions per tab, trace isolation, error messages).
- **Real Sarvam calls.** The voice layer is tested with fakes and real
  ffmpeg; Sarvam itself only through manual use.
- **Load.** Concurrency is tested for correctness, not throughput. Rate
  limits are per instance.
- **Eval size.** 89 cases is a smoke-level sample: a few misses move the
  percentages a lot, so treat them as indicators, not precise accuracy.
- **Known gaps written down as tests or notes:** "pichle mahine" (strict
  xfail); a price written as a bare number with no rupee word or price word
  is not checked by the output guard (`unit/test_prompt_safety.py`).
