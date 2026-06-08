"""
End-to-end smoke test without a browser.

Reads a WAV file, streams it through a TranscriptionSession in chunks that
mimic real-time audio delivery, and prints every event. Pass --fake-asr to
skip model loading when you just want to sanity-check the event plumbing.

Usage:
    uv run python scripts/smoke.py path/to/audio.wav
    uv run python scripts/smoke.py --fake-asr --synth
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hugorm.asr.fake import FakeASR  # noqa: E402
from hugorm.events import TranscriptEvent  # noqa: E402
from hugorm.pipeline.session import SessionConfig, TranscriptionSession  # noqa: E402


def load_wav(path: Path, target_sr: int) -> np.ndarray:
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if sr != target_sr:
        from scipy.signal import resample_poly

        g = np.gcd(sr, target_sr)
        mono = resample_poly(mono, target_sr // g, sr // g).astype(np.float32)
    return mono


def synth_audio(target_sr: int, seconds: float = 6.0) -> np.ndarray:
    t = np.linspace(0, seconds, int(target_sr * seconds), endpoint=False, dtype=np.float32)
    return 0.1 * np.sin(2 * np.pi * 440 * t).astype(np.float32)


async def run(path: Path | None, use_fake_asr: bool, synth: bool) -> None:
    if use_fake_asr:
        asr = FakeASR()
    else:
        from hugorm.asr.faster_whisper import FasterWhisperBackend

        asr = FasterWhisperBackend(
            model_size=os.environ.get("HUGORM_ASR_MODEL", "base"),
            device=os.environ.get("HUGORM_DEVICE", "auto"),
            compute_type=os.environ.get("HUGORM_COMPUTE_TYPE", "auto"),
        )

    diarizer = None
    hf_token = os.environ.get("HUGORM_HF_TOKEN")
    if hf_token and not use_fake_asr:
        from hugorm.diarization.pyannote import PyannoteDiarizer

        diarizer = PyannoteDiarizer(hf_token=hf_token)

    async def emit(event: TranscriptEvent) -> None:
        print(json.dumps(json.loads(event.model_dump_json()), indent=None))

    session = TranscriptionSession(
        asr=asr, diarizer=diarizer, emit=emit, config=SessionConfig()
    )
    await session.start()

    pcm = synth_audio(asr.sample_rate) if synth or path is None else load_wav(path, asr.sample_rate)
    print(f"# feeding {len(pcm) / asr.sample_rate:.2f}s of audio", file=sys.stderr)

    step = int(asr.sample_rate * 0.1)  # 100 ms at a time
    for i in range(0, len(pcm), step):
        await session.push_pcm(pcm[i : i + step])
        await asyncio.sleep(0.01)

    await session.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", nargs="?", type=Path, help="WAV file to transcribe")
    ap.add_argument("--fake-asr", action="store_true", help="use FakeASR (no model load)")
    ap.add_argument("--synth", action="store_true", help="use a synthetic sine wave")
    args = ap.parse_args()
    if args.audio is None and not args.synth:
        ap.error("either provide an audio path or pass --synth")
    asyncio.run(run(args.audio, args.fake_asr, args.synth))


if __name__ == "__main__":
    main()
