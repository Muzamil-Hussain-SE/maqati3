# Betrieb — Upload und Admin-Bereich

*Stand 2026-10-27. Genau die Schritte, die bei der Verifikation tatsächlich gelaufen sind.*

## Auf einen Server bringen (Docker Compose)

Getestet mit genau diesen Dateien (`deploy/`): am 2026-10-25 lokal (Arm, Chrome-Durchlauf,
208-MB-Video), am 2026-10-26 **auf einem echten Server** (Hetzner CPX12, x86, Ubuntu 26.04,
Docker 29.9): Build, Start, echtes Let's-Encrypt-Zertifikat über Caddy, Test-Uploads
(neu / identisch / neu kodierte Kopie / ohne Ton / Vorschau). Datenbank und Backend-Port
sind von außen nicht erreichbar. **Der Admin-Bereich** (Dashboard) ist am 2026-10-27 lokal getestet
(Chrome, echte Datenbank, ein Platzhalter statt Google) und noch **nicht auf dem Server**
eingespielt; er bleibt dort ohnehin zu, bis Domain und Google-Zugang eingerichtet sind.

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
   git clone https://github.com/PSchmitz-Valckenberg/maqati3.git /opt/maqati3 && cd /opt/maqati3/deploy
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
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | für den Admin-Bereich | Der OAuth-Client von Google, siehe unten |
| `PUBLIC_URL` | für den Admin-Bereich | Die Adresse der Seite, `https://<domain>`, ohne Pfad |
| `SESSION_SECRET` | für den Admin-Bereich | Signiert das Login-Cookie, mind. 32 Zeichen. `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`. Ändern = alle Admins abgemeldet. |

Die vier Admin-Werte gehören zusammen: **alle oder keine**. Keine → der Admin-Bereich ist
geschlossen (jede Adresse antwortet 503). Nur ein Teil → der Server startet nicht, mit
Meldung, welcher Wert fehlt.


## Ohne Docker (Entwicklung)

```bash
docker compose up -d --wait db   # nur die Datenbank, leer; Port belegt? DB_PORT=55432 ...
cd backend
export DATABASE_URL=postgresql://maqati3:devonly@127.0.0.1:5432/maqati3
uv run python -m maqati3 migrate && uv run python -m maqati3 seed
UPLOAD_KEY=dev STAGING_DIR=.staging uv run python -m maqati3 serve --port 8000
cd frontend && npm run dev   # leitet /api an :8000 weiter (API_ORIGIN, beim Build eingebacken)
```

Die Datenbank startet bewusst leer: das Schema legt `migrate` an, wie auf dem Server.
`STAGING_DIR` muss lokal gesetzt sein, sonst scheitert der erste Upload am Standardpfad
`/var/lib/maqati3/staging`.

Die Weiterleitung von Next kappt Uploads bei **10 MB** — nur in dieser Entwicklungs-Variante.
Auf dem Server geht `/api` über Caddy direkt zum Backend (208 MB getestet). Große Dateien
lokal deshalb direkt an Port 8000 schicken oder den Docker-Stack benutzen.

Braucht lokal `fpcalc` und `ffmpeg` (`brew install chromaprint ffmpeg`).

## Der Link für die Brüder

```
https://<domain>/ar/upload#k=<UPLOAD_KEY>
```

(`/en/` bzw. `/de/` für die anderen Sprachen.) Der Schlüssel steht hinter `#` und
erreicht deshalb nie Server-Logs oder Referrer. Nur in der Gruppe teilen.

## Der Admin-Bereich

Adresse: `https://<domain>/de/admin` (auch `/en/`, `/ar/`). Ablauf und Gründe:
`CLAUDE.md`, „The Admin Workflow“. Kurz: Admins melden sich mit Google an, sehen alle
behaltenen Uploads mit Player, wählen den Gelehrten und **registrieren** das Video (das legt
den Eintrag an, Zuschreibung bleibt „nicht sicher“) oder **verwerfen** es. Alles, was ein
Admin tut, steht mit seiner Adresse in der Tabelle `admin_log`.

### Einrichten (einmalig, ca. 15 Minuten, braucht die endgültige Domain)

Google trägt die Adresse der Seite fest ein; mit der vorläufigen DuckDNS-Adresse müsste
alles später neu gemacht werden.

1. <https://console.cloud.google.com> → ein Projekt (das aus `docs/SETUP-GOOGLE.md` oder ein neues).
2. **APIs & Dienste → OAuth-Zustimmungsbildschirm**: Nutzertyp *Extern*, App-Name und
   Support-E-Mail eintragen. Bereiche: nur `openid`, `email`, `profile` (nichts Sensibles).
   Solange der Status *Testing* ist, dürfen nur dort eingetragene **Testnutzer** hinein:
   die Admin-Adressen auch dort eintragen.
3. **Anmeldedaten → Anmeldedaten erstellen → OAuth-Client-ID**, Typ **Webanwendung**
   (nicht „Desktop“ wie bei der Drive-Anleitung). *Autorisierte Weiterleitungs-URI*:
   `https://<domain>/api/v1/admin/auth/callback` — genau so, Zeichen für Zeichen.
4. Client-ID und Client-Secret kopieren und **nur** in die `.env` auf dem Server:
   ```
   GOOGLE_CLIENT_ID=…
   GOOGLE_CLIENT_SECRET=…
   PUBLIC_URL=https://<domain>
   SESSION_SECRET=<die erzeugte Zeichenfolge>
   ```
   Dann `docker compose up -d`. Das Secret nie in den Chat, ein Repository oder ein Foto.
5. Erste Admins eintragen (die **Google-Adresse**, mit der sich die Person anmeldet):
   ```bash
   cd /opt/maqati3/deploy
   docker compose exec api python -m maqati3 admin add name@gmail.com --name Vorname
   docker compose exec api python -m maqati3 admin list
   docker compose exec api python -m maqati3 admin remove name@gmail.com   # wirkt sofort
   ```

Wer nicht auf der Liste steht, kommt nicht hinein, auch mit gültigem Google-Konto; wer
entfernt wird, ist ab der nächsten Anfrage draußen.

### Ohne Dashboard: die Inbox auf dem Server

```bash
ssh root@<IP>                                      # ggf. -i <dein Schlüssel>
cd /opt/maqati3/deploy && docker compose exec api python -m maqati3 inbox
```

listet abgeschickte Uploads mit Datei und Absender und markiert die, die **trotz Treffer**
behalten wurden. Registrieren und Verwerfen geht nur im Dashboard.
