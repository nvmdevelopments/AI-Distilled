import streamlit as st
import pandas as pd
import sqlite3
import os
import streamlit.components.v1 as components

# Configuration
DB_PATH = "articles.db"

# Page setup
st.set_page_config(
    page_title="AI Distillate Feed",
    page_icon="📰",
    layout="centered"
)


@st.cache_data(ttl=60) # Cache the function's return value for 60 seconds
def load_data():
    """Connect to the database and retrieve processed articles."""
    try:
        conn = sqlite3.connect(DB_PATH)
        # Query only processed rows
        query = "SELECT * FROM articles WHERE processed = 1"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except sqlite3.Error as e:
        st.error(f"Database error: {e}")
        return pd.DataFrame() # Return empty DataFrame on error
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_executive_summary():
    """Retrieve the latest executive summary from the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        query = "SELECT * FROM executive_summaries ORDER BY generated_at DESC LIMIT 1"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except sqlite3.Error:
        # Table might not exist yet or other DB error
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading executive summary: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def load_all_executive_summaries():
    """Retrieve all historical executive summaries from the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        query = "SELECT * FROM executive_summaries ORDER BY generated_at DESC"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

def display_countdown_timer():
    """Injects a live Javascript timer counting down to the next 11:00 UTC."""
    timer_html = """
    <div style="font-family: sans-serif; text-align: center; padding: 12px; background-color: #1e1e24; color: #ffffff; border-radius: 8px; border: 1px solid #333333; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        <span style="font-size: 1.1em; font-weight: 500;">Next Autonomous Update: </span>
        <span id="countdown" style="font-family: monospace; font-size: 1.25em; font-weight: bold; color: #00ffcc;">Calculating...</span>
    </div>
    <script>
        function updateTimer() {
            const now = new Date();
            let nextUpdate = new Date();
            // Set to exactly 15:15:00 UTC (8:15 AM MST)
            nextUpdate.setUTCHours(15, 15, 0, 0);
            
            // If it's already past 11:00 UTC today, the next update is tomorrow
            if (now > nextUpdate) {
                nextUpdate.setUTCDate(nextUpdate.getUTCDate() + 1);
            }
            
            const diff = nextUpdate - now;
            const hours = Math.floor(diff / (1000 * 60 * 60));
            const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
            const seconds = Math.floor((diff % (1000 * 60)) / 1000);
            
            document.getElementById("countdown").innerText = 
                hours.toString().padStart(2, '0') + "h " + 
                minutes.toString().padStart(2, '0') + "m " + 
                seconds.toString().padStart(2, '0') + "s";
        }
        setInterval(updateTimer, 1000);
        updateTimer();
    </script>
    """
    components.html(timer_html, height=80)


def main():
    st.title("📰 AI Distillate News Feed")
    st.markdown("A highly synthesized executive overview of automated AI news.")

    # Display Live Update Timer
    display_countdown_timer()
    
    # Load data
    df = load_data()
    exec_summary_df = load_executive_summary()

    if df.empty:
        st.warning("No processed articles found in the database. Run the ingestion and distillation pipelines first.")
        return

    # Setup tabs
    tab1, tab2, tab3 = st.tabs(["🚀 Executive Summary", "📋 Raw Source Feed", "🗄️ Archive"])

    # --- TAB 1: Executive Summary ---
    with tab1:
        if not exec_summary_df.empty:
            summary_row = exec_summary_df.iloc[0]
            generated_at = summary_row.get('generated_at', 'Unknown time')
            
            st.caption(f"Last Generated: {generated_at}")
            
            audio_path = summary_row.get('audio_path')
            if pd.notna(audio_path) and isinstance(audio_path, str):
                if os.path.exists(audio_path):
                    with open(audio_path, 'rb') as f:
                        audio_bytes = f.read()
                    st.audio(audio_bytes, format="audio/mp3")
                else:
                    st.warning("Audio file not found on disk.")
            
            st.header("1. What's new today")
            st.write(summary_row.get('whats_new_today', 'No data.'))
            st.divider()
            
            st.header("2. The AI Daily Brief Summary")
            st.write(summary_row.get('daily_brief_summary', 'No data.'))
            st.divider()
            
            st.header("3. Key Takeaways")
            st.write(summary_row.get('key_takeaways', 'No data.'))
        else:
            st.info("No Executive Summary generated yet. Please run the `synthesizer.py` pipeline.")

    # --- TAB 2: Raw Source Feed ---
    with tab2:
        # Sidebar filtering (Only relevant for Raw Feed)
        st.sidebar.header("Filter Source Feed")
        
        # Get unique industry tags for the multiselect
        unique_tags = sorted([tag for tag in df['industry_tag'].unique() if pd.notna(tag)])
        
        selected_tags = st.sidebar.multiselect(
            "Select Industry Tags:",
            options=unique_tags,
            default=[] 
        )

        if selected_tags:
            filtered_df = df[df['industry_tag'].isin(selected_tags)]
        else:
            filtered_df = df

        st.sidebar.markdown(f"**Showing {len(filtered_df)} of {len(df)} raw articles.**")

        if filtered_df.empty:
             st.info("No articles match the selected filters.")
        else:
             for index, row in filtered_df.iterrows():
                 with st.container():
                     title = row.get('title', 'Untitled')
                     url = row.get('url', '#')
                     st.subheader(f"[{title}]({url})")

                     tag = row.get('industry_tag', 'Uncategorized')
                     st.caption(f"Tag: {tag}")

                     summary = row.get('summary', 'No summary available.')
                     st.markdown(summary)

                     audio_path = row.get('audio_path')
                     if pd.notna(audio_path) and isinstance(audio_path, str):
                         if os.path.exists(audio_path):
                             with open(audio_path, 'rb') as f:
                                 st.audio(f.read(), format="audio/mp3")
                     
                     st.markdown("---")

    # --- TAB 3: Archive ---
    with tab3:
        st.header("Historical Archive")
        st.markdown("Explore past editions of the AI Distillate feed.")
        all_summaries_df = load_all_executive_summaries()
        
        if all_summaries_df.empty:
            st.info("No historical data available yet.")
        else:
            # We skip the very first one since it's the current 'live' one shown in Tab 1
            # But the user asked for an archive, so showing all of them or skipping the latest is an option.
            # Let's show all of them.
            for index, row in all_summaries_df.iterrows():
                gen_date = row.get('generated_at', 'Unknown time')
                
                # Create an expander (clickable date) that reveals the content
                with st.expander(f"📅 Daily Update: {gen_date}"):
                    a_path = row.get('audio_path')
                    if pd.notna(a_path) and isinstance(a_path, str):
                        if os.path.exists(a_path):
                            with open(a_path, 'rb') as f:
                                st.audio(f.read(), format="audio/mp3")
                        else:
                            st.caption("(Audio file not found for this archive entry)")
                    
                    st.subheader("1. What's new today")
                    st.write(row.get('whats_new_today', 'No data.'))
                    st.divider()
                    
                    st.subheader("2. The AI Daily Brief Summary")
                    st.write(row.get('daily_brief_summary', 'No data.'))
                    st.divider()
                    
                    st.subheader("3. Key Takeaways")
                    st.write(row.get('key_takeaways', 'No data.'))

if __name__ == "__main__":
    main()
