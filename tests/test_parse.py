"""Entity parsing tests. Need a loaded database: POSTGRES_URL=... pytest tests/test_parse.py"""
from datetime import date

import pytest
import sqlalchemy as sa

from backend import retrieval
from backend.config import SA_DSN

pytestmark = pytest.mark.skipif(not SA_DSN, reason="needs a loaded database")


@pytest.fixture(scope="module")
def eng():
    return sa.create_engine(SA_DSN)


def names(f):
    return [n for _, n in f["players"]]


def test_alias_and_short_date(eng):
    f = retrieval.parse("How many points did SGA score on 4/8?", eng)
    assert names(f) == ["Shai Gilgeous-Alexander"]
    assert date(2025, 4, 8) in f["dates"]


def test_team_nickname_and_long_date(eng):
    f = retrieval.parse("Who won the Knicks vs Spurs game on December 25, 2024?", eng)
    assert set(f["teams"]) == {"NYK", "SAN"}
    assert f["dates"] == [date(2024, 12, 25)]


def test_holiday(eng):
    f = retrieval.parse("What games happened on Christmas?", eng)
    assert all((d.month, d.day) == (12, 25) for d in f["dates"]) and f["dates"]


def test_accents_and_surname(eng):
    plain = retrieval.parse("How did Luka Doncic do?", eng)["players"]
    accented = retrieval.parse("How did Luka Dončić do?", eng)["players"]
    assert plain and plain == accented
    assert "Chet Holmgren" in names(retrieval.parse("How did Holmgren play against the Lakers?", eng))


def test_team_word_is_not_a_player(eng):
    f = retrieval.parse("Did the Magic beat the Heat?", eng)
    assert f["players"] == [] and set(f["teams"]) == {"ORL", "MIA"}


def test_season(eng):
    assert retrieval.parse("Who led the 2024-25 season in assists?", eng)["season"] == "2024-25"
