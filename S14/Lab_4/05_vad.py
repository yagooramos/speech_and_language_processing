from pathlib import Path
import wave

import numpy as np
import streamlit as st
from scipy.io import wavfile
from scipy.signal import resample_poly
import webrtcvad

BASE_DIR = Path(__file__).parent
TEMP_DIR = BASE_DIR / "temp"
TEMP_DIR.mkdir(exist_ok=True)


def prepare_wav(uploaded_file) -> Path:
    """Save the uploaded WAV and convert it to 16 kHz mono PCM."""
    input_path = TEMP_DIR / uploaded_file.name
    input_path.write_bytes(uploaded_file.getbuffer())

    sample_rate, audio = wavfile.read(str(input_path))

    if len(audio.shape) > 1:
        audio = audio.mean(axis=1)

    if np.issubdtype(audio.dtype, np.integer):
        audio = audio.astype(np.float32) / np.iinfo(audio.dtype).max
    else:
        audio = audio.astype(np.float32)

    if sample_rate != 16000:
        audio = resample_poly(audio, 16000, sample_rate)
        sample_rate = 16000

    output_path = TEMP_DIR / "vad_ready.wav"
    audio_int16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    wavfile.write(str(output_path), sample_rate, audio_int16)
    return output_path


def detect_speech_segments(audio_path: Path, mode: int = 2, frame_ms: int = 30):
    """Return basic start/end times for speech segments."""
    vad = webrtcvad.Vad(mode)

    with wave.open(str(audio_path), "rb") as wf:
        sample_rate = wf.getframerate()
        pcm_data = wf.readframes(wf.getnframes())

    bytes_per_frame = int(sample_rate * frame_ms / 1000) * 2
    total_duration = len(pcm_data) / (sample_rate * 2)

    segments = []
    current_start = None

    for i in range(0, len(pcm_data), bytes_per_frame):
        frame = pcm_data[i:i + bytes_per_frame]
        if len(frame) < bytes_per_frame:
            break

        is_speech = vad.is_speech(frame, sample_rate)
        frame_start = i / (sample_rate * 2)

        if is_speech and current_start is None:
            current_start = frame_start
        elif not is_speech and current_start is not None:
            segments.append((current_start, frame_start))
            current_start = None

    if current_start is not None:
        segments.append((current_start, total_duration))

    return [
        {
            "start_sec": round(start, 2),
            "end_sec": round(end, 2),
            "duration_sec": round(end - start, 2),
        }
        for start, end in segments
    ]


st.set_page_config(page_title="VAD", layout="centered")
st.title("05 - Voice Activity Detection")
st.write("Upload an English WAV file and detect the parts that contain speech.")

uploaded_file = st.file_uploader("Upload WAV audio", type=["wav"])

if uploaded_file is not None:
    st.audio(uploaded_file)

    if st.button("Run VAD"):
        try:
            with st.spinner("Detecting speech..."):
                ready_path = prepare_wav(uploaded_file)
                segments = detect_speech_segments(ready_path)
            st.success("Done")

            if segments:
                st.table(segments)
            else:
                st.write("No speech segments were detected.")
        except Exception as e:
            st.error(f"Error: {e}")
