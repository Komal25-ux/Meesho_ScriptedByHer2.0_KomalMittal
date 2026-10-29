import pytest

from backend.api.timing import StageTimer
from scripts.measure_latency import parse_server_timing, percentile, summarize


class Clock:
    # Not zero: a clock starting at 0 hides a start-time sign error, because
    # now - 0 == now + 0. Mutation testing caught exactly that.
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_stage_timer_reports_each_stage_and_the_total():
    clock = Clock()
    timer = StageTimer(clock)
    with timer.stage("graph"):
        clock.now += 2.4314
    with timer.stage("tts"):
        clock.now += 0.9
    clock.now += 0.05  # time outside any stage still counts toward the total

    assert timer.header() == "graph;dur=2431, tts;dur=900, total;dur=3381"


def test_a_stage_that_raises_is_still_timed():
    clock = Clock()
    timer = StageTimer(clock)
    with pytest.raises(RuntimeError):
        with timer.stage("asr"):
            clock.now += 0.5
            raise RuntimeError("ASR down")

    assert timer.stages_ms == {"asr": 500.0}


@pytest.mark.parametrize("header, parsed", [
    ("graph;dur=2431, tts;dur=903, total;dur=3400", {"graph": 2431, "tts": 903, "total": 3400}),
    ("asr;dur=812.5", {"asr": 812.5}),
    ("", {}),
    ("graph, tts;desc=x", {}),
])
def test_parse_server_timing(header, parsed):
    assert parse_server_timing(header) == parsed


@pytest.mark.parametrize("values, q, expected", [
    ([7], 50, 7), ([7], 95, 7),                     # one sample is every percentile
    (list(range(1, 21)), 95, 19),                   # 20 samples: p95 is the 19th
    (list(range(1, 21)), 50, 10),
    (list(range(1, 21)), 100, 20),
    (list(range(1, 21)), 0, 1),
    ([3, 1, 2], 50, 2),                             # order of input doesn't matter
])
def test_percentile_is_nearest_rank(values, q, expected):
    assert percentile(values, q) == expected


def test_percentile_of_nothing_is_an_error():
    with pytest.raises(ValueError):
        percentile([], 95)


def test_summarize_counts_each_stage_from_the_samples_that_have_it():
    summary = summarize([{"graph": 100, "tts": 50}, {"graph": 300}])

    assert summary["graph"]["n"] == 2 and summary["graph"]["max"] == 300
    assert summary["tts"]["n"] == 1
