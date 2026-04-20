from pathlib import Path
import os

from dotenv import load_dotenv
from groq import Groq
import streamlit as st

load_dotenv()

BASE_DIR = Path(__file__).parent
TEMP_DIR = BASE_DIR / "temp"
TEMP_DIR.mkdir(exist_ok=True)


def api_tts(text: str) -> bytes:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is missing in the .env file.")

    client = Groq(api_key=api_key)
    output_path = TEMP_DIR / "api_tts.wav"

    response = client.audio.speech.create(
        model="canopylabs/orpheus-v1-english",
        voice="troy",
        input=text,
        response_format="wav",
    )
    response.write_to_file(str(output_path))
    return output_path.read_bytes()


st.set_page_config(page_title="API TTS", layout="centered")
st.title("04 - External API Text to Speech")
st.write("Type English text and generate speech with the Groq API.")

if not os.getenv("GROQ_API_KEY"):
    st.warning("GROQ_API_KEY is not set, so this app will fail until you add it.")

text = st.text_area(
    "Enter text",
    "Hello. This is a simple external API text to speech demo.",
)

if st.button("Generate API TTS"):
    try:
        with st.spinner("Calling API..."):
            audio_bytes = api_tts(text)
        st.success("Done")
        st.audio(audio_bytes, format="audio/wav")
    except Exception as e:
        st.error(f"Error: {e}")
