# Contenitore di raccolta: legge pagine ostili. Contiene solo il necessario:
# niente SQLAlchemy, niente portale, nessuna credenziale interna.
ARG IMMAGINE_PLAYWRIGHT=mcr.microsoft.com/playwright/python:v1.65.2-noble
FROM ${IMMAGINE_PLAYWRIGHT}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN --mount=type=secret,id=ca,required=false \
    if [ -s /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; \
    pip install --no-cache-dir --break-system-packages \
        'playwright==1.65.2' 'psycopg[binary]>=3.2' 'boto3>=1.34' 'tldextract>=5.1' 'pyyaml>=6.0' 'dnspython>=2.6' 'telethon>=1.36' 'scrapy>=2.11' 'scrapy-playwright>=0.0.40'
COPY core/__init__.py core/config.py core/collect_client.py core/storage.py core/domains.py core/
COPY collectors/__init__.py collectors/base.py collectors/terms.py collectors/pages.py collectors/
COPY config/giochi.yaml config/emoji.yaml config/
COPY probes probes
USER pwuser
CMD ["python", "-m", "probes.runner", "--sonda", "snapshot"]
