# -*- coding: utf-8 -*-
"""Tests for geoserv_processor.insights"""
import pytest
from geoserv_processor.insights import (
    KnowledgeEntry,
    KNOWLEDGE_BASE,
    search_knowledge,
    format_insights,
    InsightsEngine,
    _tokenise,
)


class TestTokenise:
    def test_lowercase(self):
        tokens = _tokenise("Hello World")
        assert "hello" in tokens
        assert "world" in tokens

    def test_strips_punctuation(self):
        tokens = _tokenise("100-year flood!")
        assert "100" in tokens
        assert "year" in tokens
        assert "flood" in tokens

    def test_filters_short(self):
        tokens = _tokenise("a b c de")
        assert "a" not in tokens
        assert "de" in tokens

class TestKnowledgeBase:
    def test_has_entries(self):
        assert len(KNOWLEDGE_BASE) >= 5

    def test_all_have_question_and_answer(self):
        for e in KNOWLEDGE_BASE:
            assert e.question
            assert e.answer

    def test_all_have_tags(self):
        for e in KNOWLEDGE_BASE:
            assert len(e.tags) > 0


class TestSearchKnowledge:
    def test_100_year_flood_query(self):
        results = search_knowledge("100 year flood return period", top_k=3)
        assert len(results) > 0
        assert any("100" in e.question or "return" in e.question.lower()
                   for e in results)

    def test_slr_query(self):
        results = search_knowledge("sea level rise NOAA scenario", top_k=3)
        assert len(results) > 0
        # At least one result should be about SLR
        assert any(any("slr" in t or "sea" in t for t in e.tags)
                   for e in results)

    def test_empty_query_returns_results(self):
        results = search_knowledge("", top_k=3)
        assert len(results) > 0

    def test_top_k_respected(self):
        results = search_knowledge("flood", top_k=2)
        assert len(results) <= 2

    def test_scores_populated(self):
        results = search_knowledge("dem elevation model", top_k=5)
        for r in results:
            assert r.score > 0

    def test_custom_knowledge_base(self):
        custom = [
            KnowledgeEntry(
                question="Custom question about turtles",
                answer="Turtles are reptiles.",
                tags=["turtle", "reptile"],
            )
        ]
        results = search_knowledge("turtle reptile", knowledge_base=custom)
        assert len(results) == 1
        assert "turtle" in results[0].question.lower()


class TestFormatInsights:
    def test_empty_list(self):
        msg = format_insights([])
        assert "No relevant" in msg

    def test_formats_entries(self):
        entries = search_knowledge("flood", top_k=2)
        text = format_insights(entries)
        assert "[1]" in text
        assert "Source:" in text

    def test_no_source(self):
        entries = search_knowledge("flood", top_k=1)
        text = format_insights(entries, show_source=False)
        assert "Source:" not in text

class TestInsightsEngine:
    def test_search_records_history(self):
        engine = InsightsEngine(top_k=2)
        engine.search("100 year flood")
        engine.search("sea level rise")
        assert len(engine.history) == 2

    def test_add_entry(self):
        engine = InsightsEngine()
        initial_size = len(engine.kb)
        engine.add_entry(KnowledgeEntry(
            question="New entry",
            answer="New answer.",
            tags=["new"],
        ))
        assert len(engine.kb) == initial_size + 1

    def test_format_returns_string(self):
        engine = InsightsEngine()
        result = engine.format("storm surge hurricane")
        assert isinstance(result, str)
        assert len(result) > 0
