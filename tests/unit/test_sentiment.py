"""Unit tests for the unified sentiment module (jobs/utils/sentiment.py)."""

import sys
from pathlib import Path
import pytest

# Add jobs directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "jobs"))

from utils.sentiment import (
    analyze_sentiment,
    get_sentiment_score,
    get_sentiment_label,
    simple_sentiment_label,
    SENTIMENT_LEXICON,
    INTENSIFIERS,
    NEGATORS,
)


class TestAnalyzeSentiment:
    """Test cases for the main analyze_sentiment function."""

    def test_positive_sentiment(self):
        """Test positive sentiment detection."""
        result = analyze_sentiment("Markets surge with excellent growth")
        assert result["label"] == "pos"
        assert result["polarity"] > 0

    def test_negative_sentiment(self):
        """Test negative sentiment detection."""
        result = analyze_sentiment("Stocks crash amid terrible crisis")
        assert result["label"] == "neg"
        assert result["polarity"] < 0

    def test_neutral_sentiment(self):
        """Test neutral sentiment detection."""
        result = analyze_sentiment("The meeting is scheduled for 3 PM")
        assert result["label"] == "neu"
        assert -0.1 <= result["polarity"] <= 0.1

    def test_empty_text(self):
        """Test empty text returns neutral."""
        assert analyze_sentiment("")["label"] == "neu"
        assert analyze_sentiment("")["polarity"] == 0.0

    def test_none_text(self):
        """Test None input returns neutral."""
        assert analyze_sentiment(None)["label"] == "neu"
        assert analyze_sentiment(None)["polarity"] == 0.0

    def test_intensifier_boosts_score(self):
        """Test that intensifiers increase polarity magnitude."""
        normal = analyze_sentiment("This is good")
        intensified = analyze_sentiment("This is very good")
        assert abs(intensified["polarity"]) > abs(normal["polarity"])

    def test_negation_flips_sentiment(self):
        """Test that negation words flip sentiment."""
        positive = analyze_sentiment("This is great")
        negated = analyze_sentiment("This is not great")
        assert positive["polarity"] > 0
        assert negated["polarity"] < positive["polarity"]


class TestHelperFunctions:
    """Test helper functions."""

    def test_get_sentiment_score(self):
        """Test score-only function."""
        score = get_sentiment_score("Amazing wonderful news")
        assert isinstance(score, float)
        assert score > 0

    def test_get_sentiment_label(self):
        """Test label-only function."""
        label = get_sentiment_label("Terrible awful disaster")
        assert label == "neg"

    def test_simple_sentiment_label(self):
        """Test full-word label function for crawler."""
        assert simple_sentiment_label("Surge and growth") == "positive"
        assert simple_sentiment_label("Crash and crisis") == "negative"
        assert simple_sentiment_label("The weather today") == "neutral"


class TestLexicon:
    """Test lexicon structure."""

    def test_lexicon_has_positive_words(self):
        """Verify positive words exist."""
        positive_words = [w for w, s in SENTIMENT_LEXICON.items() if s > 0]
        assert len(positive_words) >= 50

    def test_lexicon_has_negative_words(self):
        """Verify negative words exist."""
        negative_words = [w for w, s in SENTIMENT_LEXICON.items() if s < 0]
        assert len(negative_words) >= 50

    def test_intensifiers_exist(self):
        """Verify intensifiers are defined."""
        assert "very" in INTENSIFIERS
        assert "extremely" in INTENSIFIERS
        assert len(INTENSIFIERS) >= 10

    def test_negators_exist(self):
        """Verify negators are defined."""
        assert "not" in NEGATORS
        assert "never" in NEGATORS
        assert len(NEGATORS) >= 10


class TestCategoryClassifier:
    """Test cases for category classification (unchanged)."""

    def test_technology_classification(self):
        """Test technology category detection."""
        keywords = ["technology", "software", "app", "digital", "computer"]
        text = "New software application launches with digital features"
        score = sum(1 for kw in keywords if kw in text.lower())
        assert score > 0

    def test_politics_classification(self):
        """Test politics category detection."""
        keywords = ["government", "election", "policy", "congress", "senate"]
        text = "The government announced new election policies"
        score = sum(1 for kw in keywords if kw in text.lower())
        assert score > 0
