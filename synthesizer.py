import sqlite3
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

from google import genai
from google.genai import types
from openai import OpenAI
from pydantic import BaseModel
from tenacity import retry, wait_exponential, stop_after_attempt

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load local API key
load_dotenv("API key.env")


class ExecutiveSummary(BaseModel):
    whats_new_today: str
    model_updates: str
    key_takeaways: str


def setup_database(cursor: sqlite3.Cursor):
    """Ensure the executive_summaries table exists with the proper schema."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS executive_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            whats_new_today TEXT,
            model_updates TEXT,
            key_takeaways TEXT,
            audio_path TEXT
        )
    """)


@retry(
    wait=wait_exponential(multiplier=2, min=4, max=65),
    stop=stop_after_attempt(6)
)
def generate_executive_report(client: genai.Client, raw_summaries: str) -> ExecutiveSummary:
    """Uses Gemini API to synthesize a single report from multiple summaries."""
    prompt_text = (
        "You are an expert AI industry analyst. "
        "Review the following collection of recent AI news summaries and synthesize them "
        "into a highly concise, executive-level report designed to be read in under 3 minutes.\n\n"
        "Please extract and construct the following three sections:\n"
        "1. What's new today: The most important general news and trends.\n"
        "2. Model and tooling updates: Specific releases, updates, or benchmarks of AI models and developer tools.\n"
        "   - CRITICAL: Limit this section to a MAXIMUM of 3 bullet points.\n"
        "   - CRITICAL: For each bullet point in this section, you MUST include a sub-bullet titled 'So what does this mean in plain English:' that explains the impact and provides potential industry applications for the change.\n"
        "3. Key takeaways: Actionable insights for professionals.\n\n"
        "CRITICAL FORMATTING INSTRUCTION: You MUST format the content of EVERYTHING strictly as markdown bulleted lists. "
        "Do not use dense paragraphs whatsoever. Every single item must be a bullet point.\n\n"
        f"Raw Summaries Batch:\n{raw_summaries}"
    )

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt_text,
        config=types.GenerateContentConfig(
            response_schema=ExecutiveSummary,
            response_mime_type="application/json",
            temperature=0.2, # Lower temperature for more analytical/factual output
        ),
    )
    
    if not response.parsed:
        raise ValueError("Failed to parse response from Gemini API")
        
    return response.parsed


@retry(
    wait=wait_exponential(multiplier=2, min=4, max=65),
    stop=stop_after_attempt(6)
)
def generate_podcast_script(client: genai.Client, raw_text: str) -> str:
    """Uses Gemini API to synthesize raw articles into a 3-minute podcast script."""
    prompt_text = (
        "You are an expert, engaging AI podcast host for 'AI Distillate'.\n"
        "Your task is to take the following raw AI news articles and write a highly engaging, "
        "conversational script that would take exactly 3 minutes to read out loud (about 450 words).\n\n"
        "The script should sound like a solo host talking directly to the listener in a natural, relaxed tone. "
        "Include natural conversational transitions (e.g., 'Now, shifting gears...', 'Interestingly...', 'Think about what this means...').\n"
        "CRITICAL: Do NOT include any speaker labels (like 'Host:' or 'Speaker 1:'), sound effect cues (like '[Intro music fades]'), or any text that isn't meant to be spoken out loud. Write ONLY the pure spoken text.\n"
        "Start with an energetic welcome framing this as the 'daily update' and dive straight into the top stories. Cover the macro trends, "
        "model updates, and actionable takeaways.\n\n"
        f"Raw Articles:\n{raw_text}"
    )

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt_text,
    )
    
    if not response.text:
        raise ValueError("Failed to generate podcast script from Gemini API")
        
    return response.text


def generate_audio(script_text: str, output_path: str = "podcast.mp3") -> str:
    """Uses OpenAI TTS to generate a highly natural human-like MP3 audio file."""
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set. Cannot generate natural audio.")
        
    openai_client = OpenAI(api_key=openai_api_key)
    
    response = openai_client.audio.speech.create(
        model="tts-1",
        voice="nova", # 'nova' is a very natural, engaging female voice.
        input=script_text
    )
    
    response.stream_to_file(output_path)
    return output_path


def synthesis_job(db_path: str = "articles.db"):
    """
    Reads processed articles, generates a synthesized report,
    and saves it to the executive_summaries table.
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        setup_database(cursor)
        
        # 1. Fetch all processed raw articles that haven't been synthesized yet
        try:
            cursor.execute("SELECT id, title, summary, raw_text FROM articles WHERE processed = 1 AND synthesized = 0")
            records = cursor.fetchall()
        except sqlite3.OperationalError:
            logger.error("Database table 'articles' does not exist.")
            return
            
        if not records:
            logger.info("No processed articles found to synthesize.")
            return
            
        logger.info(f"Synthesizing {len(records)} article summaries into an executive report...")
        
        # 2. Concatenate summaries for the text report, and raw text for the script
        aggregated_summaries = "\n\n".join([f"Title: {row['title']}\nSummary: {row['summary']}" for row in records])
        aggregated_raw_text = "\n\n".join([f"Title: {row['title']}\nContent: {row['raw_text']}" for row in records])
        
        if not aggregated_summaries.strip():
            logger.info("Aggregated text is empty. Skipping synthesis.")
            return
            
        # 3. Call LLM to generate the Executive Summary and Podcast Script
        client = genai.Client()
        try:
            logger.info("Generating text Executive Summary...")
            report_data = generate_executive_report(client, aggregated_summaries)
            
            logger.info("Generating 3-minute Podcast Script (from raw text)...")
            podcast_script = generate_podcast_script(client, aggregated_raw_text)
            
            logger.info("Generating Podcast MP3 Audio using OpenAI TTS...")
            audio_file_path = f"podcast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
            
            generate_audio(podcast_script, audio_file_path)
            logger.info(f"Audio saved to {audio_file_path}")
            
            # 4. Save everything to database
            cursor.execute(
                """
                INSERT INTO executive_summaries (whats_new_today, model_updates, key_takeaways, audio_path)
                VALUES (?, ?, ?, ?)
                """,
                (report_data.whats_new_today, report_data.model_updates, report_data.key_takeaways, audio_file_path)
            )
            
            # Mark the summarized articles as synthesized
            article_ids = [(row['id'],) for row in records]
            cursor.executemany("UPDATE articles SET synthesized = 1 WHERE id = ?", article_ids)
            
            conn.commit()
            logger.info("Successfully generated and saved new Executive Summary and Audio.")
            
        except Exception as e:
            logger.error(f"Failed to generate executive summary: {e}")
            conn.rollback()
            
    except sqlite3.Error as db_err:
        logger.error(f"Database error occurred: {db_err}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()


if __name__ == "__main__":
    logger.info("Starting synthesis pipeline...")
    synthesis_job()
