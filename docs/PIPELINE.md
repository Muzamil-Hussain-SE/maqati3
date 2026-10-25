# Pipeline und Deduplikation

*Internes Entwicklerdokument, Deutsch wie ARCHITECTURE.md. `intake/` bleibt Englisch.*

Ziel: Der Bruder lädt etwas hoch, alles Maschinelle passiert von selbst, er korrigiert nur
noch, der Admin gibt frei, es ist online. Und: nichts wird doppelt bearbeitet.

---

## 1. Der Ablauf, Schritt für Schritt

| # | Schritt | Wer/Was | Dauer | Kosten |
|---|---|---|---|---|
| 0 | Einreichung: Link **oder** Datei | Bruder | 1 Min | 0 |
| 1 | **Sofortprüfung** Quelle/Dauer | automatisch | < 1 s | 0 |
| 2 | Holen (`yt-dlp`) + Normalisieren (`ffmpeg` → Opus 24k mono) | Worker | 1–3 Min | 0 |
| 3 | Original bit-identisch ins Kaltarchiv | Worker | — | ~0 |
| 4 | **Audio-Fingerprint** gegen Bestand | Worker | Sek. | 0 |
| 5 | ASR Arabisch mit Zeitmarken | Soniox | ~Echtzeit/5 | 0,10 $/h |
| 6 | **Text-Dedup** gegen Bestand | Worker | Sek. | 0 |
| 7 | **Metadaten erzeugen** (siehe §3) | Haiku Batch | Min. | ~0,001 $ |
| 8 | Rohübersetzung DE + EN, zeilenweise | Haiku Batch | Min. | ~0,003 $ |
| 9 | Erscheint in der Aufgabenliste des Bruders | — | — | — |
| 10 | Korrektur im Doc | Bruder | **der eigentliche Aufwand** | — |
| 11 | Freigabe | Admin | Min. | — |
| 12 | Indexierung, live | Worker | Sek. | ~0 |
| 13 | **Ähnlichkeitsprüfung im Index** | Worker | Sek. | 0 |

Schritte 1–9 sind vollautomatisch. Von der Einreichung bis zur fertigen Aufgabe mit
arabischem Transkript und zwei Rohübersetzungen vergehen wenige Minuten und unter 1 Cent.

**Der ehrliche Teil:** Schritt 10 bleibt der Engpass. Bei 20–40 % Wortfehlerrate auf altem
Kassettenmaterial sind das 90–180 Minuten je Audiostunde, nicht 15. Die Automatik beseitigt
den Engpass nicht, sie halbiert ihn — mehr aber auch nicht. Die Durchsatzmessung in Woche 1
entscheidet, wie groß der Korpus realistisch werden kann.

---

## 2. Deduplikation: fünf Schichten, vom Billigsten zum Teuersten

Jede Schicht fängt einen anderen Fall. Keine ersetzt die andere.

| # | Fängt | Wann | Reaktion |
|---|---|---|---|
| **1** | Dieselbe Online-Quelle nochmal eingereicht | **vor** allem anderen, sofort | blocken, vorhandenen Eintrag zeigen |
| **2** | Byte-gleiche Datei | nach dem Holen | blocken |
| **3** | Dieselbe Aufnahme, anderer Schnitt/Intro/Bitrate | nach dem Holen | markieren, Admin entscheidet |
| **4** | Derselbe Inhalt, andere Aufnahme | nach der ASR | markieren |
| **5** | Dieselbe Antwort bei anderer Gelegenheit gegeben | nach der Indexierung | **kein Duplikat** — verwandt |

### Schicht 1 — Quelle und Dauer
Normalisierte Quell-URL und, wo vorhanden, die Plattform-ID (YouTube-Video-ID etc.) als
`UNIQUE`-Spalte. Fängt den mit Abstand häufigsten Fall — zwei Brüder reichen denselben Link
ein — für null Rechenzeit. Zusätzlich die weiche Prüfung *gleicher Gelehrter + Dauer ± 2 s*,
die als Kandidatenliste angezeigt wird, nicht als Block. Dauer ist ein erstaunlich starkes
Signal: zwei unabhängige Aufnahmen stimmen fast nie auf die Sekunde überein.

### Schicht 2 — SHA-256
Über die Originaldatei, vor jeder Umwandlung. Trivial, exakt, nutzlos gegen Re-Encodes —
deshalb braucht es Schicht 3.

### Schicht 3 — Audio-Fingerprint (Chromaprint)
**Revidiert 2026-10-25, Migration 0003.** Der ursprüngliche Plan — 30-s-Fenster, Treffer
bei byte-gleichen Fenstern — hätte keine einzige weitergeleitete Kopie erkannt. Gemessen
an echter Sprache durch AAC 64k, MP3 32k und Opus 24k: Die Fenster-Fingerprints einer
neu kodierten Kopie sind **nie** byte-gleich (1–9 % der Bits weichen ab; fremde Sprache:
~48 %). Und jede WhatsApp-Weiterleitung ist neu kodiert. Die Fenster hätten also nur
gefunden, was SHA-256 ohnehin findet.

Jetzt: ein Fingerprint je Aufnahme (`fpcalc -raw -length 0`). Ausrichtung per Abstimmung
über die 32-Bit-Werte, die die Neukodierung exakt überleben (rund die Hälfte) — auf
~0,12 s genau, also funktioniert ein Intro beliebiger Länge, nicht nur Vielfache von 15 s.
Bestätigt wird über die Bitfehlerrate auf der **längsten übereinstimmenden Strecke**,
nicht gemittelt über alles: Eine weitergeleitete Zusammenstellung aus dieser und einer
anderen Fatwa muss treffen, zwei Folgen einer Sendung mit gleichem Jingle dürfen es nicht.

Treffer, wenn: Bitfehlerrate ≤ 0,20, Strecke ≥ 10 s **und** ≥ 50 % der kürzeren
Aufnahme. Gemessen: Neukodierungen 0,008–0,085, 7-s-Intro exakt gefunden (+7,07 s),
40-s-Ausschnitt aus der Mitte gefunden; fremde Aufnahme — auch 147 s mit Stille — teilt
keinen einzigen Index-Schlüssel. **Gemessen an synthetischer Sprache.** Altes
Kassettenmaterial ist rauer; die Schwellen gegen echtes Material nachprüfen.

Index: jeder achte Wert, nach Wert gewählt (nicht nach Position, sonst verschiebt ein
Intro alle Schlüssel) — etwa ein Schlüssel pro Sekunde Audio. Kandidat ab 3 gemeinsamen
Schlüsseln, dann voller Vergleich.

### Schicht 4 — Text (SimHash über das normalisierte Arabisch)
Nach der ASR. 64-Bit-SimHash über Shingles von `text_norm` (Tashkeel entfernt, Alef/Hamza
vereinheitlicht), Hamming-Abstand ≤ 6 = Treffer. Fängt den Fall, den Audio nie fängt:
**dieselbe Fatwa, komplett andere Aufnahme** — anderes Mikrofon, anderer Anlass, derselbe
Wortlaut. Bei einer ASR mit 30 % Fehlerrate ist SimHash robuster als exakte Textvergleiche.

### Schicht 5 — Vektorähnlichkeit (ab Phase 2)
Cosinus > 0,97 auf dem arabischen Dokumentvektor. **Das ist ausdrücklich kein Duplikat.**
Derselbe Gelehrte, der dieselbe Frage zweimal bei verschiedenen Gelegenheiten beantwortet,
sind zwei legitime Einträge — und wenn die Antworten voneinander abweichen, ist das sogar
eine der wertvollsten Informationen im ganzen Archiv.

Trotzdem muss es behandelt werden, und zwar aus einem Grund, der nicht die Ordnung betrifft:
Stehen zehn Kopien derselben Antwort in der Trefferliste, liest der Nutzer das als Konsens
unter zehn Gelehrten. Das ist ein Zuschreibungsfehler, kein Darstellungsfehler. Die Lösung
ist gruppieren, nicht löschen.

---

## 3. Die Metadaten je Clip

Zwei Sorten. Die technischen entstehen beim Verarbeiten, die inhaltlichen erzeugt ein
günstiges Modell im Batch und ein Mensch bestätigt sie.

**Technisch (Schritt 2–6):**

```
sha256              Originaldatei
source_platform_id  z. B. YouTube-Video-ID, UNIQUE
duration_sec        auf die Sekunde
chromaprint         ein Fingerprint je Aufnahme + Index-Schlüssel (Migration 0003)
simhash_ar          64 Bit über text_norm
audio_profile       Samplerate, Kanäle, geschätzter Störabstand
```

`audio_profile` ist kein Selbstzweck: stark komprimiertes altes Material mit 8–16 kHz
bekommt man mit keinem besseren ASR-Modell sauber. Das früh zu wissen heißt, solche Clips
in eine eigene Warteschlange zu legen statt einen Bruder drei Stunden daran verzweifeln zu
lassen.

**Inhaltlich (Schritt 7, Haiku Batch, alles als Vorschlag mit Konfidenz):**

```
title_ar / title_en     kurzer Titel
question_ar             der Fragewortlaut, falls im Audio enthalten
topic / topic_sub       aus topics.yml
hukm                    Enum, nicht Prosa: wajib|mandub|mubah|makruh|haram|tafsil|kein_urteil
generality              allgemein | fallbezogen | unklar
speakers[]              erkannte Sprecher (Frager vs. Gelehrter)
mentions[]              genannte Gelehrte und Überlieferer
quran_refs[]            aus den ﴿ ﴾-Markierungen, gegen Tanzil aufgelöst
hadith_refs[]           Fuzzy gegen den lokalen Hadith-Korpus
```

`hukm` und `generality` sind die beiden Felder, die aus Sicht der Risikoanalyse am meisten
wert sind. `generality` bildet ab, dass eine mündliche Fatwa meistens auf einen konkreten
Fall gegeben wurde — das ist mit Retrieval prinzipiell nicht lösbar, nur mit einem Feld, das
am Ende ein Mensch bestätigt.

**Für den Ähnlichkeitsvergleich reicht Technik. Für die Anzeige braucht es den Inhalt.**

---

## 4. Was bei einem Treffer passiert — niemals automatisch löschen

Jeder Eintrag hat `canonical_id`, das auf sich selbst oder auf einen anderen Eintrag zeigt.

- Nur der kanonische Eintrag wird für die Suche indexiert.
- Varianten behalten ihr eigenes Transkript, ihre eigene Quelle, ihre eigene Herkunft.
- Die Eintragsseite zeigt „3 weitere Aufnahmen dieser Antwort".
- Welcher der kanonische ist, entscheidet der Admin — Vorschlag der Maschine: beste
  Audioqualität, längste Fassung, Frage enthalten, offiziellste Quelle.

Gründe gegen automatisches Löschen:

1. Die „Kopie" ist oft die **bessere** Aufnahme — länger, mit Frage, sauberer.
2. Die Herkunft ist Beweismittel. Ein Clip von der offiziellen Seite des Gelehrten und
   derselbe Clip aus einer Telegram-Gruppe sind nicht gleich viel wert, auch wenn das Audio
   identisch ist.
3. Weicht eine der Aufnahmen ab, ist das die interessanteste Information im Archiv und
   darf auf keinen Fall stillschweigend verschwinden.

---

## 5. Wo das mit dem Formular kollidiert

Ein Google Form kann **nicht** live prüfen. Wer vor dem Absenden sagen will „das haben wir
schon", braucht eine eigene Seite.

Trotzdem nicht sofort bauen, aus einem einfachen Grund: **am ersten Tag ist der Bestand
leer, da hat Dedup null Wert.** Wertvoll wird es ab einigen hundert Einträgen — und bis
dahin existiert das Backend ohnehin.

**Phase 1 — Apps Script im Sheet.** Ein `onFormSubmit`-Trigger, ca. 50 Zeilen, kostet
nichts und läuft ohne Backend:

1. normalisiert die eingereichte URL, zieht die Video-ID
2. vergleicht gegen alle bestehenden Zeilen
3. schreibt bei Treffer `possible_duplicate_of` mit der vorhandenen ID
4. schickt dem Bruder automatisch eine Mail: *„We may already have this one — see entry X.
   If yours is a different recording, reply and tell us."*

Das fängt Schicht 1, also den mit Abstand häufigsten Fall, bevor irgendjemand Arbeit
hineinsteckt.

**Phase 2 — eigene Upload-Seite.** Live-Prüfung während der Eingabe, Fortschrittsanzeige,
direkte Rückmeldung. Etwa 3–5 Entwicklertage, sinnvoll sobald das Backend steht.

---

## 6. Reihenfolge

| Wann | Was |
|---|---|
| **sofort, ohne Backend** | Apps Script: URL-Normalisierung + Dauer-Vergleich + Mail an den Bruder |
| **Phase 1, Woche 2–3** | SHA-256 und Chromaprint beim Ingest, `canonical_id` im Schema von Anfang an |
| **Phase 1, Woche 3** | SimHash nach der ASR |
| **Phase 1, Woche 4** | Metadaten-Erzeugung im Batch, als Vorschlag mit Konfidenz |
| **Phase 2** | Vektorähnlichkeit, Gruppierung in den Suchergebnissen, eigene Upload-Seite |

`canonical_id` und `sha256` gehören in die **erste** Migration, auch wenn die Dedup-Logik
erst Wochen später läuft. Nachträglich eine Kanonisierung über tausend bereits
veröffentlichte Einträge zu legen heißt, tausend Links zu brechen.
