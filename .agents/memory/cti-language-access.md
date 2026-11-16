---
name: Lingua e accesso della piattaforma CTI
description: Requisiti permanenti di lingua e accesso del prototipo CTI.
---

L’interfaccia CTI deve restare in italiano e usare autenticazione locale con ID utente e password; le autorizzazioni ai dati riservati vanno verificate lato server sui ruoli registrati.

**Why:** l’utente ha richiesto accessi locali con credenziali proprie e autorizzazioni basate sui ruoli.

**How to apply:** mantenere UI, messaggi ed esportazioni in italiano. Le sessioni locali devono proteggere le API e i ruoli attivi devono governare l’accesso ai dati riservati; non fidarsi di ruoli inviati dal client.
