from pathlib import Path
import os

from dotenv import load_dotenv
from groq import Groq
import streamlit as st

load_dotenv()

BASE_DIR = Path(__file__).parent
TEMP_DIR = BASE_DIR / "temp"
TEMP_DIR.mkdir(exist_ok=True)


def api_stt(uploaded_file) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is missing.")

    client = Groq(api_key=api_key)
    audio_path = TEMP_DIR / uploaded_file.name
    audio_path.write_bytes(uploaded_file.getbuffer())

    with open(audio_path, "rb") as audio_file:
        result = client.audio.transcriptions.create(
            file=audio_file,
            model="whisper-large-v3-turbo",
            language="en",
            temperature=0.0,
        )

    return result.text


st.set_page_config(page_title="API STT", layout="centered")
st.title("03 - External API Speech to Text")
st.write("Upload an English WAV file and transcribe it with the Groq API.")

if not os.getenv("GROQ_API_KEY"):
    st.warning("GROQ_API_KEY is not set, so this app will fail until you add it.")

uploaded_file = st.file_uploader("Upload WAV audio", type=["wav"])

if uploaded_file is not None:
    st.audio(uploaded_file)

    if st.button("Run API STT"):
        try:
            with st.spinner("Calling API..."):
                text = api_stt(uploaded_file)
            st.success("Done")
            st.text_area("Transcription", text, height=180)
        except Exception as e:
            st.error(f"Error: {e}")
