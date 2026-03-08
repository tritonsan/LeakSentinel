from __future__ import annotations
from pathlib import Path
import argparse, numpy as np, matplotlib.pyplot as plt
import soundfile as sf

AUDIO_DIR = Path("data/audio/zone-1"); AUDIO_DIR.mkdir(parents=True, exist_ok=True)
SPEC_DIR = Path("data/spectrogram/zone-1"); SPEC_DIR.mkdir(parents=True, exist_ok=True)
GPLA_WAV_DIR = Path("data/audio/gpla12_wav")

def placeholder_wav(path: Path, seed: int, leak_like: bool):
    rng = np.random.default_rng(seed)
    sr=16000; dur=2.0
    t = np.linspace(0,dur,int(sr*dur),endpoint=False)
    sig = 0.05*np.sin(2*np.pi*120*t) + 0.02*rng.normal(size=t.shape)
    if leak_like:
        sig += 0.12*rng.normal(size=t.shape)
    sf.write(path, sig.astype(np.float32), sr)

def spectrogram(wav: Path, out_png: Path):
    sig, sr = sf.read(wav)
    plt.figure(figsize=(6.4,3.6))
    plt.specgram(sig, NFFT=512, Fs=sr, noverlap=256)
    plt.axis("off"); plt.tight_layout(pad=0)
    plt.savefig(out_png, dpi=100, bbox_inches="tight", pad_inches=0)
    plt.close()

def build_placeholders():
    wavs=[]
    for i in range(5):
        p=AUDIO_DIR/f"normal_{i:02d}.wav"; placeholder_wav(p,300+i,False); wavs.append(p)
    for i in range(5):
        p=AUDIO_DIR/f"leak_{i:02d}.wav"; placeholder_wav(p,400+i,True); wavs.append(p)
    for wav in wavs:
        spectrogram(wav, SPEC_DIR/(wav.stem+".png"))

def build_from_gpla12():
    if not GPLA_WAV_DIR.exists():
        raise SystemExit("Run scripts/download_gpla12.py first.")
    wavs=sorted(GPLA_WAV_DIR.glob("*.wav"))
    for wav in wavs:
        spectrogram(wav, SPEC_DIR/("gpla_"+wav.stem+".png"))

if __name__ == "__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--use_gpla12", action="store_true")
    args=ap.parse_args()
    build_from_gpla12() if args.use_gpla12 else build_placeholders()
    print("Spectrogram build complete.")
