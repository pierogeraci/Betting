# Estrazione multimediale: ffmpeg, PaddleOCR PP-OCRv5, faster-whisper, OpenCV.
# Legge i file dal secchio di lavorazione e scrive nel secchio di arrivo: nessun
# accesso alle tabelle, nessuna esecuzione dei file, solo decodifica.
ARG IMMAGINE_PYTHON=python:3.12-slim
FROM ${IMMAGINE_PYTHON}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 HF_HOME=/modelli PADDLE_HOME=/modelli/paddle PADDLEX_HOME=/modelli/paddlex
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
RUN --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; \
    pip install --no-cache-dir 'paddlepaddle>=3.0' 'paddleocr>=3.0' 'faster-whisper>=1.1' 'opencv-python-headless>=4.9' \
        'imagehash>=4.3' 'pillow>=10' 'numpy<3' 'psycopg[binary]>=3.2' 'boto3>=1.34' 'tldextract>=5.1' 'pyyaml>=6.0'
WORKDIR /app
COPY core/__init__.py core/config.py core/collect_client.py core/storage.py core/domains.py core/
COPY extractors/__init__.py extractors/media.py extractors/
COPY probes/__init__.py probes/runner.py probes/
COPY config/loghi config/loghi
RUN useradd --system --uid 10002 estrazione && mkdir -p /modelli && chown estrazione /modelli
USER estrazione
CMD ["python", "-m", "probes.runner", "--sonda", "estrazione"]
