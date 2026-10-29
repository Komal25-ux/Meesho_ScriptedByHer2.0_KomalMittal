"""scripts/run_llm_eval.py, everything except the Gemini calls: it must not
spend quota unless core logic changed, and CI's --check must never spend it."""
import json

import pytest

import scripts.run_llm_eval as eval_runner


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A tiny stand-in project: one prompt file and a results file."""
    (tmp_path / "prompts.py").write_text("PROMPT = 'v1'\n")
    monkeypatch.setattr(eval_runner, "ROOT", tmp_path)
    monkeypatch.setattr(eval_runner, "FINGERPRINTED", ["prompts.py"])
    monkeypatch.setattr(eval_runner, "RESULTS", tmp_path / "results.json")
    monkeypatch.setattr(eval_runner, "REPORT", tmp_path / "RESULTS.md")

    def gemini_must_not_be_called(cases):
        raise AssertionError("the eval called Gemini")
    monkeypatch.setattr(eval_runner, "run_cases", gemini_must_not_be_called)
    return tmp_path


def record_results(project, fingerprint):
    (project / "results.json").write_text(json.dumps({"fingerprint": fingerprint}))
    (project / "RESULTS.md").write_text("# stored report\n")


def test_the_fingerprint_changes_when_a_prompt_changes(project):
    before = eval_runner.fingerprint()
    (project / "prompts.py").write_text("PROMPT = 'v2'\n")

    assert eval_runner.fingerprint() != before


def test_the_fingerprint_is_stable_when_nothing_changes(project):
    assert eval_runner.fingerprint() == eval_runner.fingerprint()


def test_the_fingerprint_changes_when_the_model_changes(project, monkeypatch):
    from backend.config import settings
    before = eval_runner.fingerprint()
    monkeypatch.setattr(settings, "GEMINI_MODEL", "some-other-model")

    assert eval_runner.fingerprint() != before


def test_the_fingerprint_does_not_depend_on_the_api_key(project, monkeypatch):
    from backend.config import settings
    before = eval_runner.fingerprint()
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "a-different-key")

    assert eval_runner.fingerprint() == before


def test_with_current_results_a_run_prints_them_instead_of_calling_gemini(project, capsys):
    record_results(project, eval_runner.fingerprint())

    assert eval_runner.main([]) == 0
    assert "not calling Gemini" in capsys.readouterr().out


def test_check_says_current_when_nothing_changed(project, capsys):
    record_results(project, eval_runner.fingerprint())

    eval_runner.main(["--check"])

    assert "current" in capsys.readouterr().out


@pytest.mark.parametrize("stored", [None, "an-old-fingerprint"])
def test_check_warns_when_stale_but_never_calls_gemini_or_fails(project, capsys, stored):
    if stored:
        record_results(project, stored)

    assert eval_runner.main(["--check"]) == 0
    assert capsys.readouterr().out.startswith("::warning title=LLM eval is stale::")


def test_the_summary_counts_accuracy_per_decision_and_injection_cases():
    rows = lambda *passed: [{"passed": p, "ms": 100, "tag": None} for p in passed]
    results = {"intent": rows(True, True, False, True), "approval": rows(True, False)}
    results["intent"][3]["tag"] = "injection"

    summary = eval_runner.summarize(results)

    assert summary["intent"]["accuracy"] == 0.75
    assert summary["_overall"] == {"cases": 6, "passed": 4, "accuracy": 0.667, "injection_cases_held": "1/1"}
