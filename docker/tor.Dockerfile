# Demone Tor usato come proxy SOCKS dal crawler e dagli snapshot dei siti .onion.
ARG IMMAGINE_DEBIAN=debian:bookworm-slim
FROM ${IMMAGINE_DEBIAN}
RUN --mount=type=secret,id=ca,required=false \
    apt-get update && apt-get install -y --no-install-recommends tor && rm -rf /var/lib/apt/lists/*
RUN printf 'SocksPort 0.0.0.0:9050\nSocksPolicy accept 172.16.0.0/12\nSocksPolicy accept 10.0.0.0/8\nSocksPolicy accept 192.168.0.0/16\nSocksPolicy reject *\nDataDirectory /var/lib/tor\nLog notice stdout\n' > /etc/tor/torrc
USER debian-tor
CMD ["tor", "-f", "/etc/tor/torrc"]
