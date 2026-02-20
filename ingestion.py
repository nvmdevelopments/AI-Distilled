import sqlite3
import time
import feedparser
import requests
import re
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import Dict
from youtube_transcript_api import YouTubeTranscriptApi

# Feeds configuration
FEEDS = [
    {"source": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"source": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/"},
    {"source": "AI News", "url": "https://www.artificialintelligence-news.com/feed/"},
    {"source": "The Verge AI", "url": "https://www.theverge.com/rss/artificial-intelligence/index.xml"},
    {"source": "Wired AI", "url": "https://www.wired.com/feed/tag/ai/latest/rss"},
    {"source": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
    {"source": "OpenAI Blog", "url": "https://openai.com/blog/rss.xml"},
    {"source": "Google Research", "url": "https://blog.research.google/feeds/posts/default?alt=rss"},
    {"source": "BAIR", "url": "https://bair.berkeley.edu/blog/feed.xml"},
    {"source": "AWS ML", "url": "https://aws.amazon.com/blogs/machine-learning/feed/"},
    {"source": "NVIDIA AI", "url": "https://blogs.nvidia.com/feed/"},
    {"source": "Microsoft Research", "url": "https://www.microsoft.com/en-us/research/feed/"},
    {"source": "ArXiv (cs.AI)", "url": "http://export.arxiv.org/rss/cs.AI"},
    {"source": "ArXiv (cs.LG)", "url": "http://export.arxiv.org/rss/cs.LG", "type": "rss"},
    {"source": "ArXiv (cs.CL)", "url": "http://export.arxiv.org/rss/cs.CL", "type": "rss"},
    {"source": "The AI Daily Brief", "url": "https://www.youtube.com/@AIDailyBrief/videos", "type": "youtube"}
]

DB_NAME = "articles.db"

def setup_database() -> None:
    """Sets up the SQLite database and the required table."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            raw_text TEXT,
            summary TEXT,
            industry_tag TEXT,
            audio_path TEXT,
            processed BOOLEAN NOT NULL DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_url_content(url: str) -> str:
    """Fetches the content of a URL with exponential backoff.
    Excludes certain content types that may not be raw HTML text, e.g. PDFs.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    return response.text

def extract_text_from_html(html_content: str) -> str:
    """Extracts raw text from HTML content using BeautifulSoup."""
    soup = BeautifulSoup(html_content, 'html.parser')
    for script_or_style in soup(["script", "style", "nav", "footer", "header"]):
        script_or_style.decompose()
    text = soup.get_text(separator=' ')
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    return '\n'.join(chunk for chunk in chunks if chunk)

def get_latest_youtube_videos(channel_url: str) -> list[str]:
    """Scrapes the YouTube channel videos page to extract recent video IDs."""
    try:
        html_content = fetch_url_content(channel_url)
        # Find all video IDs in the JS window structure
        video_ids = re.findall(r'"videoId":"([^"]+)"', html_content)
        
        # Deduplicate while preserving order
        unique_vids = []
        for vid in video_ids:
            if vid not in unique_vids:
                unique_vids.append(vid)
                
        return unique_vids[:5] # Return top 5 recent videos
    except Exception as e:
        print(f"  Error fetching YouTube videos for {channel_url}: {e}")
        return []


def process_feed(feed_config: Dict[str, str], conn: sqlite3.Connection) -> None:
    """Processes a single RSS feed or YouTube channel, and saves to DB."""
    source_name = feed_config['source']
    feed_url = feed_config['url']
    feed_type = feed_config.get('type', 'rss')
    
    print(f"Processing feed: {source_name} ({feed_type})")
    
    cursor = conn.cursor()

    if feed_type == 'youtube':
         video_ids = get_latest_youtube_videos(feed_url)
         for vid in video_ids:
             article_id = f"yt:{vid}"
             url = f"https://www.youtube.com/watch?v={vid}"
             title = f"YouTube Video {vid}" # We don't easily get the title from the regex
             
             # Check if already exists
             cursor.execute("SELECT 1 FROM articles WHERE id = ?", (article_id,))
             if cursor.fetchone():
                 print(f"  Skipping: '{url}' (Already exists)")
                 continue
                 
             try:
                 print(f"  Fetching transcript for: {url}")
                 # Fixed: Call get_transcript directly on the class correctly imported
                 transcript_list = YouTubeTranscriptApi.get_transcript(vid)
                 raw_text = ' '.join([t['text'] for t in transcript_list])
                 
                 # Set summary to the first chunk of text if needed initially
                 summary = raw_text[:500] + "..." if len(raw_text) > 500 else raw_text
                 
                 cursor.execute('''
                     INSERT INTO articles (id, source, title, url, raw_text, summary, industry_tag, processed)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                 ''', (article_id, source_name, title, url, raw_text, summary, None, False))
                 conn.commit()
                 print(f"  Saved: {url}")
             except Exception as e:
                 print(f"  Error processing YouTube video '{vid}': {e}")
                 conn.rollback()

    else:
        # Standard RSS Processing
        try:
            parsed_feed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"  Error parsing feed: {e}")
            return

        entries = parsed_feed.entries[:5]

        for entry in entries:
            title = entry.get('title', 'No Title')
            url = entry.get('link', '')
            summary = entry.get('summary', '')
            
            article_id = entry.get('id', url)
            
            audio_path = None
            if 'enclosures' in entry:
                for enc in entry.enclosures:
                    if 'audio' in enc.get('type', ''):
                        audio_path = enc.get('href', '')
                        break
            
            cursor.execute("SELECT 1 FROM articles WHERE id = ?", (article_id,))
            if cursor.fetchone():
                print(f"  Skipping: '{title}' (Already exists)")
                continue

            raw_text = summary
            
            if "ArXiv" not in source_name and audio_path is None:
                try:
                    print(f"  Fetching content for: {url}")
                    html_content = fetch_url_content(url)
                    extracted_text = extract_text_from_html(html_content)
                    if extracted_text:
                        raw_text = extracted_text
                except Exception as e:
                    print(f"  Failed to fetch content for {url}: {e}")

            try:
                cursor.execute('''
                    INSERT INTO articles (id, source, title, url, raw_text, summary, industry_tag, audio_path, processed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (article_id, source_name, title, url, raw_text, summary, None, audio_path, False))
                conn.commit()
                print(f"  Saved: {title}")
            except Exception as e:
                print(f"  Error saving '{title}': {e}")
                conn.rollback()

def main() -> None:
    """Main execution function."""
    print("Setting up database...")
    setup_database()
    
    conn = sqlite3.connect(DB_NAME)
    for feed in FEEDS:
        process_feed(feed, conn)
        time.sleep(1) # Add a small delay between feeds
        
    conn.close()
    print("Ingestion complete.")

if __name__ == "__main__":
    main()
