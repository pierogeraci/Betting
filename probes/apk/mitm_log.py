"""Script di mitmproxy: registra solo metodo, indirizzo, codice e dimensione di ogni richiesta (nessun corpo)."""

import json
import os
import time

PATH = os.environ.get("FLUSSI_MITM", "/flussi/flussi.jsonl")


def response(flow):  # chiamata da mitmproxy
    with open(PATH, "a", encoding="utf-8") as handle:  # noqa: PTH123
        handle.write(
            json.dumps(
                {
                    "t": time.time(),
                    "metodo": flow.request.method,
                    "url": flow.request.pretty_url,
                    "codice": flow.response.status_code,
                    "byte": len(flow.response.raw_content or b""),
                }
            )
            + "\n"
        )
