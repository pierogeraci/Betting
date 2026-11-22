"""Collettori di profilazione del sito, uno per area.

L'elenco si carica solo quando serve: il contenitore di raccolta usa `collectors.base`
senza portarsi dietro i collettori.
"""


def __getattr__(name: str):
    if name == "ALL":
        from collectors import aziendali, identificazione, infrastruttura, offerta, pagamenti, titolo

        return [titolo, aziendali, pagamenti, identificazione, offerta, infrastruttura]
    raise AttributeError(name)
