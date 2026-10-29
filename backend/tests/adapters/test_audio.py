import asyncio
import shutil
import wave

import pytest

from backend.core.vaani_audio import convert_to_wav

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")


def _write_wav(path, rate, channels, seconds=0.2):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * channels * int(rate * seconds))


@needs_ffmpeg
def test_convert_to_wav_produces_the_16khz_mono_pcm_that_saarika_expects(tmp_path):
    # A browser recording is typically 48 kHz stereo.
    source = tmp_path / "note.wav"
    _write_wav(source, rate=48000, channels=2)

    output = asyncio.run(convert_to_wav(str(source)))

    with wave.open(output, "rb") as w:
        assert w.getframerate() == 16000
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2


@needs_ffmpeg
def test_convert_to_wav_raises_on_a_file_that_is_not_audio(tmp_path):
    source = tmp_path / "note.webm"
    source.write_bytes(b"this is not a webm file")

    with pytest.raises(RuntimeError, match="ffmpeg exited"):
        asyncio.run(convert_to_wav(str(source)))


def _a_short_wav(path):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 1600)


def test_when_sarvam_is_unavailable_gemini_hears_the_audio_in_a_form_its_sdk_accepts(tmp_path, monkeypatch):
    # The old dict format ({"mime_type", "data"}) was rejected by google-genai,
    # so this fallback silently never worked.
    from google.genai import types
    from backend.core import vaani_audio

    wav = tmp_path / "note.wav"
    _a_short_wav(wav)
    sent = {}

    def gemini(parts):
        sent["parts"] = parts
        return "laal saree dikhao"

    monkeypatch.setattr(vaani_audio, "_get_sarvam_keys", lambda: [])
    monkeypatch.setattr(vaani_audio, "generate_with_fallback", gemini)

    assert asyncio.run(vaani_audio.transcribe_audio(str(wav))) == "laal saree dikhao"
    audio = sent["parts"][1]
    assert isinstance(audio, types.Part)
    assert (audio.inline_data.mime_type, audio.inline_data.data) == ("audio/wav", wav.read_bytes())


def test_when_no_speech_service_answers_the_transcript_is_empty(tmp_path, monkeypatch):
    from backend.core import vaani_audio

    wav = tmp_path / "note.wav"
    _a_short_wav(wav)
    monkeypatch.setattr(vaani_audio, "_get_sarvam_keys", lambda: [])
    monkeypatch.setattr(vaani_audio, "generate_with_fallback", lambda parts: None)

    assert asyncio.run(vaani_audio.transcribe_audio(str(wav))) == ""
