# Portale, lavoratore interno e comandi di amministrazione. Rete interna.
ARG IMMAGINE_PYTHON=python:3.12-slim
FROM ${IMMAGINE_PYTHON}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY . .
# Il segreto `ca` è facoltativo: serve solo dietro un proxy che sostituisce i certificati.
RUN --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; \
    pip install --no-cache-dir -e '.[dev]'

RUN useradd --system --uid 10001 betting && chown -R betting /app
USER betting
CMD ["uvicorn", "console.app:app", "--host", "0.0.0.0", "--port", "8000"]
