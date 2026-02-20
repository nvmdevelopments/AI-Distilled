import urllib.request
import re
from youtube_transcript_api import YouTubeTranscriptApi

html = urllib.request.urlopen('https://www.youtube.com/@AIDailyBrief/videos').read().decode('utf-8')
video_ids = re.findall(r'"videoId":"([^"]+)"', html)
vids = list(set(video_ids))
print(f"Found {len(vids)} videos.")

if vids:
    vid = vids[1]  # Pick a random recent one
    print(f"Testing video ID: {vid}")
    try:
        transcript = YouTubeTranscriptApi.get_transcript(vid)
        text = ' '.join([t['text'] for t in transcript])
        print(f"Transcript length: {len(text)} characters")
        print(f"Preview: {text[:200]}...")
    except Exception as e:
        print(f"Error getting transcript: {e}")
