# Deploying Sakhi

Everything needed to put this version live, in the order to do it. Each step
says where to do it, what to type, and how to check it worked. Steps 1–3
must happen in this order; the rest follow the deploy.

The backend runs on **Render** (`sakhi-backend-cbmz.onrender.com`), the
frontend on **Vercel** (`meesho-sakhi-komal25.vercel.app`), the database on
**Supabase**.

---

## 1. Update the database (Supabase) — before anything else

The new backend needs a table and a function that don't exist yet. If the
code goes live first, every message fails with a 503.

1. Open the Supabase dashboard → your project → **SQL Editor** → **New query**.
2. Paste the **whole** of `backend/db/supabase_schema.sql` and press **Run**.
   It is safe to run again on a database that already has the older
   tables; every statement checks before it creates or alters anything.
3. Check it worked — run this in the same editor:

   ```sql
   SELECT
     to_regclass('public.session_state')                       AS conversation_state_table,
     to_regproc('public.match_products_filtered')              AS filtered_search_function,
     (SELECT count(*) FROM information_schema.columns
       WHERE table_name = 'orders'
         AND column_name IN ('session_id', 'client_message_id')) AS new_order_columns,
     to_regclass('public.orders_client_message_id_key')        AS duplicate_order_guard;
   ```

   Expected: `session_state`, `match_products_filtered`, `2`,
   `orders_client_message_id_key`. Any empty (`NULL`) cell means the script
   did not finish — scroll the editor's output for the error.

What it adds: `session_state` (conversation state that survives restarts),
`match_products_filtered` (category search done in the database), and two
columns plus a unique index on `orders` (no duplicate orders). Nothing
existing is removed or renamed, which is also what makes rollback safe
(step 7).

## 2. Set the backend's environment variables (Render)

Render dashboard → the `sakhi-backend` service → **Environment**.

| Variable | Value | Why |
|---|---|---|
| `ENVIRONMENT` | `production` | Currently `development`. In production the backend **refuses to start** without Supabase, instead of quietly serving demo data as if it were real. |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | already set | Must be present, or the service will not start (see above). |
| `GEMINI_API_KEY` (+ fallbacks), `SARVAM_API_KEY` (+ fallbacks) | already set | Unchanged. |
| `SESSION_STORE` | leave **unset** | Unset means "use the database". `memory` is refused in production. |
| `CORS_ORIGINS` | leave unset, unless the frontend moves | Defaults to the Vercel URL and localhost. If the site ever gets another domain, list it here (comma-separated) or the browser will block it. |

Then check **how Render starts the app** (Settings → *Build & Deploy*):

- **If it builds from the `Dockerfile`:** nothing to do — the Dockerfile now
  uses Python 3.13 and starts uvicorn with `--proxy-headers`.
- **If it is a native Python service with a Start Command:** change the start
  command to

  ```
  uvicorn backend.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips '*'
  ```

  and add the variable `PYTHON_VERSION` = `3.13.5`. Without
  `--proxy-headers` every visitor looks like Render's proxy, so the
  per-address rate limit would treat all users as one.

Don't redeploy yet — saving variables may trigger a deploy of the *old* code,
which is harmless (it ignores the new variables). The new code arrives in
step 3.

## 3. Merge and push the code

All the work is on the branch `production-hardening`. Pushing it to `main`
deploys both halves: Render rebuilds the backend, Vercel the frontend.

```bash
git checkout main
git merge --ff-only production-hardening
git push origin main
```

(Or open a pull request from `production-hardening` and merge it on GitHub;
CI runs the full test suite on the PR first.)

For a few minutes the two deploys finish at different times. A browser tab
that still has the old frontend loaded will get errors from the new backend
(it now requires a session id) — reloading the page fixes it.

## 4. Check the deploy

1. **Health:** open `https://sakhi-backend-cbmz.onrender.com/health`. Expect
   `"environment": "production"` and `"supabase": "connected"`. (The first
   request after the service has been idle can take ~30 s while Render wakes it.)
2. **Conversations are separate:** open the site in two browser tabs. Ask for
   a product in one; the other tab's *Orchestrator's Brain* panel must stay
   empty.
3. **State is stored:** after a message, Supabase → **Table Editor** →
   `session_state` should have rows.
4. **Timing is reported:** browser DevTools → *Network* → the `send` request →
   *Timing* tab shows `graph`, `tts` and `total` (from the `Server-Timing` header).
5. **CI is green**, including the step *"Check the LLM evaluation is current"*.
   A yellow warning there means prompts or routing changed since the last
   evaluation — see step 6.

If something fails, see **Troubleshooting** at the end.

## 5. Measure real latency (optional, spends quota)

Gives the p50/p95 numbers to quote, measured on the live system:

```bash
pip install -r requirements-dev.txt
python scripts/measure_latency.py https://sakhi-backend-cbmz.onrender.com --runs 2 --out latency.json
```

It sends 20 typed messages from fresh sessions (about 20 Gemini-backed turns
and 20 voice notes of Sarvam quota) and prints per-stage percentiles; the
first request's wake-up time is reported separately. Voice-note
transcription isn't included — check `asr` in the *Timing* tab after
sending a voice note.

## 6. Re-run the LLM evaluation — only when core logic changes

`backend/evals/RESULTS.md` holds the last evaluation of Gemini's decisions.
It only needs re-running when prompts, routing, agents, the cases or the
model names change — CI warns when that has happened. It spends about 110
Gemini calls:

```bash
python scripts/run_llm_eval.py
```

If nothing changed it prints the stored results and calls nothing.

## 7. Rolling back

The database changes only *add* things, so the previous code runs fine on
the new schema. To roll back, revert the merge on `main` and push:

```bash
git revert -m 1 <merge-commit>    # or: git revert <first>^..<last> for a fast-forward merge
git push origin main
```

No database rollback is needed. If you also want to undo the environment
change, set `ENVIRONMENT` back to `development` on Render.

## 8. Housekeeping (optional)

Conversation state expires after 24 hours (reads ignore expired rows), but
the rows stay in the table. To delete them nightly, enable the `pg_cron`
extension (Supabase → **Database** → *Extensions*), then run once:

```sql
SELECT cron.schedule('sakhi-expired-sessions', '0 3 * * *',
  $$DELETE FROM session_state WHERE expires_at < now()$$);
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Every chat message gets *"abhi server se connect nahi ho pa rahi hu"* (a 503); Render logs say `Reading session state failed` or `Supabase match_products failed` | Step 1 was skipped or failed | Run the schema file again and the check query |
| Render deploy crashes at startup with `refusing to start on mock data` | `ENVIRONMENT=production` but Supabase variables missing or wrong | Fix `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` |
| Browser console: *blocked by CORS policy* | The site is on a domain not in `CORS_ORIGINS` | Add it to `CORS_ORIGINS` on Render |
| Chat says *"bahut saare messages ek saath"* | Rate limit: 20 messages/min per tab, 60/min per address | Wait a minute; raise `RATE_LIMIT_*` on Render if real users hit it |
| Many users rate-limited together | Render passes every request as the proxy's address | Step 2: `--proxy-headers` in the start command |
| A voice note fails with *"voice note bahut lamba hai"* | Over the 6 MB request limit | Expected; raise `MAX_REQUEST_BYTES` if needed |
