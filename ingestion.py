import sqlite3
import time
import feedparser
import requests
import re
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential
from typing import Dict
import youtube_transcript_api
from datetime import datetime, timezone
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional

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

class ArticleSchema(BaseModel):
    id: str
    source: str
    title: str = Field(min_length=1)
    url: HttpUrl
    raw_text: str
    summary: str
    published_at: str # ISO Format
    audio_path: Optional[str] = None
    
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
            published_at TEXT,
            processed BOOLEAN NOT NULL DEFAULT 0,
            synthesized BOOLEAN NOT NULL DEFAULT 0
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
         video_ids.reverse() # Insert oldest first so highest rowid = newest
         for vid in video_ids:
             article_id = f"yt:{vid}"
             url = f"https://www.youtube.com/watch?v={vid}"
             
             # Fetch the video page to extract the real title
             try:
                 video_html = fetch_url_content(url)
                 title_match = re.search(r'<title>(.*?)</title>', video_html)
                 title = title_match.group(1).replace(' - YouTube', '') if title_match else f"YouTube Video {vid}"
                 pub_match = re.search(r'"publishDate":"([^"]+)"', video_html)
                 published_at = pub_match.group(1) if pub_match else datetime.now(timezone.utc).isoformat()
             except Exception:
                 title = f"YouTube Video {vid}"
                 published_at = datetime.now(timezone.utc).isoformat()
             
             # Check if already exists
             cursor.execute("SELECT 1 FROM articles WHERE id = ?", (article_id,))
             if cursor.fetchone():
                 print(f"  Skipping: '{title}' (Already exists)")
                 continue
                 
             try:
                 print(f"  Fetching transcript for: {url}")
                 
                 api = youtube_transcript_api.YouTubeTranscriptApi()
                 transcript_list = api.list(vid)
                 transcript = transcript_list.find_transcript(['en'])
                 raw_text = ' '.join([t.text for t in transcript.fetch() if hasattr(t, 'text')])
                 
                 # Set summary to the first chunk of text if needed initially
                 summary = raw_text[:500] + "..." if len(raw_text) > 500 else raw_text
                 
                 # Validate strictly with Pydantic
                 validated_article = ArticleSchema(
                     id=article_id,
                     source=source_name,
                     title=title,
                     url=url,
                     raw_text=raw_text,
                     summary=summary,
                     published_at=published_at
                 )
                 
                 cursor.execute('''
                     INSERT INTO articles (id, source, title, url, raw_text, summary, industry_tag, published_at, processed)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                 ''', (validated_article.id, validated_article.source, validated_article.title, str(validated_article.url), validated_article.raw_text, validated_article.summary, None, validated_article.published_at, False))
                 conn.commit()
                 print(f"  Saved: {title}")
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
        # Reverse to insert oldest first so the newest article gets the highest rowid
        entries.reverse()

        for entry in entries:
            title = entry.get('title', 'No Title')
            url = entry.get('link', '')
            summary = entry.get('summary', '')
            
            article_id = entry.get('id', url)
            
            
            published_at = datetime.now(timezone.utc).isoformat()
            if 'published_parsed' in entry and entry.published_parsed:
                t = entry.published_parsed
                published_at = datetime(t[0], t[1], t[2], t[3], t[4], t[5], tzinfo=timezone.utc).isoformat()
            elif 'updated_parsed' in entry and entry.updated_parsed:
                t = entry.updated_parsed
                published_at = datetime(t[0], t[1], t[2], t[3], t[4], t[5], tzinfo=timezone.utc).isoformat()
                
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
                # Pydantic rigorous validation wrapper
                validated_article = ArticleSchema(
                    id=article_id,
                    source=source_name,
                    title=title,
                    url=url,
                    raw_text=raw_text,
                    summary=summary,
                    published_at=published_at,
                    audio_path=audio_path
                )
                
                cursor.execute('''
                    INSERT INTO articles (id, source, title, url, raw_text, summary, industry_tag, audio_path, published_at, processed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (validated_article.id, validated_article.source, validated_article.title, str(validated_article.url), validated_article.raw_text, validated_article.summary, None, validated_article.audio_path, validated_article.published_at, False))
                conn.commit()
                print(f"  Saved: {title}")
            except Exception as e:
                print(f"  Error validating or saving '{title}': {e}")
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
