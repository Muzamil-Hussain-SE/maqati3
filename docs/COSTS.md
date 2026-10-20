# Kostenmodell

*Aus der Recherche, Stand 2026-10-07. 1 USD = 0,92 EUR.*

Annahmen: 1 USD = 0,92 EUR, alle Betraege netto. 8 Minuten je Eintrag. Arabischer Tokenfaktor konservativ 4 Token/Wort — UNVERIFIZIERT, der Claude-Tokenizer ab 4.7 erzeugt generell ca. 30 % mehr Token und der arabische Faktor ist ungemessen. Vor dem Budget-Commit 20 echte Transkripte mit messages.count_tokens messen; bei 5,5 Token/Wort steigen alle Uebersetzungs-, Embedding- und Synthese-Positionen um 37 %.

**Einmalige Ingest-Kosten (vollstaendig, alle drei Sprachen indexiert)**

| Posten | 70 h (500 Eintr.) | 200 h (1.500) | 400 h (3.000) |
|---|---|---|---|
| ASR Soniox (0,10 USD/h) | 6,44 EUR | 18,40 EUR | 36,80 EUR |
| MT-Rohuebersetzung DE+EN, Haiku Batch | 1,62 EUR | 4,60 EUR | 9,20 EUR |
| Uebersetzungs-QA-Screening, Haiku Batch | 0,80 EUR | 2,30 EUR | 4,60 EUR |
| Themen-Tagging, Haiku Batch | 0,32 EUR | 0,97 EUR | 1,93 EUR |
| Embeddings BGE-M3 (RunPod A5000, 0,16 USD/h) | 0,10 EUR | 0,28 EUR | 0,46 EUR |
| Pre-Cache 500 Masail x 3 Spr., Opus 5.5 Batch | — | 38,64 EUR | 38,64 EUR |
| **Summe einmalig** | **9,28 EUR** | **65,19 EUR** | **91,63 EUR** |

Der gesamte Zielkorpus kostet im Ingest weniger als eine Stunde bezahlte Entwicklerzeit. ASR ist in diesem Projekt kein Kostenposten. Ein kompletter Reindex bei Embedder-Wechsel kostet erneut nur die Embedding-Zeile, also unter 0,50 EUR.

**Laufende Monatskosten**

| Posten | Phase 1: 500 Eintr., 0 KI-Fragen | Phase 2: 1.500 Eintr., 10.000 Fragen, 50 % Cache | Phase 3: 3.000 Eintr., 50.000 Fragen, 65 % Cache |
|---|---|---|---|
| Server (Hetzner CX, inkl. 20 % Backup + IPv4) | 10,79 (CX33) | 27,38 (CX43+CX33) | 43,37 (CX43+CX43) |
| Hetzner Object Storage (1 TB Storage + 1 TB Egress inkl.) | 6,49 | 6,49 | 6,49 |
| Backblaze B2 Cold-Archiv der Originale | 0,20 | 0,60 | 1,15 |
| CDN-Egress Audio (Bunny Volume, 0,005 USD/GB) | 0,02 | 0,25 | 1,10 |
| LLM-Synthese (Sonnet 5.5, 0,0246 USD je Miss) | — | 113,16 | 395,96 |
| Query-Verstehen (Haiku 5.5) | — | 2,76 | 13,80 |
| Verifier (Haiku 5.5) | — | 6,90 | 24,15 |
| Reranking (Voyage rerank-3-lite) | — | 1,38 (Freikontingent trägt ca. 13.000 Queries) | 4,83 |
| Domain, TLS, Sentry Free | 1,25 | 2,00 | 3,00 |
| **Summe** | **18,75 EUR** | **160,92 EUR** | **493,85 EUR** |

**Vergleichszahlen, die die Entscheidungen begruenden**

| Variante | Phase 2 | Phase 3 | Delta |
|---|---|---|---|
| Opus 5.5 statt Sonnet live | 274,08 | 889,81 | +113 / +396 EUR |
| Ohne Antwort-Cache | 274,08 | 1.169,80 | +113 / +676 EUR |
| Ohne Prompt-Caching | 214,16 | 680,21 | +53 / +186 EUR |
| Video statt Audio-only ausgeliefert | +15,85 | +62,00 | Storage + Egress Faktor 19 |
| Cloudflare Stream statt Object Storage | +110,40 | +220,80 | Minutenabrechnung auf den Katalog |
| Cohere Rerank 3.5 statt Voyage lite | +16,50 | +87,20 | Faktor 60 |
| Hetzner CCX statt CX | +75,00 | +150,00 | Preiserhoehung 15.06.2026 |

**Lesart:** Die Infrastruktur kostet in allen drei Phasen unter 55 EUR. Phase 1 kostet unter 20 EUR, weil es keine Synthese gibt — das ist der Hauptgrund, die Bibliothek vor dem Chatbot zu bauen. Ab Phase 2 sind ueber 80 % der Rechnung die Synthese, und die haengt an der Zahl der FRAGEN, nicht an der Korpusgroesse. Drei Hebel in dieser Reihenfolge: kuratierter Pool (jede Frage daraus kostet 0 EUR und ist zugleich die bessere Antwort, weil ein Mensch sie freigegeben hat), Sonnet statt Opus, Prompt-Caching. Erst danach ueber Self-Hosting nachdenken — der Reranker rechnet sich self-hosted erst ab ca. 380.000 Queries/Monat.

**Nicht in dieser Tabelle und groesser als alles andere:** die Review-Arbeit. 400 h Audio sind bei 90-180 Minuten je Audiostunde 600-1.200 Personenstunden fuer das Transkript und mit beiden Uebersetzungen nach der eigenen Rechnung des Projekts ca. 4.000 Mannstunden. Bei zehn Bruedern a vier Stunden pro Woche sind das zwei Jahre. Das ist die wahre Kostenkurve.

[UNVERIFIZIERT: alle Hetzner-VM-Preise stammen aus zwei Sekundaerquellen, die sich um bis zu 30 % unterscheiden (CX23 5,49 vs. 7,13 EUR), weil hetzner.com die Preise per JS rendert. Vor Buchung in der Console gegenpruefen. Ebenfalls unverifiziert: Sentry-Free-Tier-Grenze, Bunny-Volume-Preis fuer MENA.]

---
## Annahmen

- WECHSELKURS: 1 USD = 0,92 EUR. Alle USD-Preise aus der Recherche werden mit diesem Faktor umgerechnet. Alle EUR-Betraege netto (ohne MwSt.). Hetzner-Preise sind bereits EUR-Listenpreise und werden NICHT umgerechnet.
- AUDIO-LAENGE: S1 70 h / 500 Videos = 8,4 min; S2 700 h / 5.000 = 8,4 min; S3 4.000 h / 30.000 = 8,0 min. Gerechnet wird durchgaengig in Audiostunden, nicht in Videoanzahl.
- SPRECHRATE: 130 arabische Woerter pro Minute Audio (Recherche-Annahme aus Block 4). 1.000 h = 60.000 min = 7,8 Mio. arabische Woerter.
- TOKENFAKTOR ARABISCH: 4 Token pro arabischem Wort. [UNVERIFIZIERT - die Recherche sagt ausdruecklich, der Claude-Tokenizer ab 4.7 erzeuge generell ca. 30% mehr Token und der arabische Faktor sei ungemessen. 4 Token/Wort ist bewusst konservativ. Vor dem Budget-Commit 20 echte Transkripte mit messages.count_tokens messen - wenn der echte Faktor 5,5 ist, steigen alle Uebersetzungs-, Embedding- und Synthese-Positionen um 37%.] 1.000 h = 31,2 Mio. AR-Token.
- CHUNKS: Q&A-Einheiten statt fixer Tokenlaenge, ca. 16 AR-Chunks pro 8-min-Video, mal 3 Sprachen. S3 (30.000 Videos) = ca. 1,44 Mio. Vektoren, halfvec(1024) = 2 KB x 1,3 HNSW-Overhead = ca. 3,7 GB Index. Passt in 32 GB RAM, also KEINE dedizierte Vektor-DB in keinem Szenario.
- SYNTHESE-PROMPT: 14.000 Input-Token pro Antwort (ca. 12-15 Chunks AR+Uebersetzung, System-Prompt, Glossar, Gelehrten-gruppierte search_result-Bloecke) und 800 Output-Token. Die Recherche veranschlagte 11.000/600 - ich rechne wegen des arabischen Tokenaufschlags konservativer.
- PROMPT-CACHING: 6.000 der 14.000 Input-Token sind stabil (System-Prompt, Glossar, Few-Shot, Abstain-Policy) und werden als Cache-Read zu 0,05x abgerechnet. 8.000 Token (die abgerufenen Chunks) sind pro Frage frisch. Cache-Write-Kosten amortisieren sich ab ca. 20 Fragen pro 5-Minuten-Fenster und werden deshalb nicht eigens gebucht - bei S1 mit nur 2.000 Fragen/Monat (ca. 2,8 Fragen/Stunde) ist diese Amortisation [UNSICHER], dort ist der Prompt-Cache-Vorteil real kleiner.
- ANTWORT-CACHE-TRAFFERQUOTE: S1 30%, S2 50%, S3 60% (bzw. 75% im aggressiven Pre-Caching-Szenario). Die Recherche nannte 60-70% - ich starte bewusst niedriger, weil ein Fatwa-Korpus wegen Kontextabhaengigkeit (Reisender vs. Ansaessiger, Frau vs. Mann) eine harte Cache-Schwelle von 0,97 plus lexikalisches Gate braucht und damit weniger Treffer erzeugt als eine Produkt-FAQ.
- QUERY-VOLUMEN vs. BESUCHER: Query-Expansion (Haiku) laeuft auf ALLEN Fragen, Synthese/Verifier/Reranking nur auf Cache-Misses.
- MEDIEN-MENGENGERUEST: Opus 24 kbit/s mono = 0,176 MB/min gespeichert und ausgeliefert. Video-ABR-Ladder (360/480/720p) = 20 MB/min gespeichert, 9 MB/min ausgeliefert (Recherche Block 5). Originale fuer Cold Storage: 60 MB pro Video.
- TRAFFIC-ANNAHME: 1 Wiedergabe-Session pro Besucher, 5 Minuten tatsaechlich gehoert. S1 25.000 min, S2 400.000 min, S3 3.500.000 min ausgeliefert pro Monat.
- ASR: Soniox async 0,10 USD/h als Primaerpass (Diarization inklusive, verifiziert) plus 15% des Korpus im Zweitpass auf Speechmatics Enhanced 0,75 USD/h fuer Altkassetten und Rauschmaterial (verifiziert). Dieser Zweitpass ist die groesste Einzelposition des Ingests - ohne ihn halbiert sich der Ingest fast.
- HOSTING: Hetzner CX/CAX-Linie (nicht CPX/CCX nach der Preiserhoehung vom 15.06.2026). CX23 5,49 / CX33 8,49 / CX43 15,99 / CX53 29,49 EUR/Monat. [UNVERIFIZIERT - die Recherche sagt ausdruecklich, hetzner.com rendert Preise per JS und war nicht maschinell auslesbar; alle Hetzner-VM-Preise stammen aus zwei Sekundaerquellen, die sich um bis zu 30% unterscheiden (CX23 5,49 vs. 7,13 EUR). Vor Buchung in der Console gegenpruefen.] Zusaetzlich 20% Backup-Aufschlag und 0,60 EUR/Monat IPv4 pro VM.
- OBJECT STORAGE: Hetzner Object Storage 6,49 EUR/Monat inkl. 1 TB Storage + 1 TB Egress, darueber 8,70 EUR/TB Storage und 1 EUR/TB Egress. Cold-Archiv der Originale auf Backblaze B2 zu 6,95 USD/TB (verifiziert). CDN: Bunny Volume-Tier 0,005 USD/GB global flat (verifiziert) - NICHT das Standard-Netz, dort kostet Middle East & Africa 0,060 USD/GB, also das Zwoelffache.
- NICHT MONETARISIERT: die menschliche Review. Bei 90-180 min Review pro Audiostunde sind das S1 105-210 Personenstunden, S2 1.050-2.100, S3 6.000-12.000. Das ist der eigentliche Projektengpass und erscheint in keiner dieser Rechnungen, weil es Freiwilligenarbeit ist. Bei 15 EUR/h bezahlter Arbeit waere S3 allein dafuer 90.000-180.000 EUR.
- NICHT ENTHALTEN: Entwicklerzeit, Vereinsgruendung, Rechtsberatung, Steuerberatung, GPU fuer eventuelles Reranker-Self-Hosting (wird ausdruecklich nicht empfohlen, siehe Hebel).

---
## Größte Hebel

- ANTWORT-CACHE (Hebel 1, mit Abstand groesster Effekt). Jeder Prozentpunkt Cache-Trefferquote senkt Synthese, Verifier und Reranking gleichzeitig. S3: Trefferquote 0% -> 2.715,84 EUR Synthese (Sonnet); 60% -> 2.715,84 x 0,4 = 1.086,34 EUR... bzw. in der Rechnung oben 75% -> 1.697,40 EUR gegenueber 6.789,60 EUR bei 0%. Jeder Prozentpunkt ist bei S3 ca. 67 EUR/Monat wert. Konkret: 75% statt 60% spart 1.018 EUR/Monat. Pre-Caching der Top-5.000 Fragen ist damit nicht primaer eine Kostenmassnahme, sondern zahlt sich doppelt aus, weil es gleichzeitig die einzige realistische Moeglichkeit ist, Antworten VOR Auslieferung von einem Bruder mit Ilm gegenlesen zu lassen.
- MODELLWAHL FUER DIE SYNTHESE (Hebel 2). Sonnet 5.5 statt Opus 5.5 halbiert die groesste Einzelposition exakt: 0,0246 vs. 0,0492 USD pro Antwort. S2: -339,48 EUR/Monat. S3: -2.715,84 EUR/Monat bei 60% Cache. Das ist kein Sparen am falschen Ende, solange die Zitate per search_result-Bloecke erzwungen und vom Verifier geprueft werden - die Attributionstreue kommt aus der Architektur, nicht aus der Modellgroesse. Empfehlung: Routing nach Komplexitaet - Sonnet als Default, Opus nur fuer Fragen mit erkanntem Ikhtilaf ueber mehrere Gelehrte. Bei 20% Opus-Anteil liegt S3 bei 2.172 EUR statt 1.697 EUR (Sonnet pur) oder 5.432 EUR (Opus pur).
- PROMPT-CACHING (Hebel 3). 6.000 der 14.000 Input-Token zu 0,05x statt 1,00x: -31,7% auf die Synthesekosten, ein einziger cache_control-Parameter. S2: -213 EUR/Monat bei Opus. S3: -850 EUR/Monat bei Sonnet und 75% Cache. Voraussetzung ist ein stabiler System-Prompt - wer das Glossar bei jeder Anfrage dynamisch zusammenbaut, zerstoert den Cache-Hit und merkt es nur an der Rechnung.
- AUDIO STATT VIDEO ALS DEFAULT-AUSLIEFERUNG (Hebel 4, der groesste nicht-LLM-Hebel). Opus 24 kbit/s mono = 0,176 MB/min gegen 9 MB/min bei Video. S3: Medienkosten 9,26 EUR statt 179,12 EUR, Faktor 19. Bei Fatawa ist das Bild fast immer ein Standbild oder ein Scheich am Mikrofon - der Informationsverlust ist fast null, und 24 kbit/s laeuft auf jedem 2G-Netz im Maghreb. Das ist zugleich eine Architekturentscheidung, keine spaetere Optimierung: Deep-Links auf die Sekunde sind bei einer einzelnen progressiv ausgelieferten Datei zuverlaessiger als bei segmentiertem HLS.
- ASR-ZWEITPASS-QUOTE (Hebel 5, der groesste Ingest-Hebel). Der Speechmatics-Enhanced-Zweitpass auf 15% des Korpus kostet 103,50 EUR je 1.000 h und ist damit 39% des gesamten Ingests. Bei S3 sind das 414 EUR von 1.191 EUR. Die Quote muss durch Confidence-Schwellen gesteuert werden, nicht pauschal gesetzt: wenn das Bake-off zeigt, dass Soniox auf eurem Material schon bei 8% kritisch wird, halbiert das die Position. Umgekehrt: Soniox allein ist mit 0,10 USD/h so billig, dass ein kompletter Zweitpass mit einem anderen guenstigen Anbieter (statt Speechmatics) zum Vergleichen nur 92 EUR je 1.000 h kostet.
- BATCH-API IM INGEST (Hebel 6). Uebersetzung, QA und Tagging ueber die Batch-API statt synchron: pauschal -50%. S3: 198 EUR einmalig gespart. Klein in absoluten Zahlen, aber es ist ein Flag, kein Umbau - es gibt keinen Grund, es nicht zu setzen.
- HOSTING-WAHL IST KEIN HEBEL MEHR, SONDERN EIN KOSTENRISIKO. Hetzner CX-Linie statt CPX/CCX nach der Preiserhoehung vom 15.06.2026 (CCX23 stieg von 31,49 auf 85,99 EUR, Faktor 2,73). Wer aus Gewohnheit CCX bucht, zahlt bei S3 statt 104,46 EUR etwa 280 EUR Serverkosten. Das sind 175 EUR/Monat - mehr als die gesamte Medienauslieferung im Audio-Modus. Aber gemessen an 1.700 EUR Synthese ist auch das Rauschen.
- RERANKER NICHT SELF-HOSTEN. Voyage rerank-3-lite kostet bei S3 20,70 EUR/Monat; eine dauerhafte A5000 fuer bge-reranker-v2-m3 kostet 116,80 USD = 107,46 EUR/Monat. Der Reranker ist die eine Komponente, bei der die API auch im grossen Szenario deutlich billiger bleibt - und sie ist jederzeit austauschbar, weil ein Reranker-Wechsel eine Konfigzeile ist und keine Reindexierung ausloest.

---
## Wo die Rechnung explodiert

- ARABISCHER TOKENFAKTOR HOEHER ALS 4/WORT. Die gesamte Rechnung haengt an dieser einen ungemessenen Zahl. Bei 5,5 Token/Wort steigen Uebersetzung, Contextual Retrieval, Embeddings UND die 14.000 Input-Token je Synthese um 37%. S3 waere dann ca. 2.700 statt 2.060 EUR/Monat, der Ingest ca. 1.550 statt 1.190 EUR. SCHUTZ: vor dem Budget-Commit 20 echte Transkripte durch messages.count_tokens schicken und den Faktor messen. Das ist eine Stunde Arbeit und verschiebt sonst jede Zahl hier.
- CACHE-TREFFERQUOTE BLEIBT UNTER 30%. Die Schwelle von 0,97 plus lexikalisches Gate (Jaccard >= 0,8) ist bewusst streng, weil in diesem Korpus ein einziges Wort die Antwort kippt (musafir vs. muqim, Negation). Wenn die reale Fragenverteilung sehr breit ist, bleibt der Cache leer. S3 ohne Cache bei Sonnet: 6.789,60 EUR Synthese statt 1.697,40 EUR. SCHUTZ: Pre-Caching aus den tatsaechlichen Fragen der ersten Wochen plus einer kuratierten Liste klassischer Masail; Cache-Trefferquote als Dashboard-Metrik von Tag 1; wenn sie nach 4 Wochen unter 40% liegt, Modellwahl neu bewerten statt mehr Server kaufen.
- BOT ODER SCRAPER FLUTET DEN CHAT-ENDPUNKT. Ein einzelner Angreifer mit 100.000 langen Fragen ueber Nacht erzeugt bei Opus 100.000 x 0,0741 USD = 7.410 USD = 6.817 EUR. Das ist die realistischste Art, dieses Projekt in einer Nacht zu zerstoeren, und Rate-Limiting per IP ist umgehbar. SCHUTZ (vierfach, nicht einfach): (1) harter Tages-Hardcap in EUR im Code, der den Endpunkt abschaltet - nicht der Kosten-Alarm beim Provider, der feuert erst, wenn das Geld weg ist; (2) Cloudflare Turnstile vor dem Endpunkt; (3) max_tokens-Deckel auf Input UND Output; (4) semantischer Cache, der identische Floodings gar nicht erst ans Modell laesst.
- VIRALER MOMENT. Ein Video eines bekannten Da'i, das auf die Plattform verweist, kann den Traffic ueber Nacht verzehnfachen. Bei Video-Auslieferung waere S3 x 10 ein Egress von 307 TB = 1.538 USD = 1.415 EUR in einem Monat. SCHUTZ: Audio-only als Default (dann sind dieselben x10 nur 27,70 EUR), plus Cloudflare R2 als Hot-Origin, weil dort der Egress strukturell null kostet - das ist keine Optimierung, sondern eine Versicherung.
- GEMINI-PREISVERDOPPLUNG ZUM 01.01.2027 (offiziell angekuendigt: Flash 0,75 -> 1,50 Input, 3,75 -> 7,50 Output). Wer sein Budget auf den aktuellen Flash-Preisen aufbaut, hat in Phase 2 die doppelten Kosten. Analog: gpt-5.6-sol ist laut Recherche Promo-Preis bis 21.11.2026 [UNVERIFIZIERT]. SCHUTZ: Modellaufrufe hinter ein eigenes Interface mit drei Rollen (synthesize, cheap_task, verify) legen - ein Providerwechsel ist dann eine Konfigzeile, kein Umbau.
- EMBEDDING-MODELLWECHSEL MIT FALSCHEM SCHEMA. Der Re-Index selbst kostet fast nichts (55 EUR bei S3). Teuer wird er nur, wenn die Embeddings als Spalte in der chunk-Tabelle liegen statt in einer nach model_id partitionierten Tabelle - dann bedeutet ein Wechsel Downtime, Doppelschreiben und im schlimmsten Fall ein Rollback, waehrend der Chatbot aus einem halb migrierten Index antwortet. SCHUTZ: embedding(chunk_id, model_id, vec) plus app_config.active_embedding_model_id von Tag 1, CREATE INDEX CONCURRENTLY, Umschalten per Konfigwert.
- ASR AUF REALEM MATERIAL VIEL SCHLECHTER ALS IM BENCHMARK. Die zitierten 6,5-10,8% WER stammen von FLEURS (sauber gelesenes MSA im Studio). Alte Kassetten mit Raumhall und Nadschdi-Einschlag liegen bei 20-40%. Das sprengt nicht die ASR-Rechnung (die bleibt bei 0,10 USD/h), sondern die Review-Rechnung: statt 90 min pro Audiostunde werden es 180+, und bei S3 sind das 12.000 Personenstunden statt 6.000. SCHUTZ: WER auf 20 echten Clips messen, BEVOR das Korpusziel festgelegt wird; Architektur so bauen, dass ungeprueftes Material sichtbar gekennzeichnet wird und nie als woertliches Zitat ausgegeben wird; Review nach Retrieval-Treffern priorisieren statt den Korpus linear abzuarbeiten.
- CLOUDFLARE STREAM ODER MUX STATT GB-BASIERTER ABRECHNUNG. Bei S3 (240.000 Katalogminuten) kostet Cloudflare Stream allein fuer die SPEICHERUNG 240.000/1.000 x 5 USD = 1.200 USD = 1.104 EUR pro Monat, bevor irgendwer etwas anschaut. Mux waere 720 USD = 662 EUR. Das ist ein stiller Projektkiller, weil die Rechnung mit dem Archiv waechst, nicht mit der Nutzung. SCHUTZ: ausschliesslich GB-basierte Anbieter (Bunny, R2, Hetzner Object Storage, B2).
- HETZNER ERHOEHT ERNEUT. 2026 gab es bereits eine Erhoehung um Faktor 2,2-2,7 bei CPX/CCX. Bestandspreise bleiben laut Ankuendigung erhalten - aber nur bis zum naechsten Rescale, also genau in dem Moment, in dem man waechst. SCHUTZ: Deployment als Docker Compose / Terraform statt Managed-Konsole, damit ein Providerwechsel ein Wochenende ist; Export-First ohnehin, weil Deplattformierung bei diesem Inhaltstyp ein reales Risiko ist.
- GOOGLE-DRIVE-INGEST STIRBT AN QUOTEN ODER SERVICE-ACCOUNT-FALLSTRICKEN. Kostet kein Geld, aber Wochen Entwicklerzeit - und Entwicklerzeit ist in einem Ein-Personen-Team die teuerste Ressource im Projekt. Service Accounts haben keinen eigenen Speicher (403 storageQuotaExceeded ohne Shared Drive und damit ohne Google Workspace), watch-Channels laufen nach 1 bzw. 7 Tagen ohne Auto-Renew ab, und seit 01.05.2026 gilt fuer neue Projekte ein anderes Quota-Modell als fuer Testprojekte. SCHUTZ: changes.list-Polling mit persistiertem startPageToken statt watch-Channels, und so frueh wie moeglich auf ein eigenes presigned-URL-Formular umstellen - dort sind scholar_id und source_url technisch erzwingbar, was gleichzeitig das religioese Kernproblem loest.

---
## Billigster tragfähiger Weg

GUENSTIGSTER TRAGFAEHIGER WEG - und zwar tragfaehig im Sinne der Zuschreibungstreue, nicht nur im Sinne des Preises.

PHASE 1 (0-500 Videos): ca. 25 EUR einmalig + 85 EUR/Monat
Eine einzige Hetzner CX33 (8,49 EUR) traegt App, Worker, Postgres mit pgvector und pg_search sowie Redis. Audio-only als Default-Auslieferung von Tag 1 - das ist keine Sparmassnahme, die man spaeter nachruestet, sondern eine Architekturentscheidung, die bei S3 den Faktor 19 bei den Medienkosten ausmacht. ASR ueber Soniox (0,10 USD/h), Uebersetzung segmentweise mit Haiku 5.5 ueber die Batch-API, Embeddings mit BGE-M3 auf einer Miet-GPU fuer wenige Stunden, Reranking ueber Voyage rerank-3-lite im 200M-Freikontingent (das traegt die gesamte Beta kostenlos). Synthese mit Opus 5.5, weil bei 1.400 Antworten/Monat die 63 EUR es wert sind und die ersten Antworten die Vorlage fuer alle spaeteren sind. Prompt-Caching von Anfang an, auch wenn es bei 2.000 Fragen nur 51% spart - der Code dafuer soll schon stehen, wenn das Volumen kommt.

DIE EINZIGE AUSGABE, DIE MAN HIER NICHT SPAREN DARF: das 20-Clip-Bake-off der ASR-Anbieter auf eurem echten Material. Es kostet dank Speechmatics-Startguthaben (100 USD) und Gladia (50 EUR) praktisch nichts, und es entscheidet ueber die Review-Last der naechsten drei Jahre - also ueber die einzige Groesse in diesem ganzen Modell, die in Personenjahren statt in Euro gemessen wird.

PHASE 2 (bis 5.000 Videos): ca. 210 EUR einmalig + 434 EUR/Monat
Hier faellt die eine Entscheidung, die alles andere dominiert: Synthese von Opus auf Sonnet 5.5 umstellen, sobald die Zitat-Pipeline (search_result-Bloecke, Verifier mit Attributionspruefung gegen scholar_id) bewiesen hat, dass die Treue aus der Architektur kommt und nicht aus der Modellgroesse. Das halbiert 679 EUR auf 339 EUR. Parallel den Antwort-Cache auf 50% bringen. Drei VMs statt einer, weil Request-Latenz, Batch-CPU und Datenbank unterschiedliche Lastprofile sind. Monitoring auf GlitchTip self-hosted. Immer noch keine dedizierte Vektordatenbank, kein Qdrant, kein Meilisearch - bei 240.000 Vektoren waere das reiner Betriebsaufwand und, schlimmer, ein zweiter Zustand, der vom Review-Stand abweichen kann.

PHASE 3 (bis 30.000 Videos): ca. 1.190 EUR einmalig + 2.060 EUR/Monat
Sonnet als Default mit Opus-Routing nur fuer erkannten Ikhtilaf, Cache-Trefferquote auf 75% durch Pre-Caching der Top-5.000 Fragen mit menschlichem Freigabeschritt. Vier VMs, Audio-only, Bunny Volume-CDN. 2.060 EUR/Monat sind fuer ein Spendenprojekt viel, aber erreichbar - und 82% davon ist eine einzige Position, die Synthese, die direkt am Nutzen haengt. Die gesamte Infrastruktur kostet 156 EUR.

WORAN MAN DEN WEG ERKENNT: In jeder Phase gilt dieselbe Form. Ein Postgres, ein Objektspeicher, Audio statt Video, Batch-API im Ingest, Prompt-Cache und Antwort-Cache ueberall, Reranker als API statt self-hosted, und ein Modellinterface mit drei Rollen, damit der Provider austauschbar bleibt. Was sich zwischen den Phasen aendert, ist nicht die Architektur, sondern nur die Instanzgroesse und das Syntheseemodell.

WAS MAN SICH VOM GELD NICHT KAUFEN KANN: Der Ingest fuer 4.000 h kostet 1.190 EUR und ist damit billiger als eine Woche Entwicklerzeit. Die menschliche Review desselben Materials sind 6.000-12.000 Personenstunden, also bei 20 aktiven Freiwilligen zu je 4 h/Woche zwischen anderthalb und drei Jahren. Das ist die wahre Kostenkurve dieses Projekts, und sie steht in keiner Zeile oben. Jede Architekturentscheidung sollte danach beurteilt werden, ob sie diese Zahl senkt - Review nach Retrieval-Treffern priorisieren, segmentweise uebersetzen lassen statt frei uebersetzen (halbiert den Aufwand pro Eintrag), Quran-Zitate per Lookup aus dem kanonischen Text einsetzen statt vom Reviewer korrigieren lassen, und ungeprueftes Material sichtbar kennzeichnen statt es zurueckzuhalten. Ein System, das nur mit vollstaendig geprueftem Korpus funktioniert, wird nie live gehen.