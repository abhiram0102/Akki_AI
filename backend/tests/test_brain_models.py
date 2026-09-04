"""Structural tests for the brain crawl-state models — no live DB required."""
from backend.models import BrainVisitedPage, BrainFrontier, BrainDeadLetter, BrainStats


def test_brain_visited_page_columns():
    cols = {c.name for c in BrainVisitedPage.__table__.columns}
    assert cols == {"url", "concept", "source_type", "sentences_learned", "visited_at"}
    assert BrainVisitedPage.__table__.columns["url"].primary_key


def test_brain_frontier_columns():
    cols = {c.name for c in BrainFrontier.__table__.columns}
    assert cols == {"url", "concept", "source_type", "discovered_at"}
    assert BrainFrontier.__table__.columns["url"].primary_key


def test_brain_dead_letter_columns():
    cols = {c.name for c in BrainDeadLetter.__table__.columns}
    assert cols == {"url", "source_type", "error", "attempts", "last_attempt_at"}
    assert BrainDeadLetter.__table__.columns["url"].primary_key


def test_brain_stats_columns():
    cols = {c.name for c in BrainStats.__table__.columns}
    assert cols == {"id", "total_pages", "total_sentences", "updated_at"}
    assert BrainStats.__table__.columns["id"].primary_key
