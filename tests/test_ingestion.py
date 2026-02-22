import pytest
import sqlite3
import datetime
import os
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

# Import from our application code
from ingestion import extract_text_from_html, get_latest_youtube_videos

# --- Unit Tests for Ingestion Logic ---

def test_extract_text_from_html():
    """Test that BeautifulSoup properly strips out JS, CSS, and navigation elements."""
    mock_html = '''
    <html>
        <head>
            <title>Test Page</title>
            <style>body { color: red; }</style>
        </head>
        <body>
            <nav>Skip me</nav>
            <header>Site Header</header>
            <div class="content">
                <p>This is the actual article content.</p>
                <p>It has multiple lines.</p>
            </div>
            <footer>Copyright 2026</footer>
            <script>console.log("Ignore script");</script>
        </body>
    </html>
    '''
    
    extracted_text = extract_text_from_html(mock_html)
    
    assert "This is the actual article content." in extracted_text
    assert "It has multiple lines." in extracted_text
    
    # Should be stripped
    assert "Skip me" not in extracted_text
    assert "Ignore script" not in extracted_text
    assert "body { color: red; }" not in extracted_text


@patch('ingestion.fetch_url_content')
def test_get_latest_youtube_videos(mock_fetch):
    """Test that the regex correctly scrapes YouTube IDs from the channel string."""
    mock_fetch.return_value = '''
    <script nonce="test">var ytInitialData = {"contents":{"twoColumnBrowseResultsRenderer":{"tabs":[{"tabRenderer":{"title":"Videos","content":{"richGridRenderer":{"contents":[{"richItemRenderer":{"content":{"videoRenderer":{"videoId":"TEST_VID_1"}}}},{"richItemRenderer":{"content":{"videoRenderer":{"videoId":"TEST_VID_2"}}}},{"richItemRenderer":{"content":{"videoRenderer":{"videoId":"TEST_VID_1"}}}}]}}}}]}}};</script>
    '''
    
    video_ids = get_latest_youtube_videos("https://fake_channel.com")
    
    # Needs to deduce ordering and deduplicate
    assert len(video_ids) == 2
    assert video_ids[0] == "TEST_VID_1"
    assert video_ids[1] == "TEST_VID_2"
