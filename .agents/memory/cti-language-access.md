---
name: Lingua e accesso della piattaforma CTI
description: Requisiti permanenti di lingua e accesso del prototipo CTI.
---

L’interfaccia CTI deve restare in italiano e usare Clerk per l’autenticazione; le autorizzazioni ai dati riservati vanno verificate lato server sui ruoli registrati.

**Why:** l’utente ha scelto di attivare autenticazione e ruoli dopo aver rilevato che il prototipo era aperto.

**How to apply:** mantenere UI, messaggi ed esportazioni in italiano. Le sessioni Clerk devono proteggere le API e i ruoli attivi devono governare l’accesso ai dati riservati; non fidarsi di ruoli inviati dal client.
