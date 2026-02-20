import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv("API key.env")

client = genai.Client()

response = client.models.generate_content(
    model='gemini-2.0-flash',
    contents='Hello there! This is a test of the Gemini audio generation capabilities using the python SDK.',
    config=types.GenerateContentConfig(
        response_modalities=["AUDIO"],
    )
)

print(response.model_version)
if getattr(response, 'inline_data', None):
    print("Found inline_data!")
    
for part in response.candidates[0].content.parts:
    if part.inline_data:
        print("Mime type:", part.inline_data.mime_type)
        with open("test_audio.wav", "wb") as f:
            f.write(part.inline_data.data)
        print("Saved test_audio.wav")
