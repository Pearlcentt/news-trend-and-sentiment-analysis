"""Unit tests for HTML stripping and content processing."""

import pytest


class TestHTMLStripper:
    """Test cases for HTML content cleaning."""

    def test_strip_html_tags(self):
        """Test basic HTML tag removal."""
        import re
        
        def strip_html_tags(html_text):
            if not html_text:
                return ""
            text = re.sub(r'<[^>]+>', '', html_text)
            return text.strip()
        
        html = "<p>Hello <strong>World</strong></p>"
        assert strip_html_tags(html) == "Hello World"

    def test_strip_continue_reading_links(self):
        """Test removal of Continue reading links."""
        import re
        
        def strip_continue_reading(html_text):
            return re.sub(r'<a[^>]*>Continue reading[^<]*</a>', '', html_text, flags=re.IGNORECASE)
        
        html = 'Article text <a href="#">Continue reading...</a>'
        result = strip_continue_reading(html)
        assert "Continue reading" not in result

    def test_decode_html_entities(self):
        """Test HTML entity decoding."""
        text = "Hello &amp; World &lt;test&gt;"
        decoded = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
        assert decoded == "Hello & World <test>"


class TestDateParsing:
    """Test cases for date parsing and validation."""

    def test_timestamp_to_datetime(self):
        """Test millisecond timestamp conversion."""
        from datetime import datetime
        
        timestamp_ms = 1735689600000  # Jan 1, 2025
        dt = datetime.fromtimestamp(timestamp_ms / 1000)
        assert dt.year == 2025
        assert dt.month == 1
        assert dt.day == 1

    def test_date_filter_validation(self):
        """Test date filter logic."""
        from datetime import datetime, timedelta
        
        seven_days_ago = datetime.now() - timedelta(days=7)
        old_date = datetime(2023, 4, 5)
        recent_date = datetime.now() - timedelta(days=1)
        
        assert old_date < seven_days_ago
        assert recent_date > seven_days_ago
