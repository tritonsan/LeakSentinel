from __future__ import annotations
"""Download GPLA-12 public dataset from GitHub (best-effort) and convert to WAV.

Source repo: https://github.com/Deep-AI-Application-DAIP/acoustic-leakage-dataset-GPLA-12
Zip: https://github.com/Deep-AI-Application-DAIP/acoustic-leakage-dataset-GPLA-12/archive/refs/heads/main.zip
"""
import argparse, shutil, zipfile
from pathlib import Path
from urllib.request import urlretrieve
import numpy as np
import soundfile as sf
from scipy.io import loadmat

DATA = Path("data")
CACHE = DATA/"_cache"; CACHE.mkdir(parents=True, exist_ok=True)
OUT = DATA/"audio"/"gpla12_wav"; OUT.mkdir(parents=True, exist_ok=True)
ZIP_URL = "https://github.com/Deep-AI-Application-DAIP/acoustic-leakage-dataset-GPLA-12/archive/refs/heads/main.zip"

def to_wav(sig: np.ndarray, out: Path, sr: int):
    sig = np.asarray(sig).reshape(-1).astype(np.float32)
    mx = float(np.max(np.abs(sig))) if sig.size else 1.0
    if mx > 1.0: sig = sig/mx
    sf.write(out, sig, sr)

def convert(p: Path, sr: int) -> bool:
    ext=p.suffix.lower()
    out=OUT/(p.stem.replace(' ','_').replace('-','_') + ".wav")
    if ext==".wav":
        shutil.copy2(p,out); return True
    if ext==".npy":
        to_wav(np.load(p), out, sr); return True
    if ext in [".csv",".txt"]:
        arr=np.loadtxt(p, delimiter="," if ext==".csv" else None)
        to_wav(arr, out, sr); return True
    if ext==".mat":
        mat=loadmat(p)
        for k,v in mat.items():
            if k.startswith("__"): continue
            if isinstance(v,np.ndarray) and np.issubdtype(v.dtype,np.number) and v.size>100:
                to_wav(v, out, sr); return True
    return False

def main(version: str, max_files: int, sr: int):
    zpath=CACHE/"gpla12_main.zip"
    if not zpath.exists():
        print("Downloading", ZIP_URL)
        urlretrieve(ZIP_URL, zpath)
    tmp=CACHE/"gpla12_repo"
    if tmp.exists(): shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath,"r") as z: z.extractall(tmp)
    root=next(tmp.glob("acoustic-leakage-dataset-GPLA-12-*"))
    data_root=root/"data"
    # pick data_v* folder
    cand = sorted(data_root.glob("data_v*"))
    data_dir = cand[-1] if cand else data_root
    files=[p for p in data_dir.rglob("*") if p.is_file() and p.suffix.lower() in {".wav",".npy",".csv",".txt",".mat"}]
    files=sorted(files)[:max_files]
    ok=0
    for p in files:
        ok += 1 if convert(p,sr) else 0
    print(f"Produced {ok} wav files in {OUT}")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--version", default="v3")
    ap.add_argument("--max_files", type=int, default=20)
    ap.add_argument("--sr", type=int, default=16000)
    args=ap.parse_args()
    main(args.version, args.max_files, args.sr)
