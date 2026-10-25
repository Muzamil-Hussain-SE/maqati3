# Betrieb — Upload-Strecke

*Stand 2026-10-25. Genau die Schritte, die bei der Verifikation tatsächlich gelaufen sind.*

## Auf einen Server bringen (Docker Compose)

Getestet am 2026-10-25 lokal mit genau diesen Dateien (`deploy/`): Stack startet,
Migrationen und Seed laufen beim Start, Upload über Caddy inkl. 208-MB-Video, Browser-
Durchlauf in Chrome. **Auf einem echten Server noch nicht gelaufen.**

1. **Server anlegen** (Hetzner Cloud Console): Ubuntu 24.04, Standort Deutschland,
   Typ CX33 (4 vCPU, 8 GB, 80 GB) — oder CAX21 (Arm), falls CX nicht buchbar ist; die
   Images bauen auf dem Server selbst, Arm geht. SSH-Key hinterlegen. **Backups
   einschalten** (+20 %): Der Server hält die einzige Kopie jedes Uploads, bis ein Admin
   ihn registriert.
2. **Domain**: A-Record auf die IPv4 des Servers setzen.
3. **Auf dem Server:**
   ```bash
   curl -fsSL https://get.docker.com | sh
   git clone https://github.com/PSchmitz-Valckenberg/masdar.git && cd masdar/deploy
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
| `STAGING_DIR` | nein | Wo Uploads liegen, bis ein Admin sie registriert. Im Container `/var/lib/masdar/staging` auf dem Volume `staging`. |
| `MAX_UPLOAD_BYTES` | nein | Standard 2 GiB je Datei (Caddy lässt bis 2 GB durch) |
| `FPCALC_PATH` | nein | Standard `fpcalc` (im Image enthalten) |

`.env.example` sollte diese Schlüssel aufnehmen — offen, weil die Datei für Claude per
Einstellung gesperrt ist.

## Ohne Docker (Entwicklung)

```bash
cd backend
uv run python -m masdar migrate && uv run python -m masdar seed
UPLOAD_KEY=dev uv run python -m masdar serve --port 8000
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
docker compose exec api python -m masdar inbox     # auf dem Server, in deploy/
```

listet abgeschickte Uploads mit Datei, Gelehrtem, Selbsteinschätzung, Quelle — und
markiert die, die **trotz Treffer** behalten wurden: beide anhören, bevor registriert wird.
Das Registrieren als Eintrag (ID vergeben, Zuschreibung festlegen) ist noch nicht gebaut.
