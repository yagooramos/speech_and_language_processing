from pathlib import Path
import json
import wave

import numpy as np
import streamlit as st
from scipy.io import wavfile
from scipy.signal import resample_poly
from vosk import Model, KaldiRecognizer

BASE_DIR = Path(__file__).parent
TEMP_DIR = BASE_DIR / "temp"
MODEL_DIR = BASE_DIR / "models" / "vosk-model-small-en-us-0.15"
TEMP_DIR.mkdir(exist_ok=True)


@st.cache_resource
def load_model():
    if not MODEL_DIR.exists():
        raise FileNotFoundError(
            "Vosk model not found. Put 'vosk-model-small-en-us-0.15' inside the models folder."
        )
    return Model(str(MODEL_DIR))


def prepare_wav(uploaded_file) -> Path:
    """Save the uploaded WAV and convert it to 16 kHz mono PCM."""
    input_path = TEMP_DIR / uploaded_file.name
    input_path.write_bytes(uploaded_file.getbuffer())

    sample_rate, audio = wavfile.read(str(input_path))

    # Stereo -> mono
    if len(audio.shape) > 1:
        audio = audio.mean(axis=1)

    # Convert to float range -1..1
    if np.issubdtype(audio.dtype, np.integer):
        audio = audio.astype(np.float32) / np.iinfo(audio.dtype).max
    else:
        audio = audio.astype(np.float32)

    # Resample to 16 kHz if needed
    if sample_rate != 16000:
        audio = resample_poly(audio, 16000, sample_rate)
        sample_rate = 16000

    output_path = TEMP_DIR / "local_stt_ready.wav"
    audio_int16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    wavfile.write(str(output_path), sample_rate, audio_int16)
    return output_path


def transcribe_with_vosk(audio_path: Path) -> str:
    model = load_model()
    parts = []

    with wave.open(str(audio_path), "rb") as wf:
        recognizer = KaldiRecognizer(model, wf.getframerate())

        while True:
            data = wf.readframes(4000)
            if not data:
                break

            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                parts.append(result.get("text", ""))

        final_result = json.loads(recognizer.FinalResult())
        parts.append(final_result.get("text", ""))

    return " ".join(part for part in parts if part).strip()


st.set_page_config(page_title="Local STT", layout="centered")
st.title("01 - Local Speech to Text")
st.write("Upload an English WAV file and get an offline transcription with Vosk.")

uploaded_file = st.file_uploader("Upload WAV audio", type=["wav"])

if uploaded_file is not None:
    st.audio(uploaded_file)

    if st.button("Run local STT"):
        try:
            with st.spinner("Transcribing..."):
                ready_path = prepare_wav(uploaded_file)
                text = transcribe_with_vosk(ready_path)
            st.success("Done")
            st.text_area("Transcription", text, height=180)
        except Exception as e:
            st.error(f"Error: {e}")
