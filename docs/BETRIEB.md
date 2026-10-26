# Betrieb — Upload-Strecke

*Stand 2026-10-25. Genau die Schritte, die bei der Verifikation tatsächlich gelaufen sind.*

## Auf einen Server bringen (Docker Compose)

Getestet mit genau diesen Dateien (`deploy/`): am 2026-10-25 lokal (Arm, Chrome-Durchlauf,
208-MB-Video), am 2026-10-26 **auf einem echten Server** (Hetzner CPX12, x86, Ubuntu 26.04,
Docker 29.9): Build, Start, echtes Let's-Encrypt-Zertifikat über Caddy, Test-Uploads
(neu / identisch / neu kodierte Kopie / ohne Ton / Vorschau). Datenbank und Backend-Port
sind von außen nicht erreichbar.

1. **Server anlegen** (Hetzner Cloud Console): Ubuntu 24.04, Standort Nürnberg, Typ
   **CPX12** (1 vCPU, 2 GB RAM, 40 GB SSD; 11,49 €/Monat + 0,50 € IPv4, jeweils netto,
   dazu MwSt.). Gemessen am laufenden Stack: alle vier Container zusammen ~0,35 GB RAM,
   Frontend-Build in der Spitze ~0,35 GB, Images ~2,7 GB auf der Platte. Der kleinere
   CPX02 (1 GB, 20 GB) wäre zu knapp, besonders die Platte; CPX22 (19,49 €) bräuchten wir
   nicht. Später wächst man über Server-Upgrade oder ein Volume. SSH-Key hinterlegen.
   **Backups einschalten** (+20 %), bevor echte Uploads kommen: Der Server hält die einzige
   Kopie jedes Uploads, bis ein Admin ihn registriert. Danach einmal Swap anlegen (Puffer
   beim Image-Build, Standardbefehle, auf Hetzner nicht getestet):
   `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab`
2. **Domain**: A-Record auf die IPv4 des Servers setzen.
   *Vorläufig, solange der Projektname nicht feststeht:* kostenlos über duckdns.org (Login
   mit Google/GitHub, Namen wählen, Server-IP eintragen) und `DOMAIN=<name>.duckdns.org`.
   Nicht sslip.io/nip.io: beide stehen nicht auf der Public Suffix List und teilen sich
   das Let's-Encrypt-Limit mit allen Nutzern weltweit, das Zertifikat kann scheitern.
   Mit der echten Domain: `DOMAIN` in `.env` ändern, `docker compose up -d` — Daten
   bleiben, nur der Link ändert sich (den Brüdern neu geben). Ungetestet auf einem Server.
3. **Auf dem Server:**
   ```bash
   curl -fsSL https://get.docker.com | sh
   git clone https://github.com/PSchmitz-Valckenberg/masdar.git /opt/maqati3 && cd /opt/maqati3/deploy
   cat > .env <<EOF
   DOMAIN=archiv.example.org
   POSTGRES_PASSWORD=$(openssl rand -hex 24)
   UPLOAD_KEY=$(openssl rand -base64 24 | tr '+/' '-_' | tr -d '=')
   EOF
   docker compose up -d --build
   ```
   Caddy holt das HTTPS-Zertifikat selbst, sobald die Domain auf den Server zeigt.
4. **Firewall** (Hetzner Console): nur 22, 80, 443 eingehend.
5. **Aktualisieren**: `git pull && docker compose up -d --build` — Migrationen laufen
   beim Start mit.

## Einstellungen (Backend)

| Variable | Pflicht | Bedeutung |
|---|---|---|
| `DATABASE_URL` | ja | setzt `deploy/compose.yml` selbst |
| `UPLOAD_KEY` | ja | Der Schlüssel im Upload-Link. Ohne ihn startet der Server nicht. Ändern = alle alten Links ungültig. |
| `STAGING_DIR` | nein | Wo Uploads liegen, bis ein Admin sie registriert. Im Container `/var/lib/maqati3/staging` auf dem Volume `staging`. |
| `MAX_UPLOAD_BYTES` | nein | Standard 2 GiB je Datei (Caddy lässt bis 2 GB durch) |
| `FPCALC_PATH` | nein | Standard `fpcalc` (im Image enthalten) |

`.env.example` sollte diese Schlüssel aufnehmen — offen, weil die Datei für Claude per
Einstellung gesperrt ist.

## Ohne Docker (Entwicklung)

```bash
cd backend
uv run python -m maqati3 migrate && uv run python -m maqati3 seed
UPLOAD_KEY=dev uv run python -m maqati3 serve --port 8000
cd frontend && npm run dev   # leitet /api an :8000 weiter (API_ORIGIN, beim Build eingebacken)
```

Braucht lokal `fpcalc` (`brew install chromaprint`) und ein Postgres 17 mit pgvector.

## Der Link für die Brüder

```
https://<domain>/ar/upload#k=<UPLOAD_KEY>
```

(`/en/` bzw. `/de/` für die anderen Sprachen.) Der Schlüssel steht hinter `#` und
erreicht deshalb nie Server-Logs oder Referrer. Nur in der Gruppe teilen.

## Für den Admin

```bash
ssh root@<IP>                                      # ggf. -i <dein Schlüssel>
cd /opt/maqati3/deploy && docker compose exec api python -m maqati3 inbox
```

listet abgeschickte Uploads mit Datei, Gelehrtem, Selbsteinschätzung, Quelle — und
markiert die, die **trotz Treffer** behalten wurden: beide anhören, bevor registriert wird.
Das Registrieren als Eintrag (ID vergeben, Zuschreibung festlegen) ist noch nicht gebaut.
