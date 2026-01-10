"""
Unified Sentiment Analysis Module.

Provides consistent sentiment analysis across all pipeline components:
- Crawler (historical_crawler.py)
- Spark Streaming (spark_rt_pipeline.py)
- Spark Batch (batch_enhanced.py)
- Dashboard (app.py)

Uses VADER-inspired lexicon with 150+ weighted words.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional


# =============================================================================
# SENTIMENT LEXICON (VADER-Inspired)
# =============================================================================

SENTIMENT_LEXICON: Dict[str, float] = {
    # === STRONG POSITIVE (Score: 2.5-3.0) ===
    'excellent': 3.0, 'outstanding': 3.0, 'amazing': 2.8, 'incredible': 2.8,
    'fantastic': 2.8, 'wonderful': 2.8, 'superb': 2.8, 'exceptional': 2.8,
    'brilliant': 2.7, 'remarkable': 2.7, 'extraordinary': 2.7, 'magnificent': 2.7,
    'phenomenal': 2.6, 'terrific': 2.6, 'spectacular': 2.6, 'marvelous': 2.5,
    
    # === MODERATE POSITIVE (Score: 1.5-2.4) ===
    'great': 2.2, 'awesome': 2.2, 'perfect': 2.3, 'love': 2.1, 'loving': 2.0,
    'success': 2.0, 'successful': 2.0, 'win': 2.0, 'winner': 2.0, 'winning': 2.0,
    'surge': 2.0, 'soar': 2.0, 'soaring': 2.0, 'boom': 1.9, 'booming': 1.9,
    'breakthrough': 2.0, 'innovative': 1.8, 'revolutionary': 1.9,
    'thriving': 1.9, 'flourishing': 1.8, 'prosperous': 1.8, 'prosperity': 1.8,
    
    # === MILD POSITIVE (Score: 0.5-1.4) ===
    'good': 1.5, 'nice': 1.3, 'positive': 1.5, 'optimistic': 1.6, 'hopeful': 1.4,
    'improve': 1.4, 'improved': 1.4, 'improvement': 1.4, 'improving': 1.3,
    'growth': 1.5, 'growing': 1.3, 'grow': 1.2, 'gain': 1.4, 'gains': 1.4,
    'rise': 1.3, 'rising': 1.3, 'risen': 1.3, 'increase': 1.2, 'increasing': 1.2,
    'strong': 1.4, 'stronger': 1.5, 'strength': 1.4, 'upbeat': 1.3, 'bullish': 1.4,
    'recovery': 1.3, 'recover': 1.2, 'recovering': 1.2, 'rebound': 1.3,
    'advance': 1.2, 'advancing': 1.2, 'progress': 1.3, 'progressing': 1.2,
    'profit': 1.3, 'profits': 1.3, 'profitable': 1.4, 'benefit': 1.2, 'benefits': 1.2,
    'stable': 1.0, 'steady': 1.0, 'solid': 1.1, 'healthy': 1.3, 'better': 1.2,
    'boost': 1.3, 'boosted': 1.3, 'boosting': 1.2, 'favor': 1.1, 'favorable': 1.3,
    'confident': 1.3, 'confidence': 1.3, 'promising': 1.2, 'encouraged': 1.2,
    'exciting': 1.4, 'excited': 1.3, 'enthusiasm': 1.3, 'enthusiastic': 1.4,
    
    # === MILD NEGATIVE (Score: -0.5 to -1.4) ===
    'bad': -1.5, 'poor': -1.3, 'negative': -1.4, 'pessimistic': -1.5, 'worried': -1.2,
    'concern': -1.1, 'concerns': -1.1, 'concerned': -1.2, 'worry': -1.2, 'worries': -1.2,
    'uncertain': -1.1, 'uncertainty': -1.2, 'risk': -1.0, 'risky': -1.2, 'risks': -1.0,
    'decline': -1.4, 'declining': -1.3, 'declined': -1.4, 'decrease': -1.2,
    'fall': -1.3, 'falling': -1.3, 'fallen': -1.4, 'drop': -1.3, 'dropping': -1.3,
    'weak': -1.3, 'weaker': -1.4, 'weakness': -1.3, 'downbeat': -1.3, 'bearish': -1.4,
    'slow': -0.8, 'slower': -0.9, 'slowdown': -1.2, 'slowing': -1.0,
    'cut': -1.2, 'cuts': -1.2, 'cutting': -1.1, 'reduce': -1.0, 'reduced': -1.0,
    'pressure': -1.0, 'pressured': -1.1, 'struggle': -1.2, 'struggling': -1.3,
    'loss': -1.4, 'losses': -1.4, 'losing': -1.3, 'lose': -1.2, 'lost': -1.3,
    'disappoint': -1.3, 'disappointed': -1.4, 'disappointing': -1.4, 'disappointment': -1.4,
    
    # === MODERATE NEGATIVE (Score: -1.5 to -2.4) ===
    'crisis': -2.3, 'disaster': -2.4, 'catastrophe': -2.5, 'catastrophic': -2.5,
    'crash': -2.3, 'crashed': -2.4, 'crashing': -2.3, 'collapse': -2.4, 'collapsed': -2.5,
    'plunge': -2.2, 'plunging': -2.2, 'plunged': -2.3, 'slump': -2.0, 'slumping': -2.0,
    'fail': -2.0, 'failed': -2.1, 'failure': -2.2, 'failing': -2.0,
    'recession': -2.2, 'depression': -2.4, 'downturn': -1.8, 'meltdown': -2.3,
    'bankruptcy': -2.3, 'bankrupt': -2.4, 'default': -2.0, 'defaulted': -2.1,
    'panic': -2.1, 'panicking': -2.0, 'fear': -1.8, 'fearful': -1.9, 'fears': -1.7,
    'danger': -1.8, 'dangerous': -1.9, 'threat': -1.7, 'threatening': -1.8,
    
    # === STRONG NEGATIVE (Score: -2.5 to -3.0) ===
    'terrible': -2.8, 'horrible': -2.8, 'awful': -2.7, 'dreadful': -2.7,
    'devastating': -2.9, 'devastated': -2.8, 'destruction': -2.7, 'destructive': -2.6,
    'worst': -2.8, 'abysmal': -2.7, 'disastrous': -2.8,
    'tragic': -2.6, 'tragedy': -2.7, 'nightmare': -2.5, 'horror': -2.5,
}

INTENSIFIERS: Dict[str, float] = {
    'very': 1.3, 'extremely': 1.5, 'really': 1.2, 'absolutely': 1.4,
    'incredibly': 1.4, 'highly': 1.2, 'particularly': 1.1, 'especially': 1.2,
    'significantly': 1.3, 'substantially': 1.2, 'dramatically': 1.4,
    'sharply': 1.3, 'severely': 1.3, 'deeply': 1.2, 'strongly': 1.2,
}

NEGATORS: set = {
    'not', 'never', 'no', 'none', 'neither', 'nobody', 'nothing',
    "n't", "nt", 'cannot', "can't", "won't", "wouldn't", "couldn't",
    "shouldn't", "don't", "doesn't", "didn't", "isn't", "aren't", "wasn't"
}


# =============================================================================
# CORE SENTIMENT FUNCTIONS
# =============================================================================

def analyze_sentiment(text: Optional[str]) -> Dict[str, Any]:
    """
    Analyze sentiment of text using VADER-inspired lexicon.
    
    Features:
    - 150+ words with weighted sentiment scores
    - Handles intensifiers (very, extremely, really)
    - Handles negation (not, never, no)
    - Score range: -1 (most negative) to +1 (most positive)
    
    Args:
        text: Input text to analyze
        
    Returns:
        Dict with 'label' (pos/neu/neg) and 'polarity' (-1 to 1)
    """
    if not text:
        return {"label": "neu", "polarity": 0.0}
    
    tokens = re.findall(r"[A-Za-z']+", text.lower())
    if not tokens:
        return {"label": "neu", "polarity": 0.0}
    
    total_score = 0.0
    sentiment_words = 0
    
    i = 0
    while i < len(tokens):
        token = tokens[i]
        
        # Check for negation in previous 3 words
        is_negated = any(tokens[max(0, i-3):i].count(neg) for neg in NEGATORS)
        
        # Check for intensifier in previous 2 words
        intensifier = 1.0
        for j in range(max(0, i-2), i):
            if tokens[j] in INTENSIFIERS:
                intensifier = INTENSIFIERS[tokens[j]]
                break
        
        # Look up sentiment score
        if token in SENTIMENT_LEXICON:
            score = SENTIMENT_LEXICON[token] * intensifier
            if is_negated:
                score *= -0.5  # Negate but reduce magnitude
            total_score += score
            sentiment_words += 1
        
        i += 1
    
    # Normalize score to [-1, 1] range
    if sentiment_words > 0:
        polarity = total_score / (sentiment_words + 2)  # Dampen extreme values
    else:
        polarity = 0.0
    
    # Clamp to [-1, 1]
    polarity = max(min(polarity, 1.0), -1.0)
    
    # Determine label with thresholds
    if polarity > 0.1:
        label = "pos"
    elif polarity < -0.1:
        label = "neg"
    else:
        label = "neu"
    
    return {"label": label, "polarity": round(polarity, 4)}


def get_sentiment_score(text: Optional[str]) -> float:
    """
    Get sentiment polarity score only.
    
    Args:
        text: Input text
        
    Returns:
        Float between -1.0 and 1.0
    """
    return analyze_sentiment(text)["polarity"]


def get_sentiment_label(text: Optional[str]) -> str:
    """
    Get sentiment label only.
    
    Args:
        text: Input text
        
    Returns:
        String: 'pos', 'neu', or 'neg'
    """
    return analyze_sentiment(text)["label"]


def simple_sentiment_for_spark(text: str) -> Dict[str, Any]:
    """
    Wrapper for Spark UDF compatibility.
    Identical to analyze_sentiment but with explicit str type.
    """
    return analyze_sentiment(text)


# =============================================================================
# SIMPLE SENTIMENT (For Crawler Compatibility)
# =============================================================================

def simple_sentiment_label(text: Optional[str]) -> str:
    """
    Simple sentiment for crawler (returns 'positive', 'negative', 'neutral').
    
    Uses same lexicon but returns full word labels for MongoDB storage.
    """
    result = analyze_sentiment(text)
    label_map = {"pos": "positive", "neu": "neutral", "neg": "negative"}
    return label_map.get(result["label"], "neutral")


# =============================================================================
# VALIDATION
# =============================================================================

if __name__ == "__main__":
    # Self-test
    test_cases = [
        ("Markets surge with strong growth", "pos"),
        ("Stocks crash amid crisis fears", "neg"),
        ("Weather is cloudy today", "neu"),
        ("", "neu"),
        (None, "neu"),
    ]
    
    print("Sentiment Module Self-Test:")
    for text, expected in test_cases:
        result = analyze_sentiment(text)
        status = "✓" if result["label"] == expected else "✗"
        print(f"  {status} '{text[:40] if text else None}' -> {result}")
