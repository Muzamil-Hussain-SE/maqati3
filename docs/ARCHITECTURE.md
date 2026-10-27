# Architektur

*Ergebnis aus 16 parallelen Recherche- und Entwurfsagenten, Stand 2026-10-07.*
*Auf Deutsch, weil es ein internes Entwicklerdokument ist — `intake/` bleibt Englisch.*

> **Abweichung beachten:** Die Entwürfe wurden gegen die erste (deutsche, `.txt`-basierte)
> Zuliefer-Struktur gebaut. Seitdem ist auf Google Form + Google Docs umgestellt. Die
> Kernargumente halten (eine Zeile pro Zeitmarke, kein Forced Alignment nötig, kein eigenes
> Upload-Portal), aber der Ingest-Reader liest Docs-Tabellen statt `.txt`. Siehe Abschnitt am Ende.

---
## Kurzfassung

Basis ist MASDAR (Ein-Maschinen-Monolith, ein Postgres fuer alles), ergaenzt um ISNADs Governance (shadow/verified-Tiers, Melde-Button, Versionierung, Freigabe-Checkliste) und Sanads Messapparat (Goldset, ASR-Bake-off, Embedding-Partitionierung). Entscheidende Korrektur an allen drei Entwuerfen: die Zulieferstruktur existiert bereits unter /Users/by/fatawa-platform — Register-Sheet als einzige Wahrheitsquelle mit festen Spalten und Wertelisten, unveraenderliche Eintrags-ID, Zuschreibungsfeld als Veroeffentlichungssperre, Status pro Sprache, und die Konvention "eine Zeile pro Zeitmarke, in allen drei Sprachen identisch". Es wird deshalb KEIN Upload-Formular gebaut: das Backend liest Drive und Register und schreibt den Pipeline-Status in zusaetzliche Spalten desselben Sheets zurueck. Zweite Korrektur: weil die Brueder bereits [HH:MM:SS]-Zeilen liefern und Zeilen/Zeitmarken laut DATEIFORMATE.md nicht veraendern duerfen, braucht Phase 1 kein Forced Alignment und kein Needleman-Wunsch — ASR erzeugt nur die Rohfassung, der Bruder korrigiert sie in place, die Zeitmarke ueberlebt per Regel. Phase 1 (8 Wochen, ~96 Entwicklerstunden) liefert deshalb ausschliesslich die oeffentliche Bibliothek: Themenbaum, Gelehrtenseiten, Audio-Player mit synchronem dreisprachigem Transkript und sekundengenauem Deep-Link — nutzbar und zitierfaehig ohne KI, ohne Muraji-Engpass, fuer unter 20 EUR/Monat. Das KI-Tool kommt in Phase 2 (Monat 3-6), nachdem ein Goldset aus 150 echten Fragen existiert; es antwortet mit Claude Sonnet 5.5 ueber search_result-Bloecke mit nativen Citations, einem Block pro Gelehrtem, geprueft von einem Haiku-5.5-Verifier auf Attributionsdeckung. Religioese Integritaet sitzt an vier Stellen im Schema statt im Prompt: zuschreibung sperrt die Veroeffentlichung, content_class in themen.yml schliesst Jarh wa Tadil und Personenurteile vom Index aus und routet Talaq/Erbe/Geluebde auf reine Fundstellen ohne Synthese, hukm erfasst das Urteil als Enum statt als Prosa, und die View chunks_citable plus ein DB-Benutzer ohne SELECT auf die Basistabellen macht den Review-Filter unvergessbar. Phase 1 haelt die Tuer offen durch drei Schema-Entscheidungen, die spaeter nicht nachruestbar waeren: zeile.text_raw/text_norm getrennt, embedding partitioniert nach model_id mit app_config.active_embedding_model_id, und revision_log als append-only Tabelle.

---
## Stack-Entscheidungen

| Bereich | Entscheidung | Phase |
|---|---|---|
| Datenbank | Ein Postgres 17 im Container paradedb/paradedb:latest (bringt pgvector 0 | ab Phase 1 |
| Hosting | Hetzner Cloud CX33 (Phase 1), CX43 + CX33 (Phase 2), Nuernberg oder Falkenstein | ab Phase 1 |
| Ingest-Oberflaeche | KEINE eigene Oberflaeche | Phase 1 |
| Status-Rueckkanal | Der Worker schreibt in vier NEUE Spalten des bestehenden Register-Sheets: pipeline_status, pipeline_fehler, rohtext_url, geprueft_url | Phase 1 |
| Timestamps und Alignment | Phase 1: KEIN Alignment | Phase 1 ohne, Phase 3 mit (ctc-forced-aligner MMS-300m-1130, zwingend mit uroman-Romanisierung) |
| ASR | Soniox async, 0,10 USD/Audiostunde, Diarisierung und Wort-Timestamps inklusive | Phase 1 |
| Maschinelle Rohuebersetzung | Claude Haiku 5 | Phase 1 |
| Embedding | BGE-M3 (BAAI, MIT-Lizenz, 568M Params, 1024 dim, 8192 Kontext), halfvec(1024), HNSW m=32 ef_construction=200 ef_search=120 | Phase 2 |
| Index-Sprachstrategie | Alle drei Sprachen indexieren, aber DE/EN nur bei status_de bzw | Phase 2 |
| Lexikalische Suche | pg_search (ParadeDB, Tantivy) BM25 ueber eine GENERATED-Spalte zeile | Phase 2 |
| Reranker | Voyage rerank-3-lite (0,02 USD/1M Token, 200M Freitoken) | Phase 2 |
| LLM Synthese | claude-sonnet-5-5, effort explizit 'high' (Default ist medium), max_tokens 900 | Phase 2 |
| LLM Nebenaufgaben und Verifier | claude-haiku-5-5 (0,10 / 0,50 USD je 1M, Batch 0,05 / 0,25, 1M Kontext) fuer Query-Verstehen, Themen-Tagging, Uebersetzungs-QA-Screening und den Verif | Phase 2 |
| Zitat-Erkennung Quran/Hadith | Die Brueder markieren Quranverse bereits mit ﴿ ﴾ (DATEIFORMATE | Phase 1 Parser, Phase 2 Lookup |
| Job-Queue | Eine Postgres-Tabelle job(id, kind, payload jsonb, state, attempts, run_after, locked_until, last_error) mit SELECT  | Phase 1 |
| Backend | EIN Python-3 | Phase 1 |
| Frontend | Next | Phase 1 |
| Schriften | Noto Naskh Arabic 400/600 fuer Transkript und Fliesstext, IBM Plex Sans Arabic 400/600 fuer UI, selbst gehostet als WOFF2, Subsetting auf Arabisch + L | Phase 1 |
| Medien-Auslieferung | Audio-first als Architekturentscheidung: Opus 24 kbit/s mono (0,176 MB/min), ein Objekt je Eintrag, progressive HTTP-Range-Auslieferung aus Hetzner Ob | Phase 1 |
| Auth | Auth | Phase 1 minimal, Phase 2 vollstaendig |
| Observability | Sentry Cloud Developer (5 | Phase 1 Sentry, Phase 2 Traces |
| Kostenschutz | Vierfach ab dem Tag, an dem das KI-Tool live geht: (1) harter Tages-Hardcap in EUR in app_config, der bei Erreichen NICHT die Seite abschaltet, sonder | Phase 2, vor dem ersten oeffentlichen KI-Request |

### Begründungen im Detail

#### Datenbank
**Ein Postgres 17 im Container paradedb/paradedb:latest (bringt pgvector 0.8 und pg_search mit), auf EINER Hetzner-VM, Docker Compose**

*Warum:* 3.000 Eintraege ergeben bei Q&A-Chunking ca. 150.000 Vektoren ueber drei Sprachen = ca. 0,4 GB halfvec inkl. HNSW-Overhead. Der Break-even fuer eine dedizierte Vektor-DB liegt bei 10-50 Mio. Vektoren. Entscheidender als Performance: sichtbarkeit, zuschreibung, status_ar und content_class sind normale WHERE-Klauseln mit Fremdschluesseln; ein zweiter Index koennte vom Review-Stand abweichen, und das waere kein Performance-, sondern ein Zuschreibungsproblem. Das ParadeDB-Image schon in Phase 1 nehmen, obwohl pgvector/pg_search erst in Phase 2 gebraucht werden — kostet nichts und spart eine Migration.

*Verworfen:* Qdrant/Weaviate/Pinecone (100-230 USD/Monat fuer Faehigkeiten, die 50x spaeter gebraucht werden, plus Sync-Drift). Meilisearch trotz bester arabischer Tokenisierung (Charabia) — kann nicht gegen Fremdschluessel joinen. Supabase (PITR 100 USD je 7 Tage, pg_search-Verfuegbarkeit unverifiziert). Neon (Scale-to-Zero ist Gift fuer HNSW: nach Cold Start liegt der Graph nicht im Page Cache).

*Kosten:* 0 EUR Lizenz, laeuft auf der ohnehin bezahlten VM

#### Hosting
**Hetzner Cloud CX33 (Phase 1), CX43 + CX33 (Phase 2), Nuernberg oder Falkenstein. Plain Docker Compose mit Caddy, kein PaaS. pgBackRest taeglich voll plus WAL-Archiving nach Hetzner Object Storage**

*Warum:* Die Last ist Worker-Last (ffmpeg, Batch-Jobs), nicht Request-Last — dort gewinnt eine Dauer-VM sofort gegen jedes Serverless-Modell. EU-Standort, 20 TB Egress inklusive. pgBackRest ersetzt die 100 USD/Monat, die Supabase fuer PITR nimmt.

*Verworfen:* CPX und CCX kategorisch — Hetzner hat am 15.06.2026 CPX um Faktor 2,4-2,75 und CCX um 2,1-2,73 erhoeht (CCX23 von 31,49 auf 85,99 EUR), CX und CAX nur um 1,30-1,38. Coolify/Dokploy verworfen: ein selbst gehostetes PaaS ist eine zusaetzliche Schicht, die genau dann bricht, wenn der Entwickler keine Zeit hat; bei fuenf Containern auf einer Maschine loest docker compose dasselbe Problem. Vercel als Hauptplattform (Worker und ffmpeg laufen dort nicht). Railway (ein 4-vCPU-Worker 12 h/Tag kostet dort ca. 80 USD/Monat).

*Kosten:* CX33 8,49 EUR + 20% Backup + 0,60 IPv4 = 10,79 EUR/Monat. UNVERIFIZIERT: hetzner.com rendert Preise per JS; zwei Sekundaerquellen nennen fuer CX23 5,49 bzw. 7,13 EUR. Vor Buchung in der Console gegenpruefen.

#### Ingest-Oberflaeche
**KEINE eigene Oberflaeche. Das Backend liest das bestehende Google Drive (02_ARCHIV/<gelehrter>/<id>/) und das Register-Sheet. Zugriff ueber OAuth-Refresh-Token EINES menschlichen Kontos (einmalige Zustimmung), nicht ueber einen Service Account. Polling via files.list/changes.list alle 5 Minuten mit persistiertem startPageToken, supportsAllDrives=true und includeItemsFromAllDrives=true bei JEDEM Call. Join ausschliesslich ueber die Eintrags-ID und einen eigenen SHA-256, nie ueber Dateinamen**

*Warum:* Die Struktur existiert, ist durchdacht und erzwingt die Pflichtfelder bereits ueber Dropdowns und Validierung im Sheet. Ein eigenes Formular kostet 8-12 Entwicklertage und blockiert die Zulieferung bis Monat 3, waehrend das Drive sie heute erlaubt. Der Service-Account-Fallstrick (403 storageQuotaExceeded) trifft nur das SCHREIBEN von Dateien — mit einem menschlichen OAuth-Konto gehoeren erzeugte Dateien diesem Menschen und es wird kein Google Workspace gebraucht. watch-Channels werden nicht benutzt, weil sie nach max. 1 bzw. 7 Tagen ohne Auto-Renew ablaufen und einen oeffentlichen HTTPS-Endpunkt mit gueltigem Zertifikat brauchen; 100 Quota-Units pro changes.list-Call sind 28.800 Units/Tag, voellig unkritisch.

*Verworfen:* Presigned-URL-Upload-Formular (loest ein geloestes Problem). Service Account (Storage-Quota-Falle, braucht Shared Drive und damit Workspace). Telegram als Binaertransport (20 MB getFile-Limit). GitHub-PRs als Abgabeweg fuer Nicht-Techniker.

**Revidiert 2026-10-25 (siehe auch Zeile 813):** Diese Ablehnung galt fuer ein Formular, das das geloeste Problem "Datei irgendwo ablegen" nochmal loest. Die Praxis zeigt ein anderes Problem, das das Drive-Formular nicht loest: die meisten Clips kommen als WhatsApp-weitergeleitete Handyvideos ohne jede Quell-URL, oft 10-20 auf einmal, und Brueder sollen selbst entscheiden koennen, ob ein als aehnlich erkannter Clip wirklich derselbe ist (Audio-Vorschau, live, beim Hochladen) oder eine andere Gelegenheit. Das kann ein Formular ohne Backend-Ruecksprache waehrend der Eingabe nicht: kein SHA-256-Abgleich in Echtzeit, kein Fingerprint-Kandidat mit Hoerprobe, keine Entscheidung im selben Schritt. Deshalb zusaetzlich zum Drive-Formular (bleibt fuer Link-Einreichungen bestehen): eine eigene Bulk-Upload-Seite im bestehenden Next.js-Frontend, Zugriff ueber einen unlisted Link wie die beiden bestehenden Drive-Links, kein Login. Ablauf: Datei -> SHA-256 pruefen (Treffer = automatisch verworfen, Tabelle hat die Spalte seit Migration 0001) -> kein Treffer: Chromaprint gegen Eintraege UND noch nicht registrierte Uploads pruefen (Migration 0002/0003; Vergleich per Bitfehlerrate, siehe PIPELINE.md Schicht 3 — die urspruenglichen byte-gleichen 30-s-Fenster haetten keine neu kodierte Kopie erkannt) -> Treffer: Kandidat mit Hoerprobe anzeigen, Bruder entscheidet -> kein Treffer: normal in die Pipeline. Text-Dublette (Schicht 4, SimHash) bleibt Admin-Sache nach der ASR, weil sie ein fertiges Transkript braucht und nicht live laufen kann. Kostet mehr als die 96 Entwicklerstunden-Annahme oben: eine Upload-Route, einen Upload-Endpunkt, Speicher fuer Dateien waehrend der Pruefung, und einen ffmpeg/fpcalc-Dienst, der synchron antworten muss statt im Hintergrund-Worker zu laufen.

*Kosten:* 0 EUR. Google Drive API ist bis 400 Mio. Quota-Units/Tag kostenlos.

**Revidiert 2026-10-27 (Pruefen):** Das Korrigieren der Transkripte und Uebersetzungen laeuft nicht mehr ueber Google Docs im Drive, sondern in einem eigenen Tabellen-Editor im Admin-Dashboard (Zeile anklicken, Audio springt dorthin, Sprache als geprueft markieren, pro Sprache "in Bearbeitung" sichtbar). Gruende: Sperren, Pruefregeln und Zuschreibung liegen dann in einem System, und die Drive/Docs-Anbindung (OAuth-Token, Zurueckspielen, Quoten) entfaellt. Kostet mehr Bauaufwand als die Doc-Loesung, die oben als bewusst nicht gebaut galt. Login: Google-Anmeldung mit Admin-Liste, kein Keycloak. Ablauf und Begruendung: CLAUDE.md, "The Admin Workflow". `intake/` (Link 2 "My tasks", Doc-Vorlage) beschreibt bis dahin noch den alten Weg.

#### Status-Rueckkanal
**Der Worker schreibt in vier NEUE Spalten des bestehenden Register-Sheets: pipeline_status, pipeline_fehler, rohtext_url, geprueft_url. Kein Telegram-Bot, keine separate Statusseite, keine zweite Oberflaeche**

*Warum:* Die Brueder und der Admin haben das Sheet ohnehin taeglich offen. Ein Tag Arbeit statt zwei Wochen, und es entsteht kein zweites System, das jemand betreiben muss. Fehlermeldungen in der Sprache des Bearbeiters mit konkretem Feld und Korrekturvorschlag, nie ein Stacktrace: 'Zeile 34: Zeilenzahl de.txt (87) weicht von ar.txt (91) ab'.

*Verworfen:* Telegram-Bot plus oeffentliche Statusseite (beide drei Entwuerfe wollten das; zwei zusaetzliche Systeme mit Auth, i18n und Pflege).

*Kosten:* 0 EUR

#### Timestamps und Alignment
**Phase 1: KEIN Alignment. Die Zeitmarken kommen aus dem ASR-Lauf, der die Rohfassung erzeugt, und ueberleben die menschliche Korrektur, weil DATEIFORMATE.md das Aendern von Zeilen und Zeitmarken verbietet. Validator erzwingt das maschinell: monoton wachsende Zeiten, Format [HH:MM:SS], keine Zeit > dauer_sek, Zeilenzahl de/en identisch mit ar**

*Warum:* Das ist die groesste Vereinfachung gegenueber allen drei Entwuerfen und sie faellt aus der bestehenden Arbeitsanweisung heraus. Needleman-Wunsch-Alignment, ctc-forced-aligner und die uroman-Falle werden in Phase 1 schlicht nicht gebraucht. Sie kommen erst, wenn historische Transkripte OHNE Zeitmarken importiert werden sollen (Phase 3).

*Verworfen:* Forced Alignment als Pflichtschritt in Phase 1 (alle drei Entwuerfe). Montreal Forced Aligner dauerhaft (undiakritisiertes Arabisch hat keine eindeutige G2P-Abbildung). WhisperX (erbt Whispers schwache Arabisch-WER).

*Kosten:* 0 EUR in Phase 1

#### ASR
**Soniox async, 0,10 USD/Audiostunde, Diarisierung und Wort-Timestamps inklusive. Zeilenbildung aus den Segmenten: neue Zeile bei Sprecherwechsel, bei Pause > 0,6 s oder nach spaetestens 12 Sekunden. Vorgeschaltet ein Bake-off auf 20 selbst gewaehlten Clips**

*Warum:* 7,2 % WER auf FLEURS-Arabisch bei einem Fuenftel bis Siebtel des Konkurrenzpreises; 400 h Zielkorpus kosten 40 USD einmalig. ASR ist in diesem Projekt kein Kostenposten. Das Bake-off (alte Kassette, Studio, Dialekteinschub, dichtes Quran-Zitat, Frage-Antwort-Wechsel) bewertet getrennt WER, CER, Namenstreue bei Gelehrten und Ueberlieferern sowie Timestamp-Qualitaet — es entscheidet ueber die Review-Last der naechsten Jahre, also ueber die einzige Groesse im Projekt, die in Personenjahren gemessen wird.

*Verworfen:* Whisper large-v3 self-hosted (15,44 % FLEURS-ar, schlechtester Wert im Feld; spart auf 400 h unter 30 USD gegenueber Soniox). Whisper large-v3-turbo kategorisch: 125 % WER auf arabischem Realmaterial gegen 66 % bei large-v3 — ein Transkript mit mehr Fehlern als Woertern fuehrt Reviewer aktiv in die Irre. AssemblyAI (12,1 % ar auf der eigenen Benchmarkseite). Deepgram (keine publizierte Arabisch-Zahl).

*Kosten:* Zielkorpus 400 h = 40 USD = 36,80 EUR einmalig. Bake-off gratis aus Startguthaben (Speechmatics 100 USD, Gladia 50 EUR).

#### Maschinelle Rohuebersetzung
**Claude Haiku 5.5 ueber die Batch-API (0,05 / 0,25 USD je 1M), zeilenweise mit +/-3 Zeilen Kontextfenster, Glossar im gecachten System-Prompt. Ausgabe strikt eine Zielzeile je Quellzeile, sonst Job-Fehler ohne Teilschreiben**

*Warum:* Die Brueder bekommen laut ANLEITUNG bereits eine Rohuebersetzung zum Korrigieren — das halbiert ihren Aufwand gegenueber freiem Uebersetzen und ist damit eine Massnahme gegen den groessten Projektengpass. Zeilenweise Erzeugung haelt die Zeitmarkenbindung konstruktionsbedingt exakt; es gibt kein Alignment-Problem, das geloest werden muesste.

*Verworfen:* bertalign/vecalign (nur noetig fuer historische Fliesstext-Uebersetzungen, Phase 3). hunalign (kein AR-DE-Fachwoerterbuch existiert). Freie menschliche Uebersetzung als Primaerweg (erzeugt genau die Fliesstexte ohne Zeitmarken, an denen der Deep-Link bricht).

*Kosten:* 400 h Zielkorpus, beide Sprachen: ca. 10 USD = 9,20 EUR einmalig

#### Embedding
**BGE-M3 (BAAI, MIT-Lizenz, 568M Params, 1024 dim, 8192 Kontext), halfvec(1024), HNSW m=32 ef_construction=200 ef_search=120. Bulk-Indexierung einmalig auf RunPod RTX A5000 Community (0,16 USD/h), Query-Zeit per ONNX int8 auf der CPU der App-VM**

*Warum:* Bester belegter Arabisch-Wert im offenen Feld: MIRACL-ar 78,4 nDCG@10 dense gegen BM25 39,5 und mDPR 49,9; robustester cross-lingualer Embedder (en→ar 56 % Hits@20 gegen 41 % bei multilingual-e5-large). MIT-Lizenz ist bei einem Projekt, das Spenden annimmt, Voraussetzung und kein Detail. Der Embedder ist eine Einbahnstrasse — ein Wechsel heisst Reindexierung des Gesamtkorpus —, also gehoeren hier offene Gewichte und permissive Lizenz hin. WICHTIG: BGE-M3 ist NICHT Matryoshka-trainiert, Dimensionen duerfen nicht truncated werden.

*Verworfen:* multilingual-e5-large (en→ar 41 %, 512 Token zerschneiden jede Fatwa). OpenAI text-embedding-3-large (MIRACL-Mittel 54,9 gegen 67,8 fuer M3, kein sparse-Head). Jina (CC-BY-NC-4.0 — bei Spenden/Verein kein sicherer Hafen). Cohere (Pay-as-you-go-Preis nicht mehr publiziert, Model Vault ab 2.000 USD/Monat). Qwen3-Embedding als Phase-3-Kandidat gemerkt, aber ohne belastbare MIRACL-ar-Zahl.

*Kosten:* Zielkorpus alle drei Sprachen: ca. 3 GPU-Stunden = 0,50 USD einmalig

#### Index-Sprachstrategie
**Alle drei Sprachen indexieren, aber DE/EN nur bei status_de bzw. status_en = 'geprueft'. Language-balanced retrieval: pro Sprache getrennt top-30, Cap von 50 % je Sprache vor der Fusion, dann RRF. Zitiert wird IMMER das arabische Original derselben Zeilen-ID**

*Warum:* Die Hauptrichtung des Produkts ist de/en→ar; BGE-M3 haelt ar→ar bei 92 % Hits@20 und faellt bei en→ar auf 56 %. Mit indexierter Uebersetzung wird daraus ein de→de-Treffer bei ca. 90 %. Der Einwand der Gegenseite (ein Treffer auf fehlerhafter Uebersetzung ist ein Zuschreibungsrisiko) ist doppelt entschaerft: nur geprueftes Material kommt in den Index, und zitiert wird nie die Uebersetzung, sondern der arabische Parent. Same-Language-Bias ist real (fuer arabische Testsets kommen 80,8 % arabische Dokumente zurueck), deshalb der Cap vor der Fusion.

*Verworfen:* Nur-Arabisch-Index (Recall-Einbruch von ca. 35 Punkten in der Hauptrichtung). Reine Query-Uebersetzung als Alleinloesung: die CLIR-Messung zeigt BGE-M3 bei Recall@15 mit 96,2 % gegen 92,4 % fuer die beste Google-Translate-Pipeline. ABER: vor dem Festschreiben auf 200 Eintraegen in beiden Varianten gegen das Goldset messen, Kosten unter 20 USD.

*Kosten:* ca. 1,8x Vektoren statt 1x, bei diesem Korpus unter 0,5 GB

#### Lexikalische Suche
**pg_search (ParadeDB, Tantivy) BM25 ueber eine GENERATED-Spalte zeile.text_norm, Tokenizer icu, stemmer arabic. normalize_ar() als IMMUTABLE SQL-Funktion mit identischem Python-Zwilling und gemeinsamen Testvektoren**

*Warum:* Woertliche Quran- und Hadith-Zitate sowie Gelehrten- und Ueberliefererrnamen sind lexikalische Treffer, bei denen Dense-Retrieval systematisch schlecht ist. pg_search hat Arabisch im verifizierten Stemmer-Set und echtes korpusweites IDF; ts_rank hat kein IDF und gewichtet 'salah' so schwer wie den seltenen Namen eines Ueberlieferers. Normalisierung: NFKC, Tashkeel U+064B-U+0652 entfernen, Tatweel U+0640 entfernen, أ/إ/آ/ٱ→ا, ى→ي, ة→ه, Lam-Alef-Ligaturen aufloesen, ٠-٩→0-9.

*Verworfen:* Postgres-Bordmittel to_tsvector('arabic') als Basis (Snowball ohne Hunspell, trennt den Artikel nicht ab, produziert falsche Lexeme). Farasa (Research-Only-Lizenz). unaccent (auf Latein ausgelegt, entfernt Harakat nicht zuverlaessig). Automatisches Tashkeel kategorisch: bestes System im KSAA-2026-Shared-Task ca. 10 % DER / 34,5 % WER, CAMeL Tools 45,9 %, Mishkal 76,8 % — eine falsche Harakah verschiebt Aktiv/Passiv oder Kasus und setzt dem Gelehrten Vokale in den Mund.

*Kosten:* 0 EUR

#### Reranker
**Voyage rerank-3-lite (0,02 USD/1M Token, 200M Freitoken). Top-40 Kandidaten, dual gescort gegen das arabische Original UND gegen die Uebersetzung in Fragesprache, final = max(beide). Reranker arbeitet ausschliesslich auf text_raw, nie auf text_norm**

*Warum:* 200M Freitoken decken ca. 13.000 Queries, danach ca. 0,0003 USD/Query. Der Reranker ist austauschbar ohne Reindexierung — das ist der entscheidende Unterschied zum Embedder, deshalb darf er eine API sein. Dual-Scoring entscheidet die offene Frage Original-vs-Uebersetzung empirisch statt per Annahme.

*Verworfen:* Cohere Rerank 3.5 (2,00 USD je 1.000 Queries = Faktor 60+). jina-reranker-m0 trotz der besten belegten Arabisch-Zahl (MIRACL-ar 79,78) wegen CC-BY-NC-4.0 — die Zahl bleibt Qualitaets-Zielmarke. bge-reranker-v2-m3 self-hosted: rechnet sich erst ab ca. 380.000 Queries/Monat (115 USD/Monat A5000 gegen 0,0003 USD/Query), also nie in absehbarer Zeit. In einer Fremdmessung lag er zudem 0,48 % UNTER dem First-Stage-Ergebnis, deshalb ist 'Reranker aus' eine der gemessenen Konfigurationen.

*Kosten:* bei 10.000 Fragen/Monat ca. 1,50 USD

#### LLM Synthese
**claude-sonnet-5-5, effort explizit 'high' (Default ist medium), max_tokens 900. Kontext als search_result-Content-Blocks mit citations.enabled=true, EIN Block pro Gelehrtem, cache_control auf System-Prompt und Glossar. claude-opus-5-5 ausschliesslich im Pre-Cache ueber die Batch-API mit Muraji-Freigabe**

*Warum:* Citations sind hier ein API-Primitiv statt eines Prompt-Tricks: pro Textblock kommt ein citations-Array mit source, title, cited_text und Zeichen-Offsets zurueck, direkt in Deep-Links uebersetzbar, und cited_text zaehlt weder als Output- noch spaeter als Input-Token. Zuschreibungstreue entsteht strukturell (ein Block pro Gelehrtem, erzwungenes Positionsformat, Attributions-Verifier), nicht durch Modellgroesse — deshalb reicht Sonnet live. Opus gehoert genau dorthin, wo die Kosten einmalig sind und ein Mensch gegenliest. Sonnet 0,0246 USD gegen Opus 0,0492 USD pro Antwort.

*Verworfen:* Opus 5.5 als Live-Default (verdoppelt die groesste Einzelposition; bei 50.000 Fragen/Monat 2.715 statt 1.358 EUR). Gemini 3 Flash ist auf IslamicMMLU vorn (93,8 %) und hat besseres Abstention-Verhalten — bleibt Pflicht-Vergleich auf dem eigenen Goldset, hat aber kein Aequivalent zu search_result-Citations auf eigene Chunks; Google Search Grounding bleibt in jedem Fall AUS, externe Fatwa-Seiten einzuschleppen ist genau der Schaden, der verhindert werden soll. GPT-5.x (kein Span-Zitat-Primitiv). Fanar-Sadiq trotz 81,6 % — eigener, nicht an der salafiya ilmiya ausgerichteter Quellenkanon; einbinden hiesse, unsichtbar einen fremden Manhaj importieren, und zwar formal korrekt zitierend. ALLaM/Jais (59,5 bzw. 63,4 % IslamicMMLU, 8k Kontext, teurer als Sonnet).

*Kosten:* ca. 0,0246 USD je Live-Antwort inkl. Prompt-Caching

#### LLM Nebenaufgaben und Verifier
**claude-haiku-5-5 (0,10 / 0,50 USD je 1M, Batch 0,05 / 0,25, 1M Kontext) fuer Query-Verstehen, Themen-Tagging, Uebersetzungs-QA-Screening und den Verifier. Verifier mit erzwungenem Structured Output in einem ZWEITEN Call ohne Citations**

*Warum:* Query-Expansion 0,0003 USD, Verifier 0,0015 USD, Tagging 0,0007 USD je Video — damit reduziert sich die Kostenfrage praktisch vollstaendig auf die Synthese. Zwei Calls sind technisch zwingend: citations.enabled und output_config.format zusammen geben einen 400-Fehler.

*Verworfen:* NLI-Encoder (DeBERTa, Auto-GDA) als Verifier, obwohl die Literatur sie als Produktionsempfehlung fuehrt: englischzentriert, versagen bei gesprochenem klassischem Arabisch mit Quran-Zitaten genau dort, wo es zaehlt — und bei 0,0015 USD ist der Compute-Vorteil wirtschaftlich irrelevant. DeepSeek/Qwen self-hosted: Haiku 5.5 unterbietet DeepSeek-V4-Flash beim Input (0,10 gegen 0,14) bei besserem Arabisch.

*Kosten:* unter 10 EUR/Monat bei 10.000 Fragen

#### Zitat-Erkennung Quran/Hadith
**Die Brueder markieren Quranverse bereits mit ﴿ ﴾ (DATEIFORMATE.md). Der Parser nimmt die Marker als Trigger und macht NUR innerhalb des markierten Spans einen Fuzzy-Match gegen den lokal gespiegelten Tanzil-Korpus (CC BY 3.0), Schwelle 85 %, Ersetzung durch den exakten Uthmani-Rasm inkl. Diakritika, Sura:Aya als Metadatum, Span im Index schreibgeschuetzt. Hadith analog gegen fawazahmed0/hadith-api (Unlicense, 36.390 Hadithe mit Gradierungen)**

*Warum:* Der menschliche Marker macht aus einem unsicheren Suchproblem ein sicheres Lookup-Problem. Loest drei Dinge in einem Schritt: ASR-Fehler bei Rezitationsduktus, korrekte Diakritika ohne automatisches Tashkeel, und Zitierbarkeit mit Stellenangabe. Zusaetzlich fuers Retrieval wichtig: hunderte Fatawa zitieren dieselbe Ayah, Dense-Retrieval clustert sonst auf das Zitat statt auf die Frage — markierte Spans werden deshalb im Embedding-Text durch [قرآن 2:286] ersetzt und nur in der Anzeige vollstaendig behalten.

*Verworfen:* sunnah.com (Terms verbieten Weiterverteilung, 1-2 req/s) und dorar.net (Cloudflare-Challenge, ungeklaerte Rechte) als Index-Backend — beide nur Live-Link-out. Blinder Fuzzy-Match ueber den gesamten Text ohne Marker (hoehere False-Positive-Rate; ein falsch verlinkter Vers ist eine falsche Zuschreibung).

*Kosten:* 0 EUR, beide Korpora lokal spiegelbar

#### Job-Queue
**Eine Postgres-Tabelle job(id, kind, payload jsonb, state, attempts, run_after, locked_until, last_error) mit SELECT ... FOR UPDATE SKIP LOCKED, ca. 60 Zeilen Python. Pipeline-Fortschritt zusaetzlich als Zeitstempelspalten auf eintrag. Heartbeat auf locked_until alle 30 s fuer lange Jobs**

*Warum:* Volumen ist winzig: 3.000 Eintraege ueber Jahre, im Peak vielleicht 100 Jobs/Tag. Postgres-Queues liefern 11-14k Jobs/s. Jobs und Daten in EINER Transaktion macht Idempotenz trivial: jede Stufe prueft den Zeitstempel ihres Vorgaengers und schreibt den eigenen, Wiederaufsetzen und Re-Run kosten nichts. Ohne Heartbeat startet der Visibility-Timeout eine 40-Minuten-Transkription doppelt.

*Verworfen:* pgmq (unnoetige Extension, SKIP LOCKED reicht). Celery (Betriebsaufwand ohne Gegenwert). Temporal (ab 100 USD/Monat). Inngest/Trigger.dev (Fremdkosten, Kontrollverlust).

*Kosten:* 0 EUR

#### Backend
**EIN Python-3.13-Projekt mit uv: FastAPI als einzige API, Worker als zweiter Prozess derselben Codebase. Next.js macht ausschliesslich Rendering und Session, keine Geschaeftslogik und keinen DB-Zugriff. TS-Client in CI via @hey-api/openapi-ts aus openapi.json generiert und committed, mit Drift-Check**

*Warum:* ASR-Nachbearbeitung, CAMeL-Normalisierung, BGE-M3-ONNX, Levenshtein-Zitatsuche, Google-API-Client — das Oekosystem ist Python. Der Split bleibt sauber, solange die Grenze eine generierte OpenAPI ist: der Frontend-Helfer sieht nie Python.

*Verworfen:* Durchgaengiges TypeScript (Hono) — elegant, aber nur richtig, wenn kein ML im Haus laeuft. poetry zugunsten von uv.

*Kosten:* 0 EUR

#### Frontend
**Next.js 16.4 App Router mit cacheComponents: true, next-intl (AOT, ca. 457 B server / 4 KB client, ICU deckt die 6 arabischen Plural-Kategorien ab), Tailwind v4 ausschliesslich logical properties mit Lint-Regel gegen left/right/pl-/pr-, Vidstack als Player, TanStack Virtual fuer die Transkriptliste mit binaerer Cue-Suche. generateStaticParams nur fuer die Top-200, dynamicParams=true, On-Demand-revalidatePath aus dem Ingest**

*Warum:* 3.000 Eintraege x 3 Sprachen = 9.000 Seiten lassen sich noch vorrendern, 30.000 nicht mehr — die Top-N-Entscheidung von Anfang an spart den schmerzhaften Umbau. Eine 20-Minuten-Fatwa hat 150-250 Zeilen, bei Langvortraegen 800+; ohne Virtualisierung und mit linearem Scan bei jedem timeupdate ist die Seite auf dem Mittelklasse-Android unbenutzbar, genau dem Geraet der Zielgruppe. Kritisch: Video-Progressbar und Timecodes bleiben dir='ltr', sonst zeigt Vorspulen im arabischen Layout nach links.

*Verworfen:* Paraglide JS (Bundle-Vorteil bei 3 Locales marginal, mehr Eigenbau beim Routing — schlecht fuer einen freiwilligen Helfer). Plyr (deprecated). rtl-Flipping-Plugins zugunsten logischer Eigenschaften.

*Kosten:* 0 EUR

#### Schriften
**Noto Naskh Arabic 400/600 fuer Transkript und Fliesstext, IBM Plex Sans Arabic 400/600 fuer UI, selbst gehostet als WOFF2, Subsetting auf Arabisch + Latein + Ziffern, font-display: swap, preload nur fuer den Textfont**

*Warum:* Naskh-Formen sind die richtige Buchtypografie fuer Fatwa-Volltext und vokalisierte Quran-Zitate; Plex Arabic teilt Proportionen mit Plex Latin, dadurch wirken AR/DE/EN wie ein System. Subsetting vorsichtig: aggressives Unicode-Range-Subsetting zerstoert GSUB-Ligaturen und kontextuelle Formen (init/medi/fina/isol) — immer mit einer vollvokalisierten Ayah testen, nie mit Lorem-Ipsum-Arabisch.

*Verworfen:* Readex Pro (Lern-App-Charakter, unpassend fuer religioesen Text). Amiri optional lazy als reiner Zitat-Font.

*Kosten:* 0 EUR (OFL)

#### Medien-Auslieferung
**Audio-first als Architekturentscheidung: Opus 24 kbit/s mono (0,176 MB/min), ein Objekt je Eintrag, progressive HTTP-Range-Auslieferung aus Hetzner Object Storage. Originale bit-identisch in Backblaze B2 (6,95 USD/TB) BEVOR der erste ffmpeg-Lauf startet. Video nur als sekundaerer Button. Bunny Volume-CDN (0,005 USD/GB global flat) erst, wenn Traffic kommt**

*Warum:* Groesster Nicht-LLM-Hebel: der gesamte Zielkorpus von 400 h liegt als Opus bei 4,2 GB. Bei Fatawa ist das Bild fast immer irrelevant, und 24 kbit/s laeuft auf jedem 2G-Netz in MENA. Progressive Einzeldatei macht Deep-Links auf die Sekunde zuverlaessiger als segmentiertes HLS. Lossy ist unumkehrbar und der arabische Originalton ist das Beweismittel der Zuschreibung.

*Verworfen:* Cloudflare Stream (5 USD je 1.000 gespeicherte Minuten = bei 24.000 Katalogminuten 120 USD/Monat, bevor jemand etwas anschaut; Minutenabrechnung ist fuer ein Longtail-Archiv strukturell falsch, zudem wird client-seitiges Preloading als Delivery abgerechnet). Mux und api.video aus demselben Grund. AWS S3+CloudFront (Egress-Falle). PeerTube (man betreibt dann YouTube statt der eigenen Plattform). Bunny Standard-Netz: Middle East & Africa kostet dort 0,060 USD/GB, das Zwoelffache des Volume-Tiers.

*Kosten:* Object Storage 6,49 EUR/Monat inkl. 1 TB Storage und 1 TB Egress; B2 fuer 180 GB Originale ca. 1,15 EUR/Monat

#### Auth
**Auth.js mit E-Mail-Magic-Link, Rollen als Spalte in Postgres: admin | muraji | pruefer | bearbeiter. Keine Endnutzer-Accounts, kein Login fuer die Bibliothek**

*Warum:* 10-15 interne Nutzer, jede Loesung ist kostenlos. Sessions in der eigenen DB, keine US-Abhaengigkeit fuer eine Handvoll Konten. Kein Endnutzer-Account bedeutet, dass Art.-9-DSGVO-Daten gar nicht erst mit einer Identitaet verknuepfbar sind.

*Verworfen:* Clerk (US-Abhaengigkeit fuer 15 Konten). Keycloak (1 GB RAM fuer 15 Nutzer).

*Kosten:* 0 EUR

#### Observability
**Sentry Cloud Developer (5.000 Errors/Monat gratis) fuer Exceptions. LLM-Traces ab Phase 2 direkt in die eigene Tabelle antwort_log (retrievte chunk_ids mit Scores, prompt_version, model_id, Citations, Verifier-Ergebnis, Kosten)**

*Warum:* Tracing ist hier kein Betriebsthema, sondern das Pruefinstrument der religioesen Nebenbedingung: man muss nachtraeglich belegen koennen, welche Transkriptstellen zu welcher Antwort gefuehrt haben. Diese Daten werden ohnehin in der eigenen DB gebraucht (Cache-Invalidierung ueber antwort_zitat), also gehoeren sie dorthin.

*Verworfen:* Langfuse self-hosted (Postgres + ClickHouse + Redis + S3 — vier Komponenten fuer 1,5 Entwickler). Sentry self-hosted (offizielles Minimum 4 Cores / 16 GB RAM, mehr als die gesamte restliche Plattform). GlitchTip als spaeterer Ersatz vorgemerkt, wenn das Free-Tier reisst.

*Kosten:* 0 EUR

#### Kostenschutz
**Vierfach ab dem Tag, an dem das KI-Tool live geht: (1) harter Tages-Hardcap in EUR in app_config, der bei Erreichen NICHT die Seite abschaltet, sondern nur die Synthese — das Produkt liefert dann weiter Fundstellen; (2) Cloudflare Turnstile vor /ask; (3) Sliding-Window-Rate-Limit per IP und Session; (4) max_tokens-Deckel auf Input und Output**

*Warum:* Ein Bot mit 500.000 Requests ueber Residential-Proxies erzeugt bei Opus ca. 25.000 USD in einer Nacht; IP-Limits allein sind umgehbar. Ein Kostenalarm beim Anbieter feuert erst, wenn das Geld weg ist. Degradation statt Abschaltung haelt das Produkt nutzbar und die Rechnung endlich. Vor dem Launch mit 10.000 Requests gegen den eigenen Endpunkt testen, ob der Cap wirklich greift.

*Verworfen:* Alleiniges Rate-Limiting. Alleiniger Provider-Kostenalarm.

*Kosten:* 0 EUR

---
## Datenmodell

Postgres 17. Tabellen- und Feldnamen folgen bewusst dem Vokabular des Register-Sheets, damit Admin und Datenbank dieselbe Sprache sprechen. Alles mit [P2]/[P3] markierte wird in Phase 1 als Spalte ANGELEGT, aber noch nicht gefuellt — nachtraeglich einzuziehen wuerde eine Vollreindexierung bedeuten.

STAMMDATEN (aus referenz/*.csv und *.yml geseedet, nicht per UI anlegbar)

gelehrter(id PK aus gelehrte.csv, name_ar, name_de, typ enum('person','institution'), gestorben_h, gestorben_g, lebend bool, hinweis)
gelehrter_alias(id PK, gelehrter_id FK, alias, schrift enum('arabisch','latein'))
  -- ابن باز / Ibn Baz / Ibn Baaz / Bin Baz. pg_trgm-GIN-Index. Gelehrtennamen sind ein
  -- Normalisierungs-, kein Retrieval-Problem: nie darauf hoffen, dass das Embedding den Namen trifft.

thema(id PK aus themen.yml, parent_id FK NULL, name_de, name_ar,
      content_class enum('normal','nur_fundstellen','nicht_indexiert') NOT NULL DEFAULT 'normal')
  -- NEUES PFLICHTFELD in themen.yml. Belegung (die Jury nennt das Fehlen in allen drei
  -- Entwuerfen als fatalen Mangel, und themen.yml fuehrt diese Themen heute gleichrangig):
  --   nicht_indexiert : manhaj/jarh-tadil, manhaj/hizbiyya, manhaj/fitan,
  --                     manhaj/takfir, manhaj/wulat-amr
  --   nur_fundstellen : fiqh/talaq, fiqh/mawarith, fiqh/aymaan, fiqh/tibb,
  --                     muasirat/tibb-muasir, aqida/wala-bara
  --   normal          : alles uebrige

glossar(id PK, term_de, term_en, term_ar, hinweis, gepflegt_von)   -- Ziel 300-500 Paare [P2]

EINTRAG (eine Zeile je Register-Zeile)

eintrag(id PK = Eintrags-ID aus dem Register (unveraenderlich, z.B. 'uthaymin-000421'),
  gelehrter_id FK NOT NULL, zuschreibung enum('bestaetigt','wahrscheinlich','unklar') NOT NULL,
  titel_ar, titel_de, frage_ar, quelle_url NOT NULL,
  quelle_typ enum('offiziell','weiterverbreitung','privat','unbekannt') NOT NULL,
  dauer_sek int, aufnahmedatum date NULL, datum_praezision enum('tag','jahr','unbekannt'),
  thema_haupt FK, prio smallint,
  status_ar / status_de / status_en enum('fehlt','maschinell','in_arbeit','eingereicht','nachbesserung','geprueft'),
  bearbeiter_ar / _de / _en, pruefer, geprueft_am,
  sichtbarkeit enum('entwurf','oeffentlich','gesperrt') NOT NULL DEFAULT 'entwurf',
  notizen,
  -- nicht aus dem Register, vom Backend gesetzt:
  drive_file_id, content_sha256 UNIQUE, audio_key, original_key_b2,
  hukm enum('wajib','mustahabb','mubah','makruh','haram','fihi_tafsil','kein_urteil') NULL,   [P2]
  generality enum('allgemein','fallbezogen','unklar') NOT NULL DEFAULT 'unklar',              [P2]
  kontext_notiz_ar NULL, ersetzt_durch FK NULL, ersetzt FK NULL,                              [P2]
  duplikat_von FK NULL, dedupe_gruppe uuid NULL,                                              [P3]
  korpus_version bigint,
  geholt_am, transkodiert_am, asr_fertig_am, geparst_am, indexiert_am, veroeffentlicht_am)

eintrag_thema(eintrag_id, thema_id, herkunft enum('register','llm'), PRIMARY KEY(eintrag_id, thema_id))

hukm ist der Punkt, den alle drei Entwuerfe verfehlt haben und den ANLEITUNG-ADMIN.md bereits
als die folgenschwerste Fehlerquelle benennt: solange das Urteil nur in der Prosa lebt, kippt
es in Index, Reranking und Anzeige mit. Als Enum erfasst, wird es als eigenes Label angezeigt
und ist unabhaengig von der Uebersetzungsqualitaet.

TRANSKRIPT (genau die Struktur der .txt-Dateien)

transkript(id PK, eintrag_id FK, lang char(2), version smallint,
  herkunft enum('asr','mt','mensch'), review_state, erstellt_von, erstellt_am,
  ersetzt_durch FK NULL, basis_transkript_id FK NULL, stale bool DEFAULT false,
  UNIQUE(eintrag_id, lang, version))
  -- basis_transkript_id ist der Versionsanker aus ISNAD: eine neue AR-Version setzt per
  -- Trigger alle daran haengenden Uebersetzungen auf stale=true und erzeugt einen Diff-Review,
  -- der nur die geaenderten Zeilen zeigt. Ohne das verweist de.txt still auf einen korrigierten
  -- arabischen Wortlaut — ein Zuschreibungsfehler, den kein Verifier sieht. Transkripte werden
  -- NIE in place editiert.

zeile(id PK, transkript_id FK, idx int, t_start_ms int NOT NULL,
  text_raw text NOT NULL,
  text_norm text GENERATED ALWAYS AS (normalize_ar(text_raw)) STORED,
  text_anzeige text,            -- text_raw ohne [Anm: ...], mit aufgeloesten Quran-Spans
  hat_unklar bool,              -- enthaelt [...]
  hat_unsicher bool,            -- enthaelt [?]
  hat_anmerkung bool,           -- enthaelt [Anm: ...] -> wird nie ausgeliefert
  sprecher enum('gelehrter','frager','unbekannt') NULL,                                       [P2]
  UNIQUE(transkript_id, idx))
  -- t_end_ms wird NICHT gespeichert, sondern aus t_start_ms der Folgezeile abgeleitet
  -- (bzw. dauer_sek bei der letzten) — so kann es gar nicht inkonsistent werden.
  -- text_raw ist die EINZIGE Quelle fuer Zitate. text_norm existiert nur fuer den Index.
  -- Diese Trennung ab Tag 1, sonst Vollreindexierung.

zitat(id PK, zeile_id FK, art enum('quran','hadith'), span_start int, span_end int,
  sura smallint NULL, aya_von smallint NULL, aya_bis smallint NULL,
  sammlung NULL, nummer NULL, grad NULL, grader NULL, match_score real, gesperrt bool DEFAULT true)

quran_aya(sura, aya, text_uthmani, text_norm GENERATED, PRIMARY KEY(sura,aya))   -- Tanzil, CC BY 3.0
hadith(id PK, sammlung, nummer, text_ar, text_norm GENERATED, grad jsonb)        -- Unlicense

INDEX [P2]

chunk(id PK, eintrag_id FK, gelehrter_id FK, lang char(2),
  zeile_von FK, zeile_bis FK, t_start_ms, t_end_ms,
  text_raw, text_norm, text_embed,          -- text_embed: Quran-Spans durch [قرآن 2:286] ersetzt
  kontext_prefix text NULL, kontext_maschinell bool DEFAULT true,   -- nur Embedding, nie Anzeige
  token_count, korpus_version)
  -- CREATE INDEX chunk_bm25 ON chunk USING bm25 (id, text_norm)
  --   WITH (key_field='id', text_fields='{"text_norm":{"tokenizer":{"type":"icu"},"stemmer":"arabic"}}');

embedding_modell(id PK, name, revision, dim, normalized bool, erstellt_am)
embedding(chunk_id FK, modell_id FK, vec halfvec(1024), PRIMARY KEY(chunk_id, modell_id))
  PARTITION BY LIST (modell_id)
  -- je Partition und Sprache ein Partial Index, CONCURRENTLY und partitionsweise angelegt
  -- (CREATE INDEX CONCURRENTLY ist auf der partitionierten Elterntabelle nicht unterstuetzt):
  --   SET maintenance_work_mem='4GB';
  --   CREATE INDEX CONCURRENTLY ON embedding_m3 USING hnsw (vec halfvec_cosine_ops)
  --     WITH (m=32, ef_construction=200) WHERE lang='ar';
app_config(key PK, value jsonb)
  -- active_embedding_model_id, korpus_version, prompt_version, tages_budget_eur,
  -- abstain_schwelle, cache_cosine_schwelle

Diese Partitionierung wird in Phase 1 mit NULL Zeilen angelegt. Sie ist die eine Entscheidung,
an der Projekte dieser Groesse kaputtgehen, weil der Reindex als Einmalereignis geplant wird:
Embedding-Modelle wechselt man alle 12-18 Monate, und der Wechsel soll eine Partition plus ein
Konfigfeld sein, kein Projektabbruch. Der Reindex selbst kostet bei diesem Korpus unter 1 USD.

DER ZITIERFILTER — die wichtigste Zeile des ganzen Schemas

CREATE VIEW chunks_citable AS
  SELECT c.* FROM chunk c
  JOIN eintrag e ON e.id = c.eintrag_id
  JOIN transkript t ON ...
  JOIN thema th ON th.id = e.thema_haupt
  WHERE e.sichtbarkeit = 'oeffentlich'
    AND e.zuschreibung <> 'unklar'
    AND e.duplikat_von IS NULL
    AND th.content_class <> 'nicht_indexiert'
    AND (c.lang = 'ar' AND e.status_ar = 'geprueft'
      OR c.lang = 'de' AND e.status_de = 'geprueft'
      OR c.lang = 'en' AND e.status_en = 'geprueft');

Der Anwendungsbenutzer bekommt KEIN SELECT auf chunk, eintrag oder transkript — nur auf diese
View. Damit kann der Filter nicht beim naechsten Refactoring aus einer WHERE-Klausel fallen.
Dazu eine Canary-Row: ein Dummy-Eintrag mit sichtbarkeit='entwurf' und einem einzigartigen
Markerstring, nach dem ein stuendlicher Cron sucht; taucht er in Retrieval oder Antwort auf,
Alarm. Ohne diese beiden Massnahmen bricht beim Verlust des Filters nichts, nichts loggt,
die Antworten werden sogar besser — und das System zitiert ungeprefte Maschinenuebersetzung
als Wortlaut des Gelehrten, bis es jemand von aussen oeffentlich macht.

ANTWORTEN UND BETRIEB [P2]

antwort(id PK, art enum('live','vorberechnet'), frage_hash UNIQUE, frage_lang,
  frage_text NULL,            -- NULL ohne ausdrueckliche Einwilligung (Art. 9 DSGVO)
  frage_vec halfvec(1024), inhaltsbegriffe text[], negiert bool, qualifier jsonb,
  body jsonb, abstained bool, abstain_grund, verifier jsonb,
  modell_id, embedding_modell_id, prompt_version, korpus_version,
  review_state, freigegeben_von FK NULL, freigegeben_am, treffer int, invalidiert_am NULL)
antwort_zitat(antwort_id FK, satz_idx int, chunk_id FK, eintrag_id FK, gelehrter_id FK,
  cited_text, char_start, char_end, t_start_ms)   -- GIN-Index: treibt die gezielte Invalidierung
antwort_log(id PK, ts, lang, frage_hash, retrieved_ids bigint[], rerank_ids bigint[],
  abstained, abstain_grund, latenz_ms, tokens jsonb, kosten_usd, cache_level)
  -- enthaelt bewusst KEINEN Fragetext im Klartext und KEINE IP

nachfrage(chunk_id FK, woche date, treffer int, klicks int, PRIMARY KEY(chunk_id, woche))
  -- ISNADs demand_signal: steuert die Review- und Uebersetzungs-Warteschlange und setzt damit
  -- technisch um, was ANLEITUNG-ADMIN.md bereits als Absicht formuliert
  -- ('Uebersetzt wird nach Nachfrage, nicht nach Bestand').

meldung(id PK, ziel_typ enum('antwort','eintrag','zeile','zitat'), ziel_id,
  grund enum('falsche_zuschreibung','uebersetzungsfehler','kontext_fehlt','timestamp_falsch',
             'transkriptionsfehler','sonstiges'),
  notiz, melder_kontakt NULL, state enum('neu','geprueft','bestaetigt','abgelehnt','behoben'),
  bearbeitet_von FK, erstellt_am)

freigabe(id PK, ziel_typ, ziel_id, stufe enum('tadqiq','ijaza'), user_id FK,
  checkliste jsonb NOT NULL, notiz, erstellt_am)
revision_log(id bigserial PK, actor_id, aktion, entity_typ, entity_id, vorher jsonb,
  nachher jsonb, at timestamptz, prev_hash bytea, hash bytea)
  -- append-only per Trigger und entzogenem UPDATE/DELETE-Recht; hash-verkettet;
  -- naechtlicher Export als JSONL nach Git (zugleich Export-First gegen Deplattformierung)
job(id PK, kind, payload jsonb, state, attempts, run_after, locked_until, locked_by, last_error)
app_user(id PK, email UNIQUE, rolle enum('admin','muraji','pruefer','bearbeiter'), lang)

---
## Ingest-Pipeline

Jede Stufe ist ein job-kind, jede idempotent ueber ihren Zeitstempel auf eintrag. Backoff 1/5/25/125 min, max 5 Versuche, danach state='failed' und eine Meldung in die Spalte pipeline_fehler des Register-Sheets — in der Sprache des Bearbeiters, mit konkretem Feld und Korrekturvorschlag, nie ein Stacktrace.

STUFE 0 — REGISTER LESEN (alle 5 Minuten)
Sheets API v4, values.get auf das Register-Blatt. Spaltennamen aus der Kopfzeile, nicht aus Indizes (das Sheet darf Spalten bekommen). Upsert auf eintrag ueber die ID. Validierung je Zeile:
  - id matcht ^[a-z0-9-]+-\d{6}$ und der Praefix steht in gelehrte.csv
  - zuschreibung, quelle_typ, status_*, sichtbarkeit in der erlaubten Werteliste
  - thema_haupt existiert in themen.yml
  - Registerregel 1: status_de/status_en duerfen 'in_arbeit' nur erreichen, wenn status_ar='geprueft'
  - Registerregel 2: sichtbarkeit='oeffentlich' nur wenn zuschreibung<>'unklar' UND status_ar='geprueft'
Beide Regeln werden ZUSAETZLICH als CHECK-Constraint in der DB gefuehrt. Das Sheet kann sie durch Dropdowns nahelegen, erzwingen kann nur die Datenbank. Verletzung = Zeile wird nicht uebernommen, Grund landet in pipeline_fehler.
FEHLER: unbekannte gelehrter-id -> pg_trgm-Vorschlag ("'ibn-uthaimeen' unbekannt — meintest du 'ibn-uthaymin'?").

STUFE 1 — DRIVE ABHOLEN
files.list unter 02_ARCHIV/<gelehrter>/<id>/, supportsAllDrives=true, includeItemsFromAllDrives=true. Nur die fuenf erlaubten Dateinamen (media.mp3|mp4, ar.txt, de.txt, en.txt, quelle.txt), alles andere wird ignoriert und gemeldet. Join ueber die Eintrags-ID und file.id, NIE ueber Dateinamen — Drive erlaubt gleichnamige Dateien im selben Ordner, und arabische Namen kommen je nach Geraet in NFC oder NFD. md5Checksum aus der Drive-API gegen den gespeicherten Wert: unveraendert = nichts tun.
Bei neuem media.*: SHA-256, Kollisionspruefung gegen content_sha256, dann bit-identisch nach Backblaze B2, BEVOR irgendein ffmpeg-Lauf startet. Lossy ist unumkehrbar und der arabische Originalton ist das Beweismittel der Zuschreibung.

STUFE 2 — TRANSKODIERUNG
ffmpeg -i original -vn -c:a libopus -b:a 24k -ac 1 -ar 16000 -application voip -> Hetzner Object Storage.
HARTE REGEL: -ss steht immer HINTER -i, kein Schnitt, kein Normalisieren, kein Trimmen von Intros — DATEIFORMATE.md verbietet den Bruedern dasselbe, und zwar aus demselben Grund. Automatischer Test je Asset: |dauer(opus) - dauer(original)| < 100 ms, sonst Job-Fehler. Alle Zeitmarken beziehen sich auf die AUSGELIEFERTE Datei.

STUFE 3 — ASR (nur wenn status_ar='fehlt' und keine ar.txt existiert)
Soniox async, Diarisierung auf 2 Sprecher constrained, language_hints=['ar']. Aus den Wort-Timestamps werden Zeilen gebildet: neue Zeile bei Sprecherwechsel, bei Pause > 0,6 s, spaetestens nach 12 Sekunden. Ausgabe exakt im Format [HH:MM:SS] Text.
Rueckweg zum Bruder: das Ergebnis wird als ar.txt in den Eintragsordner geschrieben (OAuth-Token eines menschlichen Kontos, deshalb keine Service-Account-Quota-Falle) und status_ar auf 'maschinell' gesetzt. Fallback, falls der Schreibweg klemmt: der Text liegt unter einer stabilen URL, die in der Spalte rohtext_url erscheint, und der Bruder kopiert ihn hinein.
SANITY-CHECKS, hart: keine Zeile mit t_start_ms == t_start_ms der Vorgaengerzeile oder kleiner; keine Zeit > dauer_sek; nicht alle Zeiten 0. Verletzung = Job-Fehler, kein Teilschreiben.

STUFE 4 — PARSEN UND VALIDIEREN (bei jeder Aenderung an ar/de/en.txt)
Zeilenformat ^\[(\d{2}):(\d{2}):(\d{2})\] ?(.*)$. Daraus zeile-Zeilen mit idx und t_start_ms.
Pruefungen, die den Import hart ablehnen:
  - Zeitmarken nicht monoton wachsend
  - de.txt/en.txt hat andere Zeilenzahl als ar.txt  (die Regel steht bereits in ANLEITUNG-ADMIN.md
    als 'automatisch zurueck' — hier wird sie maschinell, bevor der Pruefer seine Zeit verbraucht)
  - Zeitmarken in de/en weichen von ar ab
Markup wird extrahiert, nicht entfernt: [...] -> hat_unklar, [?] -> hat_unsicher, [Anm: ...] -> hat_anmerkung, Text wird aus text_anzeige herausgeschnitten und NIE ausgeliefert. ﴿ ... ﴾ -> Kandidat fuer Stufe 5.
Weicheres Signal, nur als Hinweis an den Pruefer: Zeilen mit hat_unsicher-Quote 0 bei mehr als 40 Zeilen ("ein Bruder, der nie [?] setzt, ist nicht praezise, sondern unaufmerksam" — ANLEITUNG-ADMIN.md).

STUFE 5 — QURAN/HADITH AUFLOESEN
Nur innerhalb der ﴿ ﴾-Marker: Levenshtein mit Moving Pointer gegen quran_aya.text_norm, Schwelle 85 %, zweite Schicht Ratcliff/Obershelp. Treffer -> exakter Uthmani-Rasm inkl. Diakritika in text_anzeige, zitat-Zeile mit Sura:Aya, Span gesperrt. Unter der Schwelle: kein Link, Hinweis an den Pruefer. Lieber kein Link als ein falscher — ein falsch verlinkter Vers ist eine falsche Zuschreibung.

STUFE 6 — STATUS ZURUECKSCHREIBEN
values.update auf vier neue Spalten des Registers: pipeline_status (geholt | transkribiert | geparst | indexiert | fehler), pipeline_fehler (Klartext), rohtext_url, geprueft_url (Link auf die oeffentliche Seite, sobald sie existiert). Ein Rate-Limit-Puffer sammelt Aenderungen und schreibt gebuendelt alle 5 Minuten.

STUFE 7 — VEROEFFENTLICHEN
eintrag.veroeffentlicht_am setzen, korpus_version++, revalidatePath fuer /[locale]/e/[id] und die betroffenen Themen- und Gelehrtenseiten. Ab Phase 2 zusaetzlich: UPDATE antwort SET invalidiert_am=now() WHERE id IN (SELECT antwort_id FROM antwort_zitat WHERE eintrag_id = :id) — praezise Invalidierung statt globalem Flush.

STUFE 8 — MT-ROHUEBERSETZUNG [P2, erst wenn status_ar='geprueft']
Haiku 5.5 Batch, zeilenweise, +/-3 Zeilen Kontext, Glossar im gecachten System-Prompt. Ausgabe muss exakt so viele Zeilen haben wie die Eingabe, sonst Job-Fehler. Schreibt de.txt/en.txt in den Eintragsordner, setzt status_de/_en auf 'maschinell'. Danach Haiku-Screening auf genau zwei Dinge: Urteilsstaerke (haram/makruh/mustahabb/wajib/mubah) und weggefallene Konditionale; markierte Stellen landen als Hinweis in notizen.

STUFE 9 — CHUNKEN UND EMBEDDEN [P2]
Chunk-Grenzen folgen der Frage-Antwort-Einheit, nicht einer Tokenzahl. In Phase 2 ist ein Eintrag per Register-Konvention in der Regel eine Fatwa, also ein Parent; innerhalb davon Children von max. 500 Token mit 80 Overlap an Zeilengrenzen. Quran-Spans im Embedding-Text durch Platzhalter ersetzt (sonst clustert Dense-Retrieval auf das Zitat statt auf die Frage, und die Top-10 sind zehnmal dieselbe Ayah aus zehn Kontexten). BGE-M3 fuer lang in (ar, de, en), nur fuer geprueftes Material.

---
## Retrieval-Pipeline

Gilt ab Phase 2. Budget bis Quellenliste 0,6-1,1 s. Alle Zahlen sind Startwerte, die gegen eval/goldset.yaml kalibriert werden — ohne eigenes Goldset ist jede Modellwahl Glaube.

SCHRITT 1 — Query-Verstehen (Haiku 5.5, Structured Output, ca. 250 ms, 0,0003 USD)
Output: {lang, intent, inhaltsbegriffe[], ar_terme[], gelehrter_slug|null, thema_slug|null, negiert bool, qualifier{reise, geschlecht, notlage, verwendung, ...}, ich_form bool}
qualifier und negiert sind nicht nur fuer den Cache da (so machen es alle drei Entwuerfe), sondern gehen als Filter- und Rankingsignal in das Retrieval: sonst sind die Top-8 fuer "ist X erlaubt" und "ist X verboten" identisch, und die strukturellen Schutzmassnahmen greifen erst, nachdem das Modell die falsche Evidenzmenge bekommen hat.

SCHRITT 2 — HARTES ROUTING, vor jedem Retrieval
(a) intent='personenurteil' (Fragen der Form "was hat X ueber Y gesagt", "ist Z ein Mubtadi") -> keine Suche, feste Antwort mit Verweis auf die Gelehrten. Begruendung unten in integritaetUndReview.
(b) thema_haupt oder thema_unter hat content_class='nicht_indexiert' -> dasselbe.
(c) content_class='nur_fundstellen' ODER ich_form=true mit Sachverhaltsschilderung -> Suche laeuft, aber die Synthese wird abgeschaltet: nur Fundstellen plus der feste Satz "Dies ist ein Einzelfall, der eine Ruecksprache mit einem Gelehrten oder einem kundigen Imam erfordert."
(d) intent='existenzfrage' ("hat X jemals gesagt, dass ...") -> keine Synthese, nur Fundstellen plus Abdeckungsangabe.

SCHRITT 3 — Glossar-Expansion (deterministisch, < 5 ms)
inhaltsbegriffe gegen glossar gematcht -> zusaetzliche ar_terme. 300-500 handgepflegte Paare, von den Bruedern wartbar. Billiger, deterministischer und revisionssicherer als maschinelle Query-Uebersetzung, die bei religioeser Terminologie fehleranfaellig ist (Gebet -> صلاة vs. دعاء). Entschaerft zugleich den dokumentierten Reranker-Einbruch bei sehr kurzen nicht-lateinischen Queries — und "Musik haram?" ist der Normalfall.

SCHRITT 4 — Transliterationsnormalisierung (< 5 ms)
Lateinisch geschriebenes Arabisch ist bei deutsch- und englischsprachigen Nutzern der Normalfall der Fachbegriffseingabe ("wudu", "tayammum", "masah ala l-khuffain", "hal yajuz") und trifft weder den BM25-Pfad (text_norm ist arabische Schrift) noch zuverlaessig den Dense-Pfad. Keiner der drei Entwuerfe behandelt das. Loesung: das Glossar bekommt eine vierte Spalte term_translit mit mehreren Schreibvarianten je Begriff, plus eine Soundex-aehnliche Reduktion (Vokale weg, dh/th/kh/gh/sh als Einheiten, Verdopplungen kollabiert) als Lookup-Key.

SCHRITT 5 — Vier parallele Pfade, je top-30, EIN SQL-Statement mit CTEs (40-120 ms)
  A) dense, Fragesprache  : HNSW WHERE lang=query_lang, ef_search=120
  B) dense, arabisch      : HNSW WHERE lang='ar' (bei query_lang='ar' faellt A weg, B bekommt top-60)
  C) BM25 arabisch        : pg_search @@@ text_norm mit ar_terme + Originaltokens
  D) BM25 Fragesprache    : pg_search auf den Uebersetzungs-Chunks
Alle vier lesen AUSSCHLIESSLICH aus chunks_citable. Zusaetzlicher Filter: thema.content_class='normal', zeile.hat_unklar-Quote des Chunks < 20 %.
Bei hochselektiven Filtern (ein Gelehrter, < 0,5 % der Zeilen) wird der ANN-Index uebersprungen und exakt gescannt — bei diesem Korpus ist Brute-Force ueber ein paar tausend gefilterte Zeilen einstellig in Millisekunden und liefert perfekten Recall. Bei unselektiven Filtern hnsw.iterative_scan='relaxed_order' und hnsw.max_scan_tuples=40000; ohne das liefert eine gefilterte ANN-Abfrage STILLSCHWEIGEND zu wenige Treffer, und das sieht auf einer Fatwa-Seite aus wie duenne Quellenlage statt wie ein Indexfehler.

SCHRITT 6 — Sprachbalance und Fusion
Cap von 50 % je Sprache auf die Kandidatenliste VOR der Fusion (gegen den Same-Language-Bias: multilinguale Retriever liefern fuer arabische Testsets 80,8 % gleichsprachige Dokumente, eine deutsche Frage wuerde sonst die bessere arabische Originalstelle begraben).
Gewichtetes RRF, k=60: score = 1,2/(60+rank_C) + 1,0/(60+rank_B) + 1,0/(60+rank_A) + 0,9/(60+rank_D).
BM25 hoeher gewichtet, weil woertliche Zitate und Eigennamen lexikalische Treffer sind. RRF statt Score-Normalisierung, weil BM25-Scores und Cosine-Distanzen auf unvergleichbaren Skalen leben und jede Normalisierung korpusabhaengig ist und bricht, sobald neue Eintraege dazukommen.
Multiplikative Signale: zuschreibung='wahrscheinlich' -> x 0,9; generality<>'allgemein' -> x 0,95; negiert stimmt nicht mit der Polaritaet des Chunk-hukm ueberein -> x 0,7.

SCHRITT 7 — Dedup und Parent-Expansion
Gruppierung ueber dedupe_gruppe; pro Gruppe bleibt der Primaer. WICHTIG und in allen drei Entwuerfen ungeloest: der Deep-Link zeigt dann auf eine andere Aufnahme mit anderer Zeitachse. Regel hier: der Deep-Link bleibt IMMER an dem Eintrag, aus dem der Treffer stammt; der Gruppenprimaer wird nur als "laengere Aufnahme derselben Antwort" zusaetzlich verlinkt, ohne Zeitsprung. Dann gibt es kein Alignment-Problem zwischen zwei Aufnahmen.
Danach Child -> Parent: an das LLM geht die ganze Frage-Antwort-Einheit plus frage_ar, kontext_notiz_ar, aufnahmedatum, quelle_url.

SCHRITT 8 — Reranking (Voyage rerank-3-lite, 150-400 ms)
Top-40 Kandidaten, jeder zweimal gescort (AR-Original und Uebersetzung in Fragesprache), final = max(beide), beide Werte in antwort_log. Ausschliesslich auf text_raw, nie auf text_norm — die Normalisierung kollabiert ة→ه und echte Bedeutungsunterschiede, das wuerde sich sonst potenzieren. Ergebnis: top-8.

SCHRITT 9 — ZWEI SCHWELLEN STATT EINER
Die gefaehrlichste Zone ist nicht der leere Treffer (da greift Abstain), sondern der knapp ueberschwellige: eine Gharar-Randbemerkung von 1994 auf eine Krypto-Frage, vom Reranker gehoben, weil sie das Beste ist, was da ist. Durch Name, Zitat und Timestamp wirkt sie autoritativer als jede Google-Suche.
  score >= 0,55  -> Synthese
  0,35 bis 0,55  -> NUR Fundstellen, mit dem Hinweis "Die gefundenen Stellen beruehren das Thema, beantworten die Frage aber nicht direkt."
  < 0,35         -> Abstain
Zusaetzlich unabhaengig vom Score: wenn thema_haupt der Frage nicht zu den Themen gehoert, zu denen der Korpus tatsaechlich geprueftes Material hat, harter Abstain. Die Themenliste existiert ohnehin fuer die Bibliothek.
Weiter abstained wird bei: weniger als 2 Kandidaten ueber 0,55; allen Treffern von genau einem Gelehrten bei intent='fiqh_ruling' und weniger als 3 Treffern (dann Synthese MIT dem Hinweis "Hier liegt nur die Aussage von X vor").

SCHRITT 10 — Shadow-Abfrage, folgenlos
Dieselbe Fusion laeuft asynchron ueber ungepreftes Material (status_ar <> 'geprueft'). Das Ergebnis wird NIE angezeigt und NIE zitiert; es inkrementiert nachfrage und erzeugt im UI hoechstens "Es gibt N weitere, noch nicht geprefte Aufnahmen zu diesem Thema". Damit steuert die reale Nutzung die Review-Reihenfolge — die Umsetzung dessen, was ANLEITUNG-ADMIN.md als Prioritaetsregel bereits vorschreibt.

EVALUATION
eval/goldset.yaml: 150 echte Fragen (je 50 AR/DE/EN) mit handannotierten erwarteten eintrag-IDs, graduiert 0-3, erstellt von zwei Bruedern an zwei Nachmittagen. Plus 50 Negativfragen zu Themen, die bewusst nicht im Korpus sind. Plus 30 Minimalpaare (musafir/muqim, haid/tahir, Schmuck/Wertanlage, erlaubt/verboten), die gegen Retrieval UND Cache gefahren werden.
`make eval` als Skript, nicht als CI-Gate mit Regressionsblockade — bei 1,5 Entwicklern ist der Apparat teurer als der Nutzen. Berichtet werden Recall@30, nDCG@10, abstain_correct auf den Negativfragen, attribution_precision, und zwingend die Aufschluesselung nach Richtung (ar->ar, de->ar, en->ar, de->de): ein guter Mittelwert kann den Einbruch genau in der kritischen Richtung verdecken. Zielmarke zur Orientierung: jina-reranker-m0 erreicht auf MIRACL Arabisch 79,78 nDCG@10.

---
## Antwort-Pipeline

ZWEI CALLS, nicht einer: citations.enabled=true und output_config.format zusammen geben bei Anthropic einen 400-Fehler. Call 1 nutzt Citations, Call 2 nutzt Structured Output.

CALL 1 — SYNTHESE (claude-sonnet-5-5, effort='high', max_tokens 900)
Die Chunks werden NICHT als Prompttext eingebettet, sondern als search_result-Content-Blocks in der User-Message (nur dort erlaubt; Assistant-Messages mit search_result werden abgelehnt):
  { type: "search_result",
    source: "https://<domain>/e/<eintrag-id>?t=<sek>",
    title: "<Gelehrter> — <Thema> — <Datum> — <Quelle> — <zuschreibung>",
    content: [{type:"text", text:"Frage: <frage_ar>\n\n<Antwort AR>\n\n[DE] <Uebersetzung>"}],
    citations: {enabled: true},
    cache_control: {type:"ephemeral"} }
EIN BLOCK PRO GELEHRTEM. Chunks verschiedener Gelehrter landen nie im selben Block. Das ist die erste von drei strukturellen Massnahmen gegen den teuersten Fehler des Projekts — die erfundene Synthese zwischen zwei Gelehrten — und sie wirkt dort, wo ein Prompt nicht wirkt.

SYSTEM-PROMPT (prompts/synthese.v1.md, versioniert, prompt_version auf jeder Antwort):
 1. Du bist kein Mufti. Du gibst keine eigene Fatwa, kein Ijtihad, keinen Qiyas, kein Tarjih.
 2. Du sagst ausschliesslich, was in den gelieferten Quellen steht. Was nicht drinsteht, gibt es fuer dich nicht.
 3. Jede Position gehoert genau einem namentlich genannten Gelehrten. Es gibt keine Formulierung "die Gelehrten sagen" und kein "der Islam sagt".
 4. Der Dalil, den du nennst, ist der, den DIESER Gelehrte in DIESER Aufnahme genannt hat — nicht der, den du kennst.
 5. Traegt eine Quelle den Hinweis fallbezogen, nennst du die Situation im selben Satz.
 6. Widersprechen sich zwei Gelehrte, stellst du beide nebeneinander, ohne zu gewichten.
 7. Reicht die Grundlage nicht, sagst du das und hoerst auf. Das ist die richtige Antwort, keine Niederlage.
 8. Das Urteil nennst du mit dem Fachbegriff und seiner Erklaerung (makruh = verpoent, aber nicht verboten), nie nur mit dem deutschen Wort.

ERZWUNGENES FORMAT, als Struktur vorgegeben:
  ## Kurzantwort        (2-3 Saetze, nur Unstrittiges)
  ## Positionen
     ### <Gelehrtenname>
       Urteil: <hukm-Label aus der Datenbank, nicht vom Modell erfunden>
       Position: ...
       Dalil laut dem Gelehrten: ...
       Kontext: <kontext_notiz_ar oder "nicht naeher eingegrenzt">
  ## Was hier nicht vorliegt   (nur wenn relevant)
Es gibt kein Feld fuer eine kollektive Meinung im Singular — also kann das Modell dort nichts hineinschreiben. Zweite strukturelle Massnahme. Dritte: eine Regex-Blockliste auf kollektive Formulierungen ("die Gelehrten", "man ist sich einig", "nach Ansicht der Gelehrten") als letzte Schranke vor der Auslieferung.

ZITATANKER: Die API liefert pro Textblock ein citations-Array mit source, title, cited_text und Zeichen-Offsets. Das Backend mappt source -> eintrag_id + t_start_ms und schreibt antwort_zitat. Es wird NIE Freitext nach Zitatmarkern geparst. cited_text zaehlt weder als Output- noch spaeter als Input-Token — Zitieren ist hier billiger als Prompten.
ORIGINALWORTLAUT: unter jeder Position steht der arabische Ausschnitt aus text_anzeige aufklappbar, in jeder Sprachversion, immer. Das ist keine UI-Frage, sondern die Rueckfallebene, wenn die Uebersetzung falsch ist.

CALL 2 — VERIFIER (claude-haiku-5-5, Structured Output, keine Citations, ca. 0,0015 USD)
Input: die Antwort satzweise zerlegt plus alle Chunks mit chunk_id, eintrag_id, gelehrter_id, generality.
Output: {saetze: [{idx, gedeckt bool, chunk_ids[], gelehrter_behauptet, kontext_noetig bool, kontext_genannt bool}]}
Danach eine DETERMINISTISCHE Pruefung in Python, nicht im Modell:
  (a) Textdeckung — ist der Satz durch mindestens einen Chunk gedeckt?
  (b) ATTRIBUTIONSDECKUNG — gehoert mindestens eine stuetzende chunk.gelehrter_id zur genannten? Ein Satz, der Ibn Baz zugeschrieben ist, aber nur durch einen al-Albani-Chunk gedeckt wird, faellt durch. Entailment allein faengt genau diesen Fehler NICHT, denn der Satz kann vollstaendig gedeckt und trotzdem falsch zugeschrieben sein. Mit Metadaten ist die Pruefung trivial, mit einem NLI-Encoder unmoeglich.
  (c) KONTEXTDECKUNG — traegt ein zitierter Chunk generality='fallbezogen', muss der Satz die Situation nennen.

DURCHFALL-REGELN
  ein 'misattributed' -> Antwort wird VOLLSTAENDIG verworfen, Abstain-Variante ausgeliefert, Alarm im Dashboard
  ein 'kontext fehlt' -> dasselbe
  'uncovered' bei <= 20 % der Saetze -> betroffene Saetze entfernt, Rest ausgeliefert
  darueber -> Abstain
Eine Antwort, die den Verifier nicht besteht, wird NIE in den Cache geschrieben.

ABSTAIN-TEXT (fest formuliert, nicht generiert)
"Zu dieser Frage liegen in diesem Archiv keine ausreichend klaren Aussagen vor. Das Archiv enthaelt derzeit N geprefte Aufnahmen und ist nicht vollstaendig — die Abwesenheit hier ist keine Aussage darueber, ob ein Gelehrter sich geaeussert hat. Unten findest du, was wir zum Thema haben. Bitte frage einen Gelehrten."
Der zweite Satz ist nicht Hoeflichkeit: ohne ihn liest der Nutzer "er hat es nie gesagt", macht einen Screenshot und postet ihn als Beweis. Auf jeder Gelehrtenseite steht zusaetzlich ein Abdeckungsindikator (N Aufnahmen, M Stunden, welche Themenbereiche).

STREAMING (SSE auf POST /ask), Eventreihenfolge:
  event: sources   -> die Fundstellen mit Gelehrtem, Datum, Deep-Link, arabischem Snippet, zuschreibung, Uebersetzungsstatus   [0,6-1,1 s]
  event: notice    -> KI-Hinweis nach Art. 50 AI Act, Routing-Hinweise, Warnung bei ungeprefter Uebersetzung
  event: token     -> die Synthese, im UI gedaempft mit "wird geprueft"
  event: citations -> die aufgeloesten Anker
  event: verdict   -> verified | partial | retracted; bei retracted ERSETZT das UI den Text sichtbar durch die Fundstellenliste
Die Quellen kommen vor der Zusammenfassung. Das kaschiert nicht nur Latenz, es ist die Produktaussage: die Fatawa sind primaer, die Zusammenfassung ist sekundaer.
Caddy braucht X-Accel-Buffering: no bzw. proxy_buffering off, sonst stapeln sich die Tokens hinter dem Puffer und kommen als ein Block.

PFLICHTHINWEIS, dauerhaft sichtbar im Chatfenster (Art. 50 EU AI Act seit 02.08.2026; ein Satz in den AGB genuegt ausdruecklich nicht):
"Dies ist ein Suchwerkzeug, kein Mufti. Es gibt keine Fatwa, sondern zeigt, was die Gelehrten in den hinterlegten Aufnahmen gesagt haben."

---
## Caching und Vorberechnung

Drei Stufen, alle in der Postgres-Tabelle antwort. Kein Redis fuer Antworten: eine freigegebene Antwort mit ihren Zitaten ist kein fluechtiger Key-Value-Eintrag, sondern ein reviewtes Artefakt mit freigegeben_von, das transaktional zu seinen Quellen gehoert. Bei LLM-Latenzen in Sekunden ist der Unterschied zwischen 0,3 ms Redis und 2 ms Postgres irrelevant. Redis kommt nur fuer Rate-Limiting und, ab zwei App-Instanzen, als ISR-Cache-Handler.

L0 — EXAKT-CACHE
frage_hash = sha256(normalize_query(text) || lang || embedding_modell_id || modell_id || prompt_version || korpus_version || filter_hash). Lookup < 5 ms. Jeder Bestandteil ist bewusst drin: ein Modellwechsel, eine Prompt-Aenderung oder eine Korpusaenderung invalidieren den Cache automatisch, ohne dass jemand daran denken muss. Erwartet 15-25 % Trefferquote, weil geteilte Links denselben Wortlaut tragen.

L1 — KURATIERTER POOL (die wichtigste Stufe)
Vorab erzeugte und MENSCHLICH FREIGEGEBENE Antworten auf die haeufigsten Masail. Treffer bei cosine >= 0,93 UND Jaccard der Inhaltsbegriffe >= 0,6 UND identischer qualifier-Menge. Die Schwelle darf hier niedriger sein als bei L2, weil ein Mensch die Antwort freigegeben hat und weil das UI die kanonische Frage sichtbar macht: "Du hast gefragt: <q>. Wir zeigen dir unsere geprefte Antwort auf: <kanonische Frage>." Der Nutzer sieht damit selbst, ob es passt.
Erzeugung mit claude-opus-5-5 ueber die Batch-API (50 % Rabatt, stapelt mit Prompt-Caching), effort='high'. Hier lohnt das beste Modell, weil die Kosten einmalig sind und diese Antworten die meistgesehenen werden. 500 Fragen x 3 Sprachen x ca. 0,028 USD = ca. 42 USD einmalig.
Quelle der Fragenliste: (a) die haeufigsten echten Fragen aus antwort_log (nur frage_hash plus inhaltsbegriffe, nie der Rohtext), (b) eine von den Bruedern kuratierte Liste klassischer Masail in data/vorberechnete_fragen.yaml.
HARTE REGEL: art='vorberechnet' wird NICHT ausgeliefert, bevor ein Nutzer mit Rolle 'muraji' sie freigegeben hat. Vorher faellt die Frage auf den Live-Pfad zurueck. Das ist der Punkt, an dem Vorcachen aufhoert, eine Kostenoptimierung zu sein: es ist die einzige realistische Moeglichkeit, Antworten VOR der Auslieferung von einem Bruder mit Ilm gegenlesen zu lassen. Eine gecachte Antwort ist faktisch eine Veroeffentlichung unter dem Namen des Projekts.

L2 — SEMANTISCHER CACHE (die gefaehrlichste Stufe, deshalb streng)
Treffer nur wenn ALLE vier Bedingungen gelten:
  cosine(frage_vec, cached.frage_vec) >= 0,97
  UND jaccard(inhaltsbegriffe) >= 0,80
  UND negiert identisch
  UND qualifier-Menge identisch
Der uebliche Default 0,95 ist fuer Produkt-FAQs kalibriert, nicht fuer Fiqh: hier entscheidet oft ein einziges Wort ueber eine andere Antwort — musafir vs. muqim, haid vs. tahir, Gold als Gebrauchsschmuck vs. als Wertanlage, mit Niyya vs. ohne. Embeddings sind bei Verneinung notorisch schwach, "ist X erlaubt" und "ist X verboten" liegen gefaehrlich nah; deshalb ist negiert ein hartes Gate und kein Score-Beitrag.
Jeder Hit wird mit beiden Fragen und dem Score geloggt. Woechentlich prueft ein Bruder 50 Stichproben. Ein falscher Cache-Hit ist hier keine schlechte Suchantwort, sondern eine falsch zugeschriebene Fatwa — und zwar monatelang, weil nichts sie invalidiert.

PROMPT-CACHING (L3, eigentlich eine Modell-Ebene)
System-Prompt, Glossar und die haeufigsten Chunks mit cache_control. Cache-Read kostet 0,05x des Input-Preises (Sonnet 0,10 USD/1M). Bei ca. 6.000 von 14.000 stabilen Input-Token senkt das die Synthesekosten um ca. 32 %. Voraussetzung ist ein stabiler System-Prompt — wer das Glossar bei jeder Anfrage dynamisch zusammenbaut, zerstoert den Cache-Hit und merkt es nur an der Rechnung.

INVALIDIERUNG — gezielt, nie global
antwort_zitat traegt eintrag_id und chunk_id mit GIN-Index. Drei Ausloeser:
  (a) Veroeffentlichung oder Korrektur eines Eintrags:
      UPDATE antwort SET invalidiert_am=now() WHERE id IN (SELECT antwort_id FROM antwort_zitat WHERE eintrag_id = :id)
  (b) Modellwechsel: automatisch ueber den Cache-Key
  (c) prompt_version-Aenderung: dito
HARTE AUSNAHME: wird ein Eintrag auf sichtbarkeit='gesperrt' gesetzt oder eine Meldung bestaetigt, laeuft die Invalidierung SYNCHRON in derselben Transaktion ueber alle drei Stufen plus den ISR-Cache des Frontends — ausdruecklich kein Batch-Job, Ziel unter 60 Sekunden. Das ist der Grund, warum Antwort-Cache und Korpus in derselben Datenbank liegen muessen.
Naechtlicher Cron zusaetzlich: vorberechnete Antworten, deren Retrieval sich geaendert haette (Top-8 weicht um mehr als 3 Positionen ab), fallen auf review_state='unreviewed' zurueck und gehen erneut zur Freigabe.

TTL 180 Tage plus naechtlicher Aufraeumjob, weil Postgres kein eingebautes TTL hat.

WIRKUNG: Bei 10.000 Fragen/Monat und 50 % Gesamttrefferquote kostet die Synthese 113 statt 226 EUR. Jeder Prozentpunkt ist ca. 2,30 EUR wert; bei 50.000 Fragen ca. 11,50 EUR. Der Cache ist damit nicht UX-Politur, sondern das zentrale Kostenventil — und in der L1-Stufe gleichzeitig der Qualitaetsmechanismus.

---
## Integrität und Review

Die Zustandsmaschine ist die des bestehenden Registers, nicht eine neue. Sie wird nur maschinell erzwungen statt per Anleitung nahegelegt.

ZUSTANDSMASCHINE (pro Sprache, aus REGISTER.md)
  fehlt -> maschinell -> in_arbeit -> eingereicht -> geprueft
                             ^              |
                             +-- nachbesserung
Zwei Registerregeln als CHECK-Constraint, nicht als Konvention:
  R1: status_de/status_en duerfen 'in_arbeit' erst erreichen, wenn status_ar='geprueft'.
  R2: sichtbarkeit='oeffentlich' nur wenn zuschreibung <> 'unklar' UND status_ar='geprueft'.
Zustandsuebergaenge nur ueber eine SQL-Funktion, die revision_log schreibt. Ein Eintrag mit zuschreibung='unklar' kann nicht veroeffentlicht werden, auch nicht durch einen UPDATE von Hand.

SICHTBARKEITS-TIERS (ISNADs shadow/verified, auf die vorhandenen Felder abgebildet)
  verified : sichtbarkeit='oeffentlich' UND status_<lang>='geprueft'
             -> in der Bibliothek, im Index, woertlich zitierbar durch das KI-Tool
  shadow   : alles andere mit zuschreibung<>'unklar'
             -> in der Bibliothek SICHTBAR mit deutlichem Banner ("maschinell transkribiert,
                nicht geprueft"), NICHT im Zitierindex, zaehlt nur nachfrage
  gesperrt / unklar : gar nicht
Das ist die einzige ehrliche Antwort darauf, dass ein Vollreview unerreichbar ist. Die eigene Rechnung des Projekts (3.000 Videos = ca. 4.000 Mannstunden = zwei Jahre bei zehn Bruedern) macht jede Architektur, die vollstaendig geprueftes Material voraussetzt, zu einer Architektur, die nie live geht. Die Nutzung selbst priorisiert dann den Review: was oft gesucht wird, wird zuerst geprueft.

INGEST-DROSSEL
Pro Woche duerfen nur so viele Eintraege neu registriert werden, wie in derselben Woche auf status_ar='geprueft' gewandert sind, mal zwei. Harte Regel im Admin-Dashboard. Das fuehlt sich falsch an und verhindert den Zustand, in dem das Projekt typischerweise stirbt: zu gross zum Pruefen, zu klein zum Nuetzen.

ROLLEN UND FREIGABE
admin | muraji | pruefer | bearbeiter. Nur muraji kann vorberechnete Antworten freigeben. Vier-Augen gilt fuer das, was das KI-Tool zitieren darf: bearbeiter <> pruefer, erzwungen als CHECK. Eine dritte Instanz (ijaza) wird NICHT als unbedingter Constraint gefuehrt — bei zehn Freiwilligen und einem Pruefer wuerde das den Durchsatz dritteln, der ohnehin der Engpass ist. Stattdessen: ijaza nur fuer vorberechnete Antworten und fuer Eintraege mit content_class='nur_fundstellen'.

FREIGABE-CHECKLISTE (freigabe.checkliste jsonb, jeder Haken einzeln gespeichert)
Inhaltlich identisch mit ANLEITUNG-ADMIN.md, nur protokolliert statt erinnert:
  [ ] Gelehrter korrekt zugeordnet (Stimme oder Quelle geprueft)
  [ ] Quelle und Original-URL stimmen, quelle_typ korrekt
  [ ] Drei Zeitmarken stichprobenhaft angesprungen und korrekt
  [ ] Alle [?] und [...] durchgegangen
  [ ] Quranverse in ﴿ ﴾ gesetzt und korrekt aufgeloest
  [ ] Nicht geglaettet (Wiederholungen, Anreden, Fuellwoerter noch da)
  [ ] Urteilsbegriffe geprueft, hukm gesetzt
  [ ] Bedingungen als Bedingungen erhalten
  [ ] generality gesetzt (allgemein / fallbezogen)
Der Freigabe-Button bleibt deaktiviert, bis alle Haken sitzen, und darunter steht sichtbar "Du gibst dies unter deinem Namen frei: <Name>".

SITUATIONSBINDUNG — ein Datenmodellproblem, kein Retrievalproblem
generality ist Pflichtfeld der Freigabe, Default 'unklar', nie allein maschinell gesetzt. Chunks mit generality <> 'allgemein' duerfen nur ausgegeben werden, wenn frage_ar mitgeliefert und in der UI ueber der Antwort angezeigt wird; der Verifier erzwingt zusaetzlich, dass der Satz die Situation nennt. Der Deep-Link setzt immer 20 Sekunden VOR den Chunk, nie auf dessen Anfang, damit der Nutzer die Frage noch hoert. Ohne diese Felder produziert auch ein perfektes Retrieval korrekt zitierte, trotzdem irrefuehrende Antworten.

RUJU UND WIDERSPRUCH
Felder ersetzt/ersetzt_durch plus ein automatischer Konfliktdetektor: gleicher Gelehrter, gleiches Unterthema, Datumsabstand > 3 Jahre, widersprechendes hukm -> Eintrag in die Pruefliste. Bis zur Klaerung werden BEIDE Fundstellen mit Datum nebeneinander gezeigt und KEINE Synthese erzeugt. Ein leeres Feld ist keine Loesung; ohne Detektor bleibt es leer. aufnahmedatum wird damit zum Pflichtfeld fuer Konfliktfaelle — ein undatierter Eintrag darf dort nicht zitiert werden.
Das System gewichtet grundsaetzlich nicht und macht kein Tarjih. Es gibt eine redaktionell gepflegte Anzeigereihenfolge (Lajna ad-Daima vor Einzelfatwa), die im UI als solche beschriftet wird ("Reihenfolge nach redaktioneller Gewichtung — alle Positionen werden gezeigt"). Sie fliesst NICHT in den Retrieval- oder Rerank-Score ein; eine automatische Gewichtung waere verdecktes Tarjih.

THEMEN-SPERRE (content_class in themen.yml)
Das ist die wichtigste Einzelmassnahme des Produkts und fehlte in allen drei Entwuerfen — besonders gravierend, weil themen.yml jarh-tadil, takfir, wala-bara, hizbiyya, fitan und wulat-amr heute als gleichrangige Unterthemen fuehrt, die Taxonomie den Korpus also aktiv dorthin einlaedt.
  nicht_indexiert : Personenbewertungen und innerinnerlicher Streit. Das Material kommt gar nicht
    erst in den Index. Begruendung: ein Tool, das auf Knopfdruck uebersetzte, nach Relevanz
    sortierte Munition mit Deep-Link liefert, wird binnen Wochen von einer Fraktion vereinnahmt,
    spaltet die Zulieferer und verbreitet, wenn die bewertete Person in Deutschland lebt, eine
    uebersetzte ehrenruehrige Tatsachenbehauptung als EIGENEN Inhalt — §§ 7-10 DDG greifen nicht.
  nur_fundstellen : Talaq, Erbrecht, Geluebde, medizinische Fragen, Wala wa Bara. Diese Fragen
    haengen an Formulierung, Zustand und Absicht; ohne Rueckfragen ist jede Antwort falsch. Sie
    sind zugleich der haeufigste Grund, warum Menschen Fatwa-Seiten aufsuchen, und das Erste,
    was ein Journalist testet.
Zusaetzlich greift die Ich-Form-Heuristik unabhaengig vom Thema.

NER-GATE FUER LEBENDE PERSONEN
Vor jeder Veroeffentlichung laeuft ein NER-Durchlauf ueber text_anzeige. Personennamen ausserhalb von gelehrte.csv und einer Ueberliefererliste sperren den Eintrag, bis ein Mensch entschieden hat. Fuer lebende Personen gilt pauschal: keine Uebersetzung, keine Indexierung, kein Zitat. Das ist die Massnahme, die die einstweilige Verfuegung verhindert — das wahrscheinlichste juristische Einzelereignis des Projekts, wahrscheinlicher als jede Urheberrechtsfrage.

MELDEFUNKTION
Melde-Button an jeder Antwortkarte, jeder Transkriptzeile und jeder Uebersetzung mit sechs festen Gruenden. Eine Meldung von pruefer/muraji ODER zwei unabhaengige Meldungen setzen den Eintrag in derselben Transaktion auf sichtbarkeit='gesperrt', nehmen ihn aus dem Index und invalidieren alle Antworten, die ihn zitieren. Triage innerhalb 72 h. Ergebnis: wieder oeffentlich mit Notiz, neue Version, oder dauerhaft gesperrt — und gesperrt laesst die URL bestehen mit einer sichtbaren Erklaerung, weil stilles Verschwinden selbst ein Vertrauensbruch ist. Billigster Qualitaetsmechanismus im Projekt: eine Tabelle, ein Endpunkt, ein Button — und er laesst die Nutzer einen Teil der fehlenden Review-Kapazitaet ersetzen.

TIMESTAMP-INTEGRITAET, LAUFEND
Alle drei Entwuerfe pruefen nur beim Ingest. Hier zusaetzlich ein taeglicher Cron: 50 zufaellige Zeilen ziehen, das Audio ab t_start_ms fuer 10 Sekunden erneut durch Soniox schicken, fuzzy gegen die ersten Woerter matchen, unter 70 % Uebereinstimmung Alarm. Kosten: wenige Cent pro Tag. Drift entsteht nicht nur beim Import, sondern auch durch spaetere Transkodierung und Korrekturlaeufe — und der Deep-Link ist das Vertrauensmerkmal, auf dem die ganze Produktidee ruht.

AUDIT UND EXPORT-FIRST
revision_log append-only und hash-verkettet, Kopf-Hash taeglich nach Git. Naechtlicher Export aller Metadaten, Transkripte und Uebersetzungen als JSONL nach Git plus pg_dump zu einem zweiten Anbieter. Deployment als Docker Compose, Domain mit zweitem Registrar-Account. Ziel: ein Providerwechsel ist ein Wochenende, keine Neuentwicklung. Das ist zugleich die Gegenmassnahme gegen Deplattformierung und gegen Bus-Faktor 1.

DATENSCHUTZ
Eine Frage wie "ist X haram fuer mich" offenbart die religioese Ueberzeugung des Fragestellers — Art. 9 DSGVO, und praktisch traegt nur die ausdrueckliche Einwilligung nach Abs. 2 lit. a. Konsequenz: Chat ohne Account, frage_text per Default NULL, antwort_log ohne Fragetext und ohne IP, Speicherung des Volltexts nur nach separater Opt-in-Checkbox, TTL 30 Tage auf Rohlogs. Antworten cachen ist unproblematisch, Fragen cachen ist es nicht — deshalb ist der Cache-Key der Vektor plus die Begriffe, nicht der Rohtext. LLM-Aufrufe laufen hinter einem eigenen Gateway mit drei Rollen (synthesize, cheap_task, verify), damit ein Providerwechsel eine Konfigzeile ist; das EU-US Data Privacy Framework ist formal gueltig, aber seit Ende Oktober 2025 beim EuGH angefochten.

RECHTSTRAEGER
Verein oder gGmbH vor dem Livegang, Impressum nach § 5 DDG und § 18 Abs. 2 MStV mit ladungsfaehiger Anschrift, nie die Privatadresse eines Bruders. § 48 UrhG traegt ausdruecklich NICHT: Abs. 2 nimmt Sammlungen aus, die ueberwiegend Reden desselben Urhebers enthalten — ein thematisch sortiertes Ibn-Uthaymin-Archiv ist exakt dieser Ausnahmefall. Die Uebersetzung ist nach § 3 UrhG eine Bearbeitung und darf nach § 23 UrhG nur mit Einwilligung veroeffentlicht werden; die deutsche Fassung ist also riskanter als das arabische Original, nicht harmloser. (Orientierung, keine Rechtsberatung.)

---
## Repo-Layout

fatawa-platform/                      (das bestehende Verzeichnis wird zum Repo-Wurzelordner)
├── README.md                         vorhanden, wird fortgeschrieben
├── CLAUDE.md                         Konventionen: nie text_norm anzeigen, nie Tashkeel
│                                     generieren, nur logical properties, nie auf Dateinamen joinen
├── docker-compose.yml                caddy, web, api, worker, db (paradedb/paradedb:latest)
├── Caddyfile                         TLS, X-Accel-Buffering: no fuer /api/ask
│
├── intake/                           VORHANDEN — wird nach Drive 00_START-HIER/ gespiegelt
│   ├── ANLEITUNG-BRUEDER.md          unveraendert
│   ├── ANLEITUNG-ADMIN.md            + Abschnitt zum Melde- und Sperrvorgang
│   ├── ORDNERSTRUKTUR.md             unveraendert
│   ├── DATEIFORMATE.md               unveraendert (der Validator setzt genau diese Regeln um)
│   ├── _VORLAGE/  _BEISPIEL/
│
├── referenz/                         VORHANDEN — vom Backend direkt gelesen
│   ├── gelehrte.csv                  + Spalte aliase (semikolongetrennt)
│   ├── themen.yml                    + Pflichtfeld content_class je Unterthema
│   ├── REGISTER.md                   + vier Backend-Spalten (pipeline_status, pipeline_fehler,
│   │                                   rohtext_url, geprueft_url)
│   ├── register-vorlage.csv          entsprechend erweitert
│   └── glossar.tsv                   NEU: term_de, term_en, term_ar, term_translit, hinweis
│
├── apps/web/                         Next.js 16.4, cacheComponents: true
│   ├── app/[locale]/
│   │   ├── page.tsx                  Startseite
│   │   ├── t/[themaSlug]/page.tsx    Themenbaum aus themen.yml
│   │   ├── g/[gelehrterSlug]/page.tsx  Gelehrtenseite MIT Abdeckungsindikator
│   │   ├── e/[eintragId]/page.tsx    Player + dreispaltiges Transkript, ?t=<sek>
│   │   ├── ask/page.tsx              [P2] KI-Tool, SSE-Client, Art.-50-Hinweis
│   │   └── legal/{impressum,datenschutz}/page.tsx
│   ├── app/admin/                    minimal in P1: Freigabe, Meldungen, Dashboard
│   ├── components/
│   │   ├── player/{AudioPlayer,Waveform}.tsx     Vidstack; Progressbar bleibt dir="ltr"
│   │   ├── transkript/{VirtualList,Zeile,BidiSpan}.tsx
│   │   ├── badges/{Zuschreibung,UebersetzungStatus,Ungeprueft}.tsx
│   │   └── melden/MeldeDialog.tsx
│   ├── messages/{ar,de,en}.json
│   └── styles/fonts.css              Noto Naskh Arabic + IBM Plex Sans Arabic, subgesetzt
│
├── services/api/                     EIN Python-Projekt (uv), FastAPI + Worker
│   ├── app/main.py
│   ├── app/routers/{bibliothek,ask,admin,melden,health}.py
│   ├── app/drive/{client.py,register.py,dateien.py}   OAuth-Refresh-Token, Polling
│   ├── app/ingest/{holen,transkodieren,asr,parsen,zitate,status,uebersetzen,chunken}.py
│   ├── app/rag/{verstehen,routing,embed,retrieve,rerank,synthese,verify,cache,abstain}.py   [P2]
│   ├── app/llm/gateway.py            drei Rollen: synthesize | cheap_task | verify
│   ├── app/arabic/{normalize.py,translit.py}
│   ├── app/worker/{runner.py,jobs.py}            SKIP LOCKED, Heartbeat, Backoff
│   └── prompts/{synthese.v1.md,verify.v1.md,verstehen.v1.md,uebersetzen.v1.md}
│
├── packages/api-client/              generiert via @hey-api/openapi-ts, committed, CI-Drift-Check
│
├── db/
│   ├── migrations/0001_init.sql ...  plain SQL, kein ORM-Migrationstool
│   ├── functions/normalize_ar.sql    IMMUTABLE, Zwilling zu app/arabic/normalize.py
│   └── views/chunks_citable.sql      + GRANT-Skript, das der App SELECT auf die Basistabellen entzieht
│
├── data/
│   ├── quran/                        Tanzil, CC BY 3.0, lokal gespiegelt
│   ├── hadith/                       fawazahmed0/hadith-api, Unlicense
│   └── vorberechnete_fragen.yaml     [P2] kuratierte Masail je Sprache
│
├── eval/
│   ├── goldset.yaml                  150 Fragen + 50 Negativ + 30 Minimalpaare
│   ├── run_eval.py                   Recall@30, nDCG@10, abstain_correct, nach Richtung getrennt
│   └── bakeoff_asr.py                20 Clips x 4 Anbieter, WER + CER + Namenstreue
│
├── ops/
│   ├── backup.sh / restore_test.sh   pgBackRest; restore_test MONATLICH, sonst ist das Backup Fiktion
│   ├── export_jsonl.sh               Export-First nach Git
│   └── canary.sh                     stuendlich: taucht der Marker in Retrieval/Antwort auf?
│
└── .github/workflows/ci.yml          lint, pytest, openapi-drift, normalize_ar-Testvektoren

---
## Roadmap

### Phase 0 — De-Risking, vor der ersten Zeile Produktionscode
**Dauer:** 1 Woche, ca. 10 h Entwickler + Zeit der Brueder, unter 50 EUR  
**Ergebnis:** Fuenf Zahlen liegen vor, die die Korpus-Zielgroesse, den Ingest-Weg und die Produkttauglichkeit bestimmen. Ohne sie plant man gegen Annahmen.

- DURCHSATZMESSUNG: drei Brueder, je 30 Minuten echtes Audio, voller Durchlauf mit Stoppuhr — ASR-Korrektur, DE-Uebersetzung, Pruefung durch einen Zweiten. Ergebnis mit der realen Wochenkapazitaet multiplizieren. Diese Zahl entscheidet ueber die Korpus-Zielgroesse, vermutlich gegen 3.000 und fuer 800-1.500.
- ASR-BAKE-OFF: 20 selbst gewaehlte Clips (alte Kassette, Studio, Dialekteinschub, dichtes Quran-Zitat, Frage-Antwort-Wechsel) gegen Soniox, ElevenLabs Scribe v2, Speechmatics Enhanced, gpt-4o-transcribe. Getrennt bewerten: WER, CER, Namenstreue bei Gelehrten und Ueberlieferern, Timestamp-Qualitaet. Bei gpt-4o-transcribe zwingend pruefen, ob word-level timestamps geliefert werden. Finanziert aus Startguthaben (Speechmatics 100 USD, Gladia 50 EUR).
- ZUSCHREIBUNGS-STICHPROBE: 30 kursierende Clips von einem Kenner gegen binbaz.org.sa, binothaimeen.net und alifta.gov.sa pruefen lassen. Falschzuschreibungsrate ueber 10 % heisst: nur offizielle Quellen duerfen zitiert werden.
- NUANCEN-TEST: 20 Saetze mit makruh/haram, la yanbaghi, al-ahwat, fihi tafsil und Konditionalkonstruktionen durch MT und durch zwei Brueder. Ueber 20 % gekippte Nuance heisst: hukm als Enum ist Pflicht, nicht optional (ist im Schema ohnehin vorgesehen).
- ADVERSARIALES FRAGENSET: 50 Fragen schreiben, die das System kaputtmachen sollen (Negationen, 'hat X je gesagt', Minimalpaare, Vergleichsfragen, Takfir, Talaq in Ich-Form, Gelehrter-gegen-Gelehrten, duenne Themen). Gegen einen Wegwerf-Prototyp mit 50 Eintraegen und Sonnet 5.5 fahren, von einem Bruder mit Ilm bewerten lassen. Das sagt in Woche 1, ob die Produktidee traegt.
- ORGANISATORISCH, parallel: Verein oder gGmbH klaeren; Muraji namentlich benennen (mindestens zwei, besser drei, mit realistischem Monatspensum); Erlaubnisschreiben an binothaimeen.net, miraath.net und das al-Fawzan-Buero; content_class in themen.yml gemeinsam festlegen; 90 Minuten bei einem Anwalt fuer IT- und Aeusserungsrecht (300-500 EUR).

### Phase 1 — Die Bibliothek
**Dauer:** 8 Wochen, ca. 96 h Entwickler (12 h/Woche) + 48 h Helfer (6 h/Woche)  
**Ergebnis:** Oeffentlich erreichbares, dreisprachiges Archiv: Themenbaum, Gelehrtenseiten, Audio-Player mit synchronem Transkript in AR/DE/EN und sekundengenauem Deep-Link. Die Brueder liefern ins bestehende Drive, sehen den Pipeline-Status im Register und ihren Eintrag live auf der Seite. KEIN KI-Tool, kein Muraji-Engpass, unter 20 EUR/Monat. Damit ist der unstrittig nuetzliche Teil fertig und der Chatbot ist kein Risiko mehr, sondern eine Erweiterung.

- W1 (12 h): Repo aus dem bestehenden Verzeichnis, docker-compose mit paradedb, 0001_init.sql mit dem VOLLSTAENDIGEN Schema inkl. der [P2]-Spalten, chunks_citable-View, GRANT-Skript, embedding-Partitionierung, revision_log mit Hash-Trigger, normalize_ar in SQL und Python mit gemeinsamen Testvektoren. Seeds aus gelehrte.csv und themen.yml, content_class ergaenzt.
- W2 (12 h): Drive-Client mit OAuth-Refresh-Token, Register-Reader mit vollstaendiger Validierung, Dateiabholung, B2-Spiegel, ffmpeg nach Opus mit Dauer-Test. Statusschreiber in die vier neuen Sheet-Spalten.
- W3 (12 h): Soniox-Anbindung mit Zeilenbildung und Sanity-Checks, Rueckweg der ar.txt ins Drive, Parser fuer [HH:MM:SS]-Zeilen und Markup, Validator fuer Zeilenzahl und Monotonie, Quran-Lookup gegen Tanzil innerhalb der ﴿ ﴾-Marker. HELFER parallel: Next.js-Geruest, next-intl, [locale]-Routing, dir-Umschaltung, Schriften subgesetzt und mit einer vollvokalisierten Ayah getestet.
- W4-5 (24 h): FastAPI-Endpunkte fuer Bibliothek, Themenbaum, Gelehrtenseite, Eintrag, VTT-Export. Job-Runner mit SKIP LOCKED und Heartbeat. HELFER: Themen- und Gelehrtenseiten, Listen, Suche ueber Titel (Postgres trigram, noch kein Retrieval).
- W6-7 (24 h Dev-Support): Eintragsseite mit Vidstack-Player, dreispaltigem virtualisiertem Transkript (TanStack Virtual, binaere Cue-Suche), aktiver Zeile, Klick-zum-Springen, Deep-Link ?t=. Bidi-Isolation fuer Timecodes, Hadith-Nummern und Jahreszahlen — eine verrutschte Hadith-Nummer ist eine inhaltliche Falschaussage, nicht Kosmetik. Badges fuer zuschreibung='wahrscheinlich' und ungeprefte Uebersetzung. Melde-Button. HELFER baut, Entwickler liefert Daten zu.
- W8 (12 h): Impressum und Datenschutzerklaerung, pgBackRest mit EINEM tatsaechlich durchgefuehrten und protokollierten restore_test, Sentry, Canary-Cron, Timestamp-Drift-Cron, Export-Skript nach Git. Soft-Launch mit 200-400 geprueften Eintraegen im engen Kreis.
- BEWUSST NICHT IN PHASE 1: Upload-Formular (Drive existiert), Review-Workbench mit Wellenform (die Brueder korrigieren .txt-Dateien, wie DATEIFORMATE.md es vorsieht — das ist der groesste streichbare Posten und kostet fast keine Qualitaet), Forced Alignment, Dedup-UI, Glossar-UI, Cache-Freigabe-UI, Embeddings, Reranking, KI-Tool.

### Phase 2 — Das Suchwerkzeug
**Dauer:** Monat 3 bis 6, ca. 150 h Entwickler  
**Ergebnis:** Das KI-Tool beantwortet Fragen auf AR/DE/EN ausschliesslich aus geprueftem Material, mit Zitatankern auf die Sekunde, Attributionspruefung und Themen-Routing. Vorberechnete Antworten sind von einem Muraji freigegeben. Messbar gegen ein eigenes Goldset.

- ZUERST das Goldset: 150 echte Fragen mit annotierten Eintrags-IDs, 50 Negativfragen, 30 Minimalpaare — von den Bruedern, nicht vom Entwickler. Danach die A/B-Messung AR-only gegen dreisprachig auf 200 Eintraegen (unter 20 USD) und erst dann die Index-Strategie festschreiben.
- BGE-M3 ONNX int8 auf CPU fuer Queries, Bulk-Indexierung auf RunPod A5000. pg_search-BM25-Index. Hybrid-SQL mit vier CTEs, Sprachbalance, gewichtetes RRF, Parent-Expansion, Voyage-Reranking mit Dual-Scoring.
- Routing und Sperrliste VOR dem ersten Retrieval: Intent-Classifier, content_class-Auswertung, Ich-Form-Heuristik, Existenzfragen-Abfang. Zwei Schwellen statt einer.
- Synthese mit search_result-Bloecken und Citations, ein Block pro Gelehrtem, erzwungenes Positionsformat, Regex-Blockliste gegen kollektive Formulierungen. Verifier mit Attributions- und Kontextdeckung. SSE mit sources-first.
- Kostenschutz VOR dem ersten oeffentlichen Request: Tages-Hardcap mit Degradation auf reine Fundstellen, Turnstile, Rate-Limit, max_tokens. Lasttest mit 10.000 Requests gegen den eigenen Endpunkt.
- Cache L0/L1/L2 mit qualifier-Gate, gezielte Invalidierung ueber antwort_zitat, synchrone Sperrung binnen 60 s. Pre-Cache von 500 Masail mit Opus 5.5 Batch plus Freigabe-UI fuer den Muraji.
- Glossar mit 300-500 Paaren inkl. Transliterationsvarianten, Pflege-UI. MT-Rohuebersetzung und QA-Screening im Ingest. NER-Gate fuer lebende Personen. Ruju-Konfliktdetektor.
- Review-Priorisierung aus nachfrage scharf schalten: die Warteschlange sortiert sich nach tatsaechlichen Treffern, nicht nach Eingangsdatum.

### Phase 3 — Haertung und Wachstum
**Dauer:** ab Monat 7, nur was gemessen weh tut  
**Ergebnis:** Das System traegt 3.000+ Eintraege, ueberlebt einen Embedder-Wechsel und einen Providerwechsel, und die Review-Kapazitaet ist der einzige verbleibende Engpass.

- Worker auf eigene VM trennen, sobald ffmpeg die Request-Latenz stoert. ISR-Cache-Handler auf Redis, sobald mehr als eine App-Instanz laeuft — zwei Instanzen mit getrenntem Dateisystem-Cache zeigen unterschiedliche Transkripte, und das ist hier kein Caching-Bug, sondern ein Zuschreibungsfehler.
- REINDEX-DRILL: einmal einen vollstaendigen Embedder-Wechsel ueben (neue Partition fuellen, partitionsweise CONCURRENTLY indexieren, gegen das Goldset messen, active_embedding_model_id umschalten, alte Partition nach einer Woche droppen). Der Reindex ist der Moment, an dem Projekte dieser Groesse kaputtgehen, weil er als einmalig geplant wird.
- Import historischer Transkripte ohne Zeitmarken: erst hier ctc-forced-aligner (MMS-300m-1130) mit zwingender uroman-Romanisierung und hartem Null-Timing-Check, oder bertalign fuer vorhandene freie Uebersetzungen mit gespeichertem Block-Score und deaktiviertem Deep-Link unterhalb der Schwelle.
- Dedup in drei Stufen: SHA-256, Chromaprint (revidiert 2026-10-25: ein Fingerprint je Aufnahme, Vergleich per Bitfehlerrate — siehe PIPELINE.md Schicht 3), MinHash ueber text_norm. Nie automatisch loeschen, nur verlinken.
- Bunny Volume-CDN vor den Object Storage, wenn die Latenz im Golf messbar stoert. Arabic-Triplet-Matryoshka-V2 als zweiter AR-Retriever mit RRF — nur behalten, wenn er auf dem Goldset mindestens 2 nDCG-Punkte bringt.
- Qdrant erst jenseits von 10 Mio. Vektoren neu bewerten. Realistisch erreicht dieses Projekt den Punkt nie.

---
## Top-Bottlenecks

**1.** MENSCHLICHE REVIEW — der eigentliche Engpass, und er ist um Groessenordnungen groesser als alles Technische. Die eigene Rechnung im README (3.000 Videos = ca. 4.000 Mannstunden = zwei Jahre bei zehn Bruedern) ist realistisch und vermutlich noch optimistisch: bei 20-40 % WER auf altem Kassettenmaterial liegt die Transkriptkorrektur eher bei 90-180 Minuten je Audiostunde, nicht bei den 15-20 Minuten aus englischen Benchmarks. Konsequenz fuer die Architektur: Vollreview ist kein erreichbarer Zustand, also muessen shadow/verified-Tiers, Ingest-Drossel und nachfragegesteuerte Priorisierung von Anfang an drin sein. Konsequenz fuer die Planung: die Korpus-Zielgroesse ist die Stellschraube, nicht die Technik — tief statt breit, 800-1.500 sorgfaeltig kuratierte Eintraege zu den meistgefragten Masail sind wertvoller und glaubwuerdiger als 30.000 halbgeprefte.

**2.** FREIWILLIGENABBRUCH NACH DREI MONATEN. Der typische Verlauf: Begeisterung, Ramadan-Peak, Einbruch. Danach liegt das Projekt im Zwischenzustand — zu gross zum Pruefen, zu klein zum Nuetzen. Die Gegenmassnahmen sind nicht technisch, sondern in der Phasung: die Bibliothek steht in Woche 8 und nicht in Monat 5, der Pipeline-Status wandert sichtbar im Sheet, das die Brueder ohnehin offen haben, und die Ingest-Drossel (max. 2:1 registriert zu geprueft) verhindert den Backlog, der demotiviert. Gemessen wird der woechentliche aktive Beitragenden-Count; faellt er zwei Wochen in Folge, hat die Kurve begonnen.

**3.** DER MURAJI. Die Freigabestufe fuer vorberechnete Antworten und fuer content_class='nur_fundstellen' braucht eine namentlich benannte Person mit Ilm, die unterschreibt. Ohne sie ist die gesamte Zuschreibungstreue-Kette technisch korrekt und inhaltlich wertlos. Mit nur einer Person ist sie Flaschenhals und Haftungssubjekt zugleich und wird entweder nicht mitkommen oder durchwinken. Deshalb: mindestens zwei, besser drei Murajiun mit geteilten Themenbereichen und einem realistischen Pensum (z.B. 50 Antworten im Monat) — und das System muss ohne sie funktionieren, also als Archiv ohne Synthese.

**4.** DIE KI-SCHICHT IST DER TEIL, DEN DIE ZIELGRUPPE ABLEHNT. islamqa.info hat eine Fatwa gegen das Einholen von Fatawa bei KI, Dar al-Ifta Aegypten hat KI-Tafsir untersagt. Es ist moeglich, neun Monate zu bauen und als erste Reaktion 'man fragt keine Maschine' zu hoeren statt 'das ist falsch zitiert'. Genau deshalb steht die Bibliothek in Phase 1 und das KI-Tool erst in Phase 2: der unstrittig nuetzliche Teil ist dann fertig und unabhaengig lebensfaehig. Und das KI-Tool wird visuell und sprachlich als Suchhilfe praesentiert — Fundstellen zuerst, Zusammenfassung zweitrangig —, nie als antwortende Instanz.

**5.** BUS-FAKTOR 1. Eine Person soll arabische ASR, Drive-Integration, RAG, Next.js mit RTL, Linux-Ops und deutsches Medienrecht beherrschen. Export-First rettet die Daten, aber niemanden am Montagmorgen, wenn Postgres nach einem Neustart nicht hochkommt. Gegenmassnahmen im Entwurf: radikal wenige bewegliche Teile (fuenf Container, eine Maschine, kein PaaS, kein Broker, kein self-hosted Monitoring), alles als Docker Compose, und ein zweiter Mensch bekommt ab Woche 8 Zugaenge und fuehrt den restore_test EINMAL selbst aus, auch wenn er sonst nichts beitraegt.

**6.** RECHTSGRUNDLAGE JE QUELLE. binbaz.org.sa traegt im Footer eine ausdrueckliche Weitergabeerlaubnis gegen Quellenangabe. binothaimeen.net hat KEINE und fuehrt in robots.txt die Content-Signals-Policy mit Rechtevorbehalt nach Art. 4 DSM-RL 2019/790 gegen ai-input und ai-train — darueber hinwegzugehen waere kein Graubereich, sondern Handeln gegen eine dokumentierte Willenserklaerung. islamqa.info verbietet Redistribution in den Terms. Das Einholen schriftlicher Erlaubnisse hat Monate Vorlauf und muss in Phase 0 beginnen, nicht in Woche 8. Fuer binothaimeen gibt es ein eigenes API-Backend (shekhapi.binothaimeen.net), das sie bei Zustimmung oeffnen koennen — zehnmal sauberer als jeder Scraper.

**7.** SITUATIONSBINDUNG UND RUJU. Die Mehrheit muendlicher Fatawa ist auf einen konkreten Fall gegeben, und Positionswechsel der Gelehrten (al-Albani bei Hadith-Gradierungen, Ibn Uthaymin in einzelnen Masail) sind real. Beides ist mit Retrieval prinzipiell nicht loesbar — nur ueber generality, frage_ar, aufnahmedatum, ersetzt/ersetzt_durch und einen Konfliktdetektor, und alle diese Felder muss am Ende ein Mensch setzen. Damit haengt auch dieser Punkt wieder an der Review-Kapazitaet.

**8.** ASR-QUALITAET AUF REALEM MATERIAL. Die zitierten 6,5-10,8 % WER stammen von FLEURS, also sauber gelesenem MSA im Studio. Alte Kassetten mit Raumhall, Mikrofonuebersteuerung und Nadschdi-Einschlag liegen realistisch bei 20-40 %; das Open Universal Arabic ASR Leaderboard zeigt in realistischeren Settings 28-45 % avg WER selbst fuer Spitzenmodelle. Das sprengt nicht die ASR-Rechnung (0,10 USD/h bleibt), sondern die Review-Rechnung — und damit wieder Engpass 1. Bei stark komprimierten alten MP3s mit 8-16 kHz hilft kein besseres Modell; dort ist Audio-Restauration der groessere Hebel als die Anbieterwahl.

**9.** QUERY-KOSTEN SKALIEREN MIT FRAGEN, NICHT MIT DEM KORPUS. Ab Phase 2 sind ueber 80 % der Rechnung Synthese. Ein viraler Moment im Ramadan verzehnfacht den Traffic ueber Nacht, und ein Bot mit Residential-Proxies macht IP-Limits wirkungslos. Der Tages-Hardcap mit Degradation auf reine Fundstellen ist deshalb kein Nice-to-have, sondern muss vor dem ersten oeffentlichen Request stehen und mit 10.000 Requests getestet sein.

**10.** EMBEDDER-LOCK-IN. Ein Reranker-Wechsel ist eine Konfigzeile, ein Embedder-Wechsel eine Reindexierung in drei Sprachen. Rechnerisch kostet das unter 0,50 EUR — operativ ist es der Moment, an dem Projekte dieser Groesse kaputtgehen, weil er als Einmalereignis geplant wird. Deshalb Partitionierung nach model_id und active_embedding_model_id in der ERSTEN Migration, obwohl in Phase 1 null Embeddings existieren.

---
## Woche 1 — billige Experimente zuerst

- Durchsatz messen statt schaetzen: drei Brueder, je 30 Minuten echtes Audio, voller Durchlauf mit Stoppuhr (ASR-Korrektur, DE-Uebersetzung, Pruefung durch einen Zweiten). Die resultierende Zahl Stunden-pro-Audiostunde mit der real verfuegbaren Wochenkapazitaet multiplizieren. Kosten: 0 EUR, ein Nachmittag. Diese eine Zahl entscheidet ueber die Korpus-Zielgroesse, und alles davor zu planen ist verschwendete Zeit.
- ASR-Bake-off auf 20 selbst gewaehlten Clips aus dem echten Zielmaterial gegen Soniox, ElevenLabs Scribe v2, Speechmatics Enhanced und gpt-4o-transcribe. Getrennt bewerten: WER, CER, Namenstreue bei Gelehrten und Ueberlieferern, Verhalten bei Quran-Zitaten, Timestamp-Qualitaet. Finanziert aus den Startguthaben (Speechmatics 100 USD, Gladia 50 EUR), also faktisch 0 EUR. Entscheidet ueber die Review-Last der naechsten Jahre.
- Zuschreibungs-Stichprobe: 30 Clips, die bereits als Fatawa der genannten Gelehrten kursieren, von einem Kenner gegen binbaz.org.sa, binothaimeen.net und alifta.gov.sa pruefen lassen. Liegt die Falschzuschreibungsrate ueber 10 %, duerfen nur offizielle Quellen zitiert werden — das aendert die gesamte Ingest-Politik und spart Monate.
- Adversariales 50-Fragen-Set schreiben und gegen einen Wegwerf-Prototyp mit 50 Eintraegen und Sonnet 5.5 fahren, von einem Bruder mit Ilm bewerten lassen. Kosten unter 20 USD, zwei Tage. Das sagt in Woche 1, ob die Produktidee traegt, statt in Monat 9 — und es produziert nebenbei den Kern des spaeteren Goldsets.
- Nuancen-Test: 20 Saetze mit makruh/haram, la yanbaghi, al-ahwat, fihi tafsil und Konditionalkonstruktionen durch MT und durch zwei Brueder laufen lassen und zaehlen, wie oft die Rechtsnuance kippt. Ein Tag, 0 EUR. ANLEITUNG-ADMIN.md nennt das bereits als die folgenschwerste Fehlerklasse — hier wird sie messbar.
- content_class in themen.yml gemeinsam festlegen und committen: welche Themen gar nicht in den Index (jarh-tadil, hizbiyya, fitan, takfir, wulat-amr) und welche nur Fundstellen ohne Synthese liefern (talaq, mawarith, aymaan, tibb, tibb-muasir, wala-bara). Eine Besprechung, drei Zeilen YAML je Thema — und die wichtigste inhaltliche Sicherheitsmassnahme des Produkts. Sie muss in dieselbe Datei, in der die Themen stehen, weil die Taxonomie den Korpus sonst aktiv dorthin einlaedt.
- Erlaubnisschreiben rausschicken: eine Seite Konzept auf Arabisch an binothaimeen.net, miraath.net und das al-Fawzan-Buero, mit der Bitte um Erlaubnis und um Rueckmeldung zur Idee. Formuliert als 'Index und Suche in den Worten der Gelehrten', nie als Mufti. Die Antwort oder das Schweigen ist das wichtigste Signal des gesamten Projekts und kostet eine E-Mail — aber sie hat Monate Vorlauf, also muss sie jetzt raus.
- Drive anlegen und die ersten 20 Eintraege gemeinsam durchspielen, bevor zehn Brueder loslaufen (steht bereits als offener Punkt im README). Dabei konkret pruefen: haelt die Zeilen-pro-Zeitmarke-Konvention in der Praxis, oder ziehen die Uebersetzer doch Zeilen zusammen? Die gesamte Deep-Link-Faehigkeit haengt daran, und ein 20-Zeilen-Skript, das die Zeilenzahl prueft und sofort Rueckmeldung gibt, ist der billigste Qualitaetsmechanismus im ganzen Projekt — es kann im Drive laufen, lange bevor ein Backend existiert.
- 90 Minuten Anwalt fuer IT- und Aeusserungsrecht buchen (300-500 EUR), drei Fragen: Traegerstruktur und Impressum, Haftung fuer uebersetzte Aeusserungen ueber lebende Personen, Art. 9 DSGVO beim Chat ohne Account. Billigste Versicherung im Projekt, verhindert die zwei wahrscheinlichsten Rechtsereignisse.
- Zwei bis drei Murajiun namentlich benennen und ihr realistisches Monatspensum schriftlich festhalten. Ohne diese Zusage ist die gesamte Freigabearchitektur eine Attrappe — und die Entscheidung gehoert vor das Datenmodell, nicht danach.

---
## Offene Fragen, die nur ihr beantworten könnt

- Wie viele Stunden pro Woche stehen DIR real zur Verfuegung? Die 8-Wochen-Phase-1 rechnet mit 12 h/Woche plus 6 h beim Helfer. Bei 6 h/Woche werden daraus 16 Wochen, und dann muss Phase 1 weiter schrumpfen — mein Vorschlag waere dann: Bibliothek ohne eigenen Player, mit einem simplen HTML5-Audio-Element und Transkript als statische Liste. Diese Zahl bestimmt den Schnitt, nicht die Technik.
- Gibt es ein Google Workspace oder nur private Gmail-Konten? Die Antwort aendert den Drive-Zugriff: mit Workspace geht ein Shared Drive und ein Service Account, ohne Workspace laeuft es ueber einen normalen geteilten Ordner plus OAuth-Refresh-Token eines menschlichen Kontos (so ist der Entwurf gebaut, weil das auch ohne Workspace funktioniert). Falls es Workspace gibt, wird der Betrieb etwas robuster.
- Bringen die Brueder ueberwiegend Dateien mit oder ueberwiegend YouTube-Links? Bei Links wird der Ingest primaer ein yt-dlp-Job, die gesamte Upload-Logistik vereinfacht sich drastisch, und source_url ist automatisch ein echter Herkunftsnachweis statt eines Textfeldes. Das aendert Stufe 1 der Pipeline erheblich.
- Wer ist der Muraji, und wie viele Antworten pro Monat kann er realistisch gegenlesen? Von dieser Zahl haengt ab, ob der Pre-Cache 500 oder 50 Antworten umfasst — und ob das KI-Tool in Phase 2 ueberhaupt vorberechnete Antworten ausliefert oder nur live generiert mit sichtbarem Hinweis 'nicht redaktionell geprueft'.
- Soll content_class so belegt werden, wie ich es vorschlage? Konkret: jarh-tadil, hizbiyya, fitan, takfir und wulat-amr gar nicht in den Index; talaq, mawarith, aymaan, tibb, tibb-muasir und wala-bara nur als Fundstellen ohne Synthese. Das ist eine inhaltliche Entscheidung mit Reichweitenfolgen, keine technische — sie kostet einen Teil der Zielgruppe und schuetzt das Projekt. Nur ihr koennt sie treffen.
- Wie geht ihr mit zwei widersprechenden Aussagen DESSELBEN Gelehrten um, wenn die Chronologie unklar ist? Mein Vorschlag: beide mit Datum nebeneinander, keine Synthese, Flag fuer den Pruefer. Alternative waere, die spaetere zu bevorzugen — das setzt aber voraus, dass aufnahmedatum zuverlaessig gefuellt ist, und laut REGISTER.md ist es optional mit der Regel 'nie raten'.
- Gibt es bereits digitalisierte, autoritative Textfassungen zu einem Teil des Materials (binbaz.org.sa, binothaimeen.net, alifta.gov.sa)? Falls ja, waere Text-zu-Audio-Alignment statt Transkription der groesste denkbare Hebel auf den Review-Aufwand — er wuerde den teuersten Posten weitgehend eliminieren. Das wuerde eine eigene Phase-2-Komponente rechtfertigen.
- Trefft ihr die Entscheidung, auch lebende Gelehrte aufzunehmen (al-Fawzan, Rabi al-Madkhali, al-Abbad und andere stehen bereits in gelehrte.csv)? Bei lebenden Gelehrten ist das Risiko hoeher, dass eine Zuschreibung bestritten oder eine Position korrigiert wird — und ein Widerspruch des Gelehrten selbst waere der schwerste denkbare Fall. Mein Vorschlag: aufnehmen, aber ausschliesslich mit quelle_typ='offiziell' und zuschreibung='bestaetigt'.
- Welches Query-Volumen erwartet ihr realistisch in Monat 1, 6 und 12 nach dem KI-Launch? Unter 10.000 Fragen im Monat ist die Modellwahl fast egal, ueber 100.000 wird jede Entscheidung zu Cache und Modell dreistellig teuer. Die gesamte Kostenrechnung ab Phase 2 haengt an dieser Zahl, nicht an der Korpusgroesse.
- Wollt ihr Spenden annehmen, und wenn ja ueber welchen Weg? Das entscheidet ueber die Lizenzlage einzelner Korpora (OpenITI ist CC BY-NC-SA, Tanzil-Uebersetzungen sind non-commercial) und erhoeht das Deplattformierungsrisiko beim Zahlungsdienstleister. Vor der Korpusauswahl klaeren, nicht danach.

---
## Anpassung an Google Form + Docs

Was sich gegenüber den Entwürfen ändert:

- **Kein Nachteil beim Upload-Portal:** Die Jury verwarf ein eigenes Einreichformular, weil es 8–12 Entwicklertage kostet. Ein Google Form kostet null. Die Empfehlung wird dadurch erfüllt, nicht verletzt.
- **Ingest-Reader liest Docs statt `.txt`:** Die Docs-API liefert Tabellen strukturiert zurück (`table/tableRow/tableCell`), also entfällt sogar das Parsen des `[HH:MM:SS]`-Zeilenformats. Die Zeitmarke steht in Spalte 1, die Sprachen in Spalte 2–4. Eher einfacher als der `.txt`-Weg.
- **Validator bleibt gleich wichtig:** Zeilenzahl, Monotonie, Zeit ≤ `duration_sec`. Er prüft jetzt Tabellenzeilen statt Dateizeilen.
- **Forced Alignment bleibt in Phase 3:** Das Argument hält unverändert — die Zeitmarke kommt aus dem ASR-Lauf und überlebt die Korrektur, weil Zeilen nicht verändert werden dürfen.
- **Status-Rückkanal unverändert:** zusätzliche Spalten im selben Register-Sheet, keine zweite Oberfläche.