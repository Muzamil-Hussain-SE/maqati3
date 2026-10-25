# Betrieb — Upload-Strecke

*Stand 2026-10-25. Genau die Schritte, die bei der Verifikation tatsächlich gelaufen sind.*

## Was der Server braucht

| | |
|---|---|
| Postgres 17 mit pgvector | ParadeDB-Image aus `docker-compose.yml`, oder lokal |
| `fpcalc` (Chromaprint) | `apt install libchromaprint-tools` bzw. `brew install chromaprint`. Liest MP4/M4A/Opus/MP3 selbst — ffmpeg/ffprobe braucht der Server nicht. |
| Python 3.13 + uv | Backend |
| Node 22 | Frontend |

## Umgebungsvariablen (Backend)

| Variable | Pflicht | Bedeutung |
|---|---|---|
| `DATABASE_URL` | ja | `postgresql://masdar:…@host:5432/masdar` |
| `UPLOAD_KEY` | ja | Der Schlüssel im Upload-Link. Ohne ihn startet der Server nicht. Erzeugen: `python -c "import secrets; print(secrets.token_urlsafe(24))"`. Ändern = alle alten Links ungültig. |
| `STAGING_DIR` | nein | Wo Uploads liegen, bis ein Admin sie registriert. Standard `/var/lib/masdar/staging`. Auf ein Volume legen, das gesichert wird. |
| `MAX_UPLOAD_BYTES` | nein | Standard 2 GiB je Datei |
| `FPCALC_PATH` | nein | Standard `fpcalc` |

`.env.example` sollte diese Schlüssel aufnehmen — in dieser Session nicht geschehen,
weil das Lesen der Datei nicht freigegeben war.

## Starten

```bash
cd backend
uv run python -m masdar migrate      # wiederholbar, wendet nur Neues an
uv run python -m masdar seed         # scholars.csv + topics.yml, wiederholbar
uv run python -m masdar serve --host 127.0.0.1 --port 8000

cd frontend
npm ci && npm run build && npm start   # Port 3000
```

Der Server räumt alle 30 Minuten Uploads auf, die 24 h lang nicht abgeschickt wurden.
Von Hand: `python -m masdar sweep`.

## Routing

Ein Reverse Proxy (Caddy) vor beidem: `/api/*` → Backend :8000, alles andere →
Frontend :3000. Request-Body-Limit am Proxy mindestens so hoch wie `MAX_UPLOAD_BYTES`.

Nur in der Entwicklung leitet Next selbst `/api` weiter (`next.config.ts`). Achtung:
`API_ORIGIN` wird beim **Build** eingebacken, nicht beim Start.

## Der Link für die Brüder

```
https://<domain>/ar/upload#k=<UPLOAD_KEY>
```

(`/en/` bzw. `/de/` für die anderen Sprachen.) Der Schlüssel steht hinter `#` und
erreicht deshalb nie Server-Logs oder Referrer. Nur in der Gruppe teilen.

## Für den Admin

```bash
uv run python -m masdar inbox
```

listet abgeschickte Uploads mit Datei, Gelehrtem, Selbsteinschätzung, Quelle — und
markiert die, die **trotz Treffer** behalten wurden: beide anhören, bevor registriert wird.
Das Registrieren als Eintrag (ID vergeben, Zuschreibung festlegen) ist noch nicht gebaut.
