"""Voice-note uploads are written to disk under a name the server chooses."""
import io
import os

import pytest

from backend.tests.support.sessions import SESSION_A


@pytest.fixture
def ffmpeg_inputs(monkeypatch):
    """Stands in for ffmpeg: records the path it was asked to read and leaves
    a real .wav beside it, so cleanup can be checked."""
    seen = []

    async def convert(path):
        seen.append(path)
        with open(path + ".wav", "wb") as f:
            f.write(b"RIFF")
        return path + ".wav"

    monkeypatch.setattr("backend.api.chat_router.convert_to_wav", convert)
    return seen


def upload(api_client, filename, content=b"opus"):
    return api_client.post("/api/v1/chat/send", data={"session_id": SESSION_A},
                           files={"audio_file": (filename, io.BytesIO(content), "audio/webm")})


@pytest.mark.parametrize("filename", ["../../../main.py", "/etc/passwd", "..\\..\\main.py", "note.webm\x00.py"])
def test_a_path_in_the_client_filename_never_reaches_the_disk(api_client, ffmpeg_inputs, filename):
    from backend.api.chat_router import TEMP_DIR

    upload(api_client, filename)

    assert os.path.dirname(ffmpeg_inputs[0]) == TEMP_DIR
    assert os.path.splitext(ffmpeg_inputs[0])[1] == ".webm"


@pytest.mark.parametrize("filename, suffix", [
    ("note.webm", ".webm"), ("note.MP4", ".mp4"), ("note.m4a", ".m4a"), ("note.ogg", ".ogg"), ("note.wav", ".wav"),
    ("note.exe", ".webm"), ("note", ".webm"),
])
def test_only_a_known_audio_extension_is_kept(api_client, ffmpeg_inputs, filename, suffix):
    upload(api_client, filename)

    assert ffmpeg_inputs[0].endswith(suffix)


def test_two_uploads_with_the_same_name_never_share_a_file(api_client, ffmpeg_inputs):
    upload(api_client, "reseller_recording.webm")   # every browser sends this name
    upload(api_client, "reseller_recording.webm")

    assert len(set(ffmpeg_inputs)) == 2


def test_both_temp_files_are_removed_after_a_turn(api_client, ffmpeg_inputs):
    upload(api_client, "note.webm")

    assert not os.path.exists(ffmpeg_inputs[0]) and not os.path.exists(ffmpeg_inputs[0] + ".wav")


def test_both_temp_files_are_removed_even_when_transcription_fails(api_client, ffmpeg_inputs, monkeypatch):
    async def broken(path):
        raise RuntimeError("ASR down")
    monkeypatch.setattr("backend.api.chat_router.transcribe_audio", broken)

    assert upload(api_client, "note.webm").status_code == 500
    assert not os.path.exists(ffmpeg_inputs[0]) and not os.path.exists(ffmpeg_inputs[0] + ".wav")
