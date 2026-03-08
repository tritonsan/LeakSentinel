from __future__ import annotations

from pathlib import Path
import wave
import argparse
import numpy as np
import matplotlib.pyplot as plt


AUDIO_DIR = Path("data/audio/zone-1")
SPEC_DIR = Path("data/spectrogram/zone-1")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
SPEC_DIR.mkdir(parents=True, exist_ok=True)

GPLA_WAV_DIR = Path("data/audio/gpla12_wav")
GPLA_SPEC_DIR = Path("data/spectrogram/gpla12")


def _placeholder_wav(path: Path, seed: int, leak_like: bool) -> None:
    rng = np.random.default_rng(seed)
    sr = 16000
    dur = 2.0
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    sig = 0.05 * np.sin(2 * np.pi * 120 * t) + 0.02 * rng.normal(size=t.shape)
    if leak_like:
        sig += 0.12 * rng.normal(size=t.shape)
    # Write 16-bit PCM WAV using stdlib (avoids external deps like soundfile).
    pcm = np.clip(sig, -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm16.tobytes())


def _spectrogram(wav: Path, out_png: Path) -> None:
    with wave.open(str(wav), "rb") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
        sig16 = np.frombuffer(raw, dtype=np.int16)
        sig = (sig16.astype(np.float32) / 32767.0).clip(-1.0, 1.0)
    plt.figure(figsize=(6.4, 3.6))
    plt.specgram(sig, NFFT=512, Fs=sr, noverlap=256)
    plt.axis("off")
    plt.tight_layout(pad=0)
    plt.savefig(out_png, dpi=100, bbox_inches="tight", pad_inches=0)
    plt.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--use-gpla12", action="store_true", help="Build spectrograms from data/audio/gpla12_wav/*.wav")
    args = ap.parse_args()

    if args.use_gpla12:
        if not GPLA_WAV_DIR.exists():
            raise SystemExit("GPLA-12 wav dir missing. Run: python scripts/download_gpla12.py")
        GPLA_SPEC_DIR.mkdir(parents=True, exist_ok=True)
        wavs = sorted(GPLA_WAV_DIR.glob("*.wav"))
        if not wavs:
            raise SystemExit("No GPLA-12 wavs found. Run: python scripts/download_gpla12.py")
        for wav in wavs:
            _spectrogram(wav, GPLA_SPEC_DIR / (wav.stem + ".png"))
        print("GPLA-12 spectrogram build complete.")
        return

    wavs: list[Path] = []
    for i in range(5):
        p = AUDIO_DIR / f"normal_{i:02d}.wav"
        _placeholder_wav(p, 300 + i, False)
        wavs.append(p)
    for i in range(5):
        p = AUDIO_DIR / f"leak_{i:02d}.wav"
        _placeholder_wav(p, 400 + i, True)
        wavs.append(p)

    for wav in wavs:
        _spectrogram(wav, SPEC_DIR / (wav.stem + ".png"))

    print("Spectrogram build complete.")


if __name__ == "__main__":
    main()
