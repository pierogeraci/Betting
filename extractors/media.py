"""Estrazione dai file multimediali: fotogrammi, OCR, codici QR, loghi, trascrizione.

Gira nel contenitore `estrazione`, su rete separata: legge il file dal secchio di
lavorazione e scrive il risultato nel secchio di arrivo. Non esegue i file: li
decodifica con ffmpeg e con le librerie di immagini.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_FRAMES = 40
SCENE_THRESHOLD = 0.3
PHASH_DISTANCE = 6
OCR_MIN_CONFIDENCE = 0.6
LOGOS = Path(__file__).resolve().parent.parent / "config" / "loghi"
WHISPER_MODEL = os.environ.get("MODELLO_TRASCRIZIONE", "large-v3")
FFMPEG_TIMEOUT = 600


@dataclass
class Frame:
    time_ms: int
    image: Any  # PIL.Image
    phash: Any = None


@dataclass
class Result:
    items: list[dict[str, Any]] = field(default_factory=list)
    keyframes: list[tuple[str, bytes]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    info: dict[str, Any] = field(default_factory=dict)


def ffmpeg(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-protocol_whitelist",
            "file,pipe",
            *args,
        ],  # noqa: S603, S607 - binario fisso
        capture_output=True,
        timeout=FFMPEG_TIMEOUT,
        check=False,
    )


def scene_frames(video: Path, workdir: Path) -> list[Frame]:
    """Fotogrammi ai cambi di scena, più il primo; tempo in millisecondi da showinfo."""
    from PIL import Image

    pattern = workdir / "f_%04d.jpg"
    proc = subprocess.run(  # noqa: S603, S607
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-protocol_whitelist",
            "file",
            "-i",
            str(video),
            "-vf",
            f"select='eq(n,0)+gt(scene,{SCENE_THRESHOLD})',showinfo,scale='min(1280,iw)':-2",
            "-vsync",
            "vfr",
            "-frames:v",
            str(MAX_FRAMES * 3),
            str(pattern),
        ],
        capture_output=True,
        timeout=FFMPEG_TIMEOUT,
        check=False,
    )
    times = [
        int(float(line.split("pts_time:")[1].split()[0]) * 1000)
        for line in proc.stderr.decode("utf-8", "replace").splitlines()
        if "pts_time:" in line
    ]
    frames = []
    for i, path in enumerate(sorted(workdir.glob("f_*.jpg"))):
        frames.append(Frame(times[i] if i < len(times) else i * 1000, Image.open(path).convert("RGB")))
    return frames


def dedupe(frames: list[Frame], distance: int = PHASH_DISTANCE) -> list[Frame]:
    """Elimina i quasi duplicati con l'hash percettivo."""
    import imagehash

    kept: list[Frame] = []
    for frame in frames:
        frame.phash = imagehash.phash(frame.image)
        if all(frame.phash - k.phash > distance for k in kept):
            kept.append(frame)
        if len(kept) >= MAX_FRAMES:
            break
    return kept


_ocr = None


def ocr_engine():
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR

        _ocr = PaddleOCR(
            lang=os.environ.get("OCR_LINGUA", "it"),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    return _ocr


def ocr(image: Any) -> list[dict[str, Any]]:
    import numpy as np

    lines = []
    for page in ocr_engine().predict(np.array(image)):
        data = page.json.get("res", page.json) if hasattr(page, "json") else page
        for text, score, box in zip(
            data.get("rec_texts", []),
            data.get("rec_scores", []),
            data.get("rec_polys", data.get("dt_polys", [])),
            strict=False,
        ):
            if text.strip() and float(score) >= OCR_MIN_CONFIDENCE:
                lines.append(
                    {
                        "testo": text.strip(),
                        "confidenza": round(float(score), 3),
                        "riquadro": [list(map(int, p)) for p in box],
                    }
                )
    return lines


def qr_codes(image: Any) -> list[str]:
    import cv2
    import numpy as np

    detector = cv2.QRCodeDetector()
    array = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    try:
        ok, decoded, _, _ = detector.detectAndDecodeMulti(array)
    except cv2.error:
        return []
    return [d for d in (decoded if ok else []) if d]


def logo_matches(image: Any, min_matches: int = 25) -> list[dict[str, Any]]:
    """Loghi noti (cartella config/loghi) cercati per corrispondenza di punti ORB."""
    import cv2
    import numpy as np

    if not LOGOS.exists():
        return []
    orb = cv2.ORB_create(nfeatures=1500)
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    _, frame_desc = orb.detectAndCompute(gray, None)
    if frame_desc is None:
        return []
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    found = []
    for logo_path in sorted(LOGOS.glob("*.png")):
        logo = cv2.imread(str(logo_path), cv2.IMREAD_GRAYSCALE)
        if logo is None:
            continue
        _, logo_desc = orb.detectAndCompute(logo, None)
        if logo_desc is None:
            continue
        pairs = matcher.knnMatch(logo_desc, frame_desc, k=2)
        good = [m for m, n in (p for p in pairs if len(p) == 2) if m.distance < 0.75 * n.distance]
        if len(good) >= min_matches:
            found.append({"logo": logo_path.stem, "corrispondenze": len(good)})
    return found


def frame_items(frame: Frame) -> list[dict[str, Any]]:
    items = []
    lines = ocr(frame.image)
    if lines:
        items.append(
            {
                "tipo": "ocr",
                "testo": "\n".join(line["testo"] for line in lines),
                "inizio_ms": frame.time_ms,
                "modello": "PP-OCRv5",
                "metadati": {"righe": lines[:80]},
            }
        )
    for value in qr_codes(frame.image):
        items.append(
            {"tipo": "qr", "testo": value[:2000], "inizio_ms": frame.time_ms, "modello": "opencv-qr"}
        )
    for logo in logo_matches(frame.image):
        items.append(
            {
                "tipo": "logo",
                "testo": logo["logo"],
                "inizio_ms": frame.time_ms,
                "modello": "orb",
                "metadati": logo,
            }
        )
    return items


def transcribe(media: Path, translate: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from faster_whisper import WhisperModel

    model = WhisperModel(
        WHISPER_MODEL,
        device=os.environ.get("DISPOSITIVO", "auto"),
        compute_type=os.environ.get("PRECISIONE", "default"),
    )
    segments, info = model.transcribe(
        str(media), vad_filter=True, task="translate" if translate else "transcribe", beam_size=5
    )
    items = [
        {
            "tipo": "traduzione" if translate else "trascrizione",
            "testo": s.text.strip(),
            "inizio_ms": int(s.start * 1000),
            "fine_ms": int(s.end * 1000),
            "modello": f"faster-whisper {WHISPER_MODEL}",
            "metadati": {"lingua": info.language},
        }
        for s in segments
        if s.text.strip()
    ]
    return items, {
        "lingua": info.language,
        "probabilita_lingua": round(info.language_probability, 3),
        "durata_s": round(info.duration, 1),
    }


def has_audio(path: Path) -> bool:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(path),
        ],  # noqa: S603, S607
        capture_output=True,
        timeout=60,
        check=False,
    )
    return bool(proc.stdout.strip())


def keyframe_bytes(frame: Frame) -> bytes:
    buffer = io.BytesIO()
    thumb = frame.image.copy()
    thumb.thumbnail((640, 640))
    thumb.save(buffer, format="JPEG", quality=80)
    return buffer.getvalue()


PLAYLIST_MARKERS = (b"#EXTM3U", b"ffconcat", b"[playlist]", b"<?xml", b"<SMIL", b"<smil")


def is_playlist(data: bytes) -> bool:
    """Playlist e liste di concatenazione farebbero leggere a ffmpeg altri file o URL: si rifiutano."""
    head = data[:512].lstrip()
    return any(head.startswith(m) for m in PLAYLIST_MARKERS) or b"#EXT-X-" in head


def process(data: bytes, kind: str, translate: bool = False) -> Result:
    from PIL import Image

    result = Result()
    if kind in {"video", "audio"} and is_playlist(data):
        result.errors.append("Il file è una playlist o una lista di file, non un video: non elaborato")
        return result
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        source = work / "sorgente.bin"
        source.write_bytes(data)
        if kind == "immagine":
            try:
                image = Image.open(source).convert("RGB")
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"Immagine non leggibile: {type(exc).__name__}")
                return result
            image.thumbnail((2000, 2000))
            result.items += frame_items(Frame(0, image))
            return result
        if kind == "video":
            frames = dedupe(scene_frames(source, work))
            result.info["fotogrammi"] = len(frames)
            for i, frame in enumerate(frames):
                result.items += frame_items(frame)
                if i < 12:
                    result.keyframes.append((f"fotogramma_{frame.time_ms:08d}.jpg", keyframe_bytes(frame)))
        if kind in {"video", "audio"} and has_audio(source):
            audio = work / "audio.wav"
            proc = ffmpeg("-i", str(source), "-vn", "-ac", "1", "-ar", "16000", str(audio))
            if proc.returncode != 0 or not audio.exists():
                result.errors.append("Traccia audio non estraibile")
            else:
                items, info = transcribe(audio)
                result.items += items
                result.info["audio"] = info
                if translate and info.get("lingua") not in {"it", "en"}:
                    result.items += transcribe(audio, translate=True)[0]
    return result


def run_job(client: Any, job: Any) -> dict[str, Any]:
    """Lavoro `estrai_media`: legge dal secchio di lavorazione, scrive manifesto e fotogrammi nel secchio di arrivo."""
    key = str(job.payload.get("chiave", ""))
    kind = str(job.payload.get("tipo", ""))
    data = client.read_work(key)
    result = process(data, kind, translate=bool(job.payload.get("traduci")))
    manifest = {
        "esito": "riuscito",
        "media_id": job.payload.get("media_id"),
        "estrazioni": result.items,
        "errori": result.errors,
        "info": result.info,
        "fotogrammi": [],
    }
    import hashlib

    for name, blob in result.keyframes:
        client.upload(job.id, name, blob, "image/jpeg")
        manifest["fotogrammi"].append({"nome": name, "sha256": hashlib.sha256(blob).hexdigest()})
    client.upload(job.id, "manifesto.json", json.dumps(manifest).encode(), "application/json")
    return {"esito": "riuscito", "estrazioni": len(result.items)}
