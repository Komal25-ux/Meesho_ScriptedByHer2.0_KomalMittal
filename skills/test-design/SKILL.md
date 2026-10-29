---
name: test-design
description: How tests are designed, written and verified in Sakhi - risk first, named test-design techniques, fakes instead of patch stacks, every bug pinned by a regression test proven on the old code, mutation testing to measure the tests, and a fingerprinted evaluation for LLM decisions. Use whenever writing, reviewing or extending tests in this repository, by a person or an AI assistant.
---

# Test design for Sakhi

These are the rules the test suite in `backend/tests/` was built by, written
so that a person or an AI assistant follows the same method. `TESTING.md`
shows the result; this file is the process.

The human owns the risks, the decisions and the verification. An AI
assistant may draft cases and code at speed, but nothing it writes is
trusted until it passes the checks in step 6.

## 1. Start from risk, not from code

Before writing a test, write down what could go wrong for a real person and
rank it by harm. Money first (a wrong price, a lost or duplicate order),
then privacy (one user seeing another's data), then trust (a failure
presented as an answer), then everything else.

- Every risk in `TESTING.md` §1 names the test files that cover it.
- A test that guards no listed risk is either covering a risk that should
  be added to the table, or not worth keeping.

## 2. Test at the lowest level that can show the behaviour

| Level | Use it for | Stand-ins |
|---|---|---|
| `unit/` | a rule: a formula, a parser, a limit | none |
| `components/` | one agent or graph gate | `support/` fakes |
| `journeys/` | a conversation across several messages | `support/` fakes |
| `adapters/` | talking to Supabase, Gemini, audio | a fake of that SDK |
| `api/` | HTTP: status codes, validation, security | `support/` fakes |

Never test a pricing rule through HTTP, and never test "two tabs don't share
state" with a unit test.

## 3. Derive cases with a named technique

Cases come from a technique, not from inspiration. For every input, ask
which of these applies:

- **Equivalence classes**: group inputs that should behave the same; take
  one from each group, including the invalid groups. Price formats ₹599 /
  Rs.599 / 599/- / 5,999 are one class; "size 42" is the not-a-price class.
- **Boundary values**: bugs live at edges. For a limit L, test L-1, L and
  L+1. Price above cost: 499 / 500 / 501 with cost 500.
- **Decision tables**: when several conditions combine, write the table
  first (condition A × B → result) and make one test per row.
- **State transitions**: for any flow that waits for the next message
  (approval, picker, returns), list every state × every input → next state,
  including the transitions that must *not* happen.
- **Properties (Hypothesis)**: for rules that must hold for *every* input,
  state the rule and let Hypothesis search for a counter-example ("no cost
  ever yields less than ₹150 profit").
- **Negative and adversarial**: malformed IDs, path traversal, prompt
  injection, forged origins.
- **Fault injection**: the database or Gemini failing at each step.

Put the table or the boundary reasoning in the test file's docstring, so the
reader sees *why* each case exists.

## 4. Fakes, not patch stacks

- Agents run against `backend/tests/support/`: `ScriptedGemini`,
  `Classifiers` and `FakeSupabase`, installed by the `sakhi` fixture.
- Do not stack `patch("backend.x.y.z")` calls: they tie a test to import
  paths, so a refactor breaks tests that aren't about it.
- Assert **outcomes** (the row saved, the prompt sent, the reply returned),
  not which internal functions were called.

## 5. The quality bar for test code

- The name is a sentence about behaviour:
  `test_a_new_price_must_be_above_cost`, not `test_price_2`.
- One behaviour per test; parametrize for more inputs.
- No `or` in an assertion unless the rule itself is "either/or". An `or` is
  usually a test that doesn't know what it expects.
- No tautologies (a dict holds what was put in it) and no
  "the mock returned what the mock was told to return".
- No sleeps. Concurrency tests use events, so they are deterministic.
- Test data must not be able to hide a bug. Not zero (`now - 0 == now + 0`),
  not values where two rules agree, not ties unless the tie is the point.
- Comments explain *why* a case exists, never *what* the line does.
- A known limitation is a strict `xfail` with a reason, so it fails loudly
  the day it is fixed.

## 6. Prove the tests, don't assume them

A test that has never failed has not proven anything. Every change to the
suite goes through these checks, whoever wrote it:

1. **Run it against the old code.** A regression test must fail on the
   pre-fix code and pass on the fix (`git stash` the fix, or run against
   `git archive HEAD~1`).
2. **Mutation testing** (`mutmut run`, configured in `setup.cfg`). For every
   surviving mutant, decide: is the test weak (fix the test), or is the
   mutant equivalent (it cannot change behaviour; write down why)?
3. **Read the failure message.** A useful test fails with a message that
   points at the bug.
4. **Reference check.** Every test name cited in `TESTING.md` must exist.

## 7. LLM behaviour: scripted in tests, real in the evaluation

- Unit, component and journey tests script Gemini's answers. They prove
  what the code does *with* an answer.
- Whether Gemini gives the *right* answer is measured by
  `scripts/run_llm_eval.py` against labelled cases in
  `backend/evals/cases.json`.
- The eval spends real quota, so it runs once per change to core logic,
  never on every build. CI only runs `--check`.
- A perfect eval score is a reason to read the replies by hand, not to
  celebrate. Report sample size and bias honestly.

## 8. Every bug leaves two things behind

1. A regression test, named for the behaviour, that failed on the old code.
2. A row in the defects table in `TESTING.md` §4: what the defect was, how
   it was found, and the test that pins it.
