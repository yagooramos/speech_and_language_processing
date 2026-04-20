from pathlib import Path
import time

import pyttsx3
import streamlit as st

BASE_DIR = Path(__file__).parent
TEMP_DIR = BASE_DIR / "temp"
TEMP_DIR.mkdir(exist_ok=True)


def local_tts(text: str) -> bytes:
    """Create a WAV file using the Windows offline voice."""
    output_path = TEMP_DIR / "local_tts.wav"
    if output_path.exists():
        output_path.unlink()

    engine = pyttsx3.init()
    engine.setProperty("rate", 170)

    voices = engine.getProperty("voices")
    if voices:
        engine.setProperty("voice", voices[0].id)

    engine.save_to_file(text, str(output_path))
    engine.runAndWait()
    engine.stop()

    # On Windows the file may appear a moment later.
    time.sleep(0.5)

    if not output_path.exists():
        raise RuntimeError("The local TTS file was not created.")

    return output_path.read_bytes()


st.set_page_config(page_title="Local TTS", layout="centered")
st.title("02 - Local Text to Speech")
st.write("Type English text and generate offline speech with pyttsx3.")

text = st.text_area(
    "Enter text",
    "Hello. This is a simple local text to speech demo.",
)

if st.button("Generate local TTS"):
    try:
        with st.spinner("Generating audio..."):
            audio_bytes = local_tts(text)
        st.success("Done")
        st.audio(audio_bytes, format="audio/wav")
    except Exception as e:
        st.error(f"Error: {e}")
