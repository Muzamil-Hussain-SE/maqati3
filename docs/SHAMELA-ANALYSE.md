# Shamela — was man übernehmen sollte

*Recherche 2026-10-20. Internes Dokument.*

## Was Shamela ist

shamela.ws ist eine Bibliothek **klassischer Bücher**, nicht von Audio: ~8.000 Werke,
~3.000 Autoren, ~7 Mio. Seiten, 40 Kategorien. Zitiert wird nach **gedrucktem Band und
Seite**. Das Projekt beschreibt sich als kostenlos und nicht gewinnorientiert.

Für uns ist das strukturell dieselbe Aufgabe mit einem anderen Träger:

| Shamela | Wir |
|---|---|
| gedruckte Seite | Sekunde im Audio |
| Band/Seite als Zitatanker | Zeitmarke als Zitatanker |
| Edition und Muhaqqiq | Aufnahme und Quelle |
| Fußnote des Herausgebers | Worte des Fragestellers |

Deshalb lohnt der Blick: sie haben dieselben Zitierprobleme zehn Jahre früher gelöst.

## Es gibt keinen offiziellen MCP-Server und keine offene API

Drei Dinge existieren, alle von Dritten:

- **[themuhammad-personal/shamela-mcp](https://github.com/themuhammad-personal/shamela-mcp)** — MIT, Cloudflare Workers, 14 Tools, **scrapt** shamela.ws-HTML. Speichert nur kleine Zitat-Indizes, keinen Buchtext. Lauffähiger öffentlicher Endpunkt.
- **[qurangallery/kb-mcp](https://github.com/qurangallery/kb-mcp)** — gehostet, **Server-Quellcode nicht veröffentlicht**, eigene Kopie des Korpus, 14 Tools, erzwungene Such-Scopes, Rate-Limits, optionaler Gratis-Key. Nur die Doku ist CC BY.
- **[ragaeeb/shamela](https://github.com/ragaeeb/shamela)** — MIT, TypeScript, spricht die **offizielle v4-API** (`/api/books`, `/api/master_patch`). Braucht einen Key, den es nur direkt von `mail@shamela.ws` gibt.

Shamela selbst hat ein KI-Werkzeug („اسأل الشاملة", shamela.ws/ai): Login per Google/Apple
nötig, Antworten mit anklickbaren Quellenverweisen in die Bücher, und genau ein Disclaimer,
sinngemäß: *dies ist nur ein Werkzeug, um Informationen zugänglich zu machen; prüfe die
Quellen, bevor du dich darauf stützt.* Bemerkenswert: **kein Wort zu Fatwa oder Urteilen.**
Wir gehen hier bewusst weiter als sie.

---

## Die fünf Dinge, die wir übernehmen sollten

### 1. `span_role` — der wichtigste Fund

QuranGallery markiert bei jedem Treffer `matchedIn: body | footnote | both` und warnt
ausdrücklich: eine Fußnote, die einen anderen Autor zitiert, wird leicht dem Autor des
Buches zugeschrieben.

**Unser Äquivalent fehlt im bisherigen Entwurf.** Ein Gelehrter sagt:

> „Manche behaupten, das sei erlaubt — aber das ist falsch, und der Beweis ist …"

Zieht das Retrieval die erste Hälfte und schreibt sie ihm zu, ist das exakt der schwerste
Fehlerfall, den die Risikoanalyse benennt. Diarisierung allein reicht nicht: der Gelehrte
spricht in beiden Fällen.

Also ein Feld pro Zeile, vom Modell vorgeschlagen und beim Review bestätigt:

```
span_role:  scholar_own      die eigene Aussage des Gelehrten
            questioner       Worte des Fragestellers
            quoted_other     zitierte fremde Position
            recited_text     verlesener Quran-, Hadith- oder Buchtext
            unclear          nicht entscheidbar
```

Nur `scholar_own` darf als Position des Gelehrten zitiert werden. Der Rest bleibt im Index
(er ist für den Kontext nötig), ist aber nicht zitierfähig.

### 2. `citable` als eigenes Flag, auf Zitat-Ebene

Shamela trennt Werke mit echter Druckseitenzählung (7.177) von automatisch nummerierten
(1.417) und markiert jeden Treffer entsprechend. Für Letztere wird **keine formale
Zitation** ausgegeben.

Unser Äquivalent: eine Zeile, deren Zeitmarke aus dem ASR-Lauf stammt und menschlich
bestätigt wurde, gegen eine, bei der das nicht gilt (importierte Transkripte, Alignment
unterhalb der Schwelle). Wir hatten `zuschreibung` auf **Eintragsebene** — das hier gehört
zusätzlich auf **Zeilenebene**.

### 3. Pflicht-Scope statt freier Suche

QuranGallery verlangt bei jeder Suche einen von zwölf Scopes (`hadith-primary`,
`tafsir-canonical`, `fiqh-hanafi` …). Es gibt keine ungescopte Suche.

Das ist strenger als unser `content_class`-Routing und besser: ein Scope, der gesetzt werden
**muss**, kann nicht vergessen werden. Für uns: Gelehrter, Themenbereich oder „alles
Freigegebene" — aber eine bewusste Angabe, kein Default.

### 4. `{"found": false}` auf Tool-Ebene

Der eine Server gibt `found: false` zurück, wenn eine Zitation auf der Live-Seite nicht
verifizierbar ist. Das Abstain-Verhalten sitzt damit **im Werkzeug**, nicht im Prompt — und
ist dadurch nicht wegzureden.

### 5. Grounding-Regeln als eigene Ressource

QuranGallery liefert `qurangallery://grounding-rules` als MCP-Resource mit. Die Regeln, wie
das Modell die Daten verwenden darf, sind Teil der Schnittstelle, nicht Teil unseres
Prompts. Passt genau zu unserem Prinzip „Integrität ins Schema, nicht in den Prompt".

---

## Der strategische Punkt: ein eigener MCP-Server

Wenn unser Archiv einen MCP-Server anbietet, kann jeder in Claude oder ChatGPT die Worte der
Gelehrten mit sekundengenauen Zitaten abfragen — ohne dass wir eine Chat-Oberfläche bauen.

Das entschärft genau das Akzeptanzrisiko aus der Risikoanalyse (*„man fragt keine
Maschine"*): **Wir sind dann nicht die antwortende Instanz.** Das Modell gehört dem Nutzer,
unser Beitrag sind nachprüfbare Quellen. Das ist inhaltlich ehrlicher und politisch
erheblich leichter zu verteidigen als ein eigener Chatbot.

Aufwand: etwa 2–3 Tage auf die Phase-2-API obendrauf, weil Retrieval, Zitatanker und
Filterlogik ohnehin existieren. Als Verbreitungsweg ist es das Billigste, was es gibt —
keine Oberfläche, kein SEO, keine App.

**Empfehlung: MCP-Server vor dem eigenen Chatbot bauen.**

---

## Daten: wenig direkt, viel als Referenz

Bücher sind nicht unser Material. Aber als **Nachschlagekorpus** ist Shamela wertvoll:
Auflösen von Quran- und Hadith-Zitaten in den Transkripten, Überliefererbiografien,
klassische Terminologie. Genau die Tools `get_hadith_by_number` und
`get_narrator_biography` sind das, was unser Zitat-Erkennungsschritt braucht.

**Rechtlich sauber bleiben:**

- shamela.ws veröffentlicht **keine Lizenz**. „Kostenlos und nicht gewinnorientiert" ist
  keine Nutzungserlaubnis. Nicht spiegeln.
- OpenITI ist frei herunterladbar und trägt Shamela-IDs in den Dateinamen, aber die
  Lizenzlage der Texte ist unklar — die Werke selbst sind meist gemeinfrei, die **Editionen
  nicht**.
- Der saubere Weg ist der, den die MIT-Bibliothek selbst nennt: **Key anfragen bei
  `mail@shamela.ws`.** Das gehört in denselben Stapel wie die Erlaubnisschreiben an
  binothaimeen.net und die anderen — gleiche Vorlaufzeit, gleicher Ton.
- Der **Code** ist MIT und darf verwendet werden.

---

## Einordnung in unsere Phasen

| Wann | Was |
|---|---|
| **Phase 1** | Nichts von Shamela nötig. `span_role` und `citable` aber **jetzt ins Schema** — nachträglich über veröffentlichte Einträge legen ist teuer. |
| **Phase 2** | Pflicht-Scope, `found: false`, Grounding-Regeln als Ressource. Kosten praktisch null, schließen ein reales Loch. |
| **Phase 2/3** | Eigener MCP-Server, vor dem eigenen Chatbot. |
| **parallel** | Mail an `mail@shamela.ws` wegen API-Key, zusammen mit den übrigen Erlaubnisschreiben. |

---

# Nachtrag: Shamelas KI-Werkzeug, analysiert

*Quelle: das öffentlich ausgelieferte Frontend-Bundle `assets/js/ai.js` (~168 KB), das
jeder Browser beim Aufruf von shamela.ws/ai bekommt. Kein Login umgangen, kein Account
angelegt — die Antwortinhalte und die Tool-Definitionen liegen hinter der Anmeldepflicht
und bleiben dort.*

## Beobachteter Stack

- Hauptseite: **CodeIgniter / PHP** (erkennbar an der Standard-Fehlerseite)
- Authentifizierung: `/api/auth/browser/v1/…` — die Pfadform von **django-allauth
  (headless)**. Also ein getrennter Auth-Dienst neben der PHP-Seite.
- KI-Frontend: handgeschriebenes JS plus `markdown-it` zum Rendern. **Kein React, kein
  Vue.** Für eine Seite, die auf schwachen Geräten in MENA laufen muss, eine bewusste und
  gute Entscheidung.
- Kein `robots.txt` (404).

## API-Oberfläche

```
/api/ai/v1/threads          Konversationen
/api/ai/v1/threads/sync
/api/ai/v1/runs             eine Frage = ein Run
/api/ai/v1/runs/{id}        SSE-Stream
/api/ai/v1/runtime
/api/ai/v1/status
/api/ai/v1/shares/{id}      geteilte Konversation
/api/account/v1/account
/ai/examples/index          Beispielfragen
```

**Run-Lebenszyklus:** `queued → running → completed | failed | aborted`.

**SSE-Events:** `run_started`, `tool_call_started`; Payload-Typen `answer_delta`,
`answer_snapshot`, `sources_updated`.

`tool_call_started` ist der aufschlussreichste Fund: **sie machen agentisches Retrieval,
kein einmaliges RAG-Prefill.** Das Modell entscheidet selbst, wann und wonach es in der
Bibliothek sucht, und das Frontend zeigt diese Schritte an.

**Zitate:** nummerierte Marken im Antworttext (`reference_id`, `citation_reference_ids`),
Quellen separat mit `book_id`, `page_id`, `url`. Klick öffnet einen Lesebereich auf der
Buchseite. Auffällig: `normalize_reference_number` und `reference_digits` — sie müssen
Ziffern normalisieren, arabisch-indisch gegen lateinisch. **Genau das Problem, das unsere
Frontend-Notiz zur Bidi-Isolation bei Zahlen beschreibt.** Gute Bestätigung.

## Drei Dinge, die ich übernehmen würde

### 1. `answer_delta` **und** `answer_snapshot` nebeneinander

Sie streamen Deltas, schicken aber regelmäßig den vollständigen Stand. Bei Markdown mit
eingebetteten Zitatmarken ist das der Unterschied zwischen robust und „Darstellung zerfällt,
sobald ein Delta verlorengeht oder mitten in einer Struktur ankommt". Kostet fast nichts und
löst ein Problem, das wir sonst erst im Betrieb gemerkt hätten.

### 2. Quellen als eigener Kanal, nicht im Antworttext

`sources_updated` läuft parallel zur Antwort und wird fortlaufend nachgemerged — kein
einmaliges Vorab-Senden. Unser Blueprint sagte „SSE mit sources-first"; das hier ist die
genauere Form.

### 3. Der Run als persistentes Objekt statt Request/Response

Eine Frage ist ein Job mit Status, kein HTTP-Austausch. Das gibt für fast nichts:

- Wiederaufnahme nach Verbindungsabbruch (auf dem Handy der Normalfall)
- Teilen einer Antwort per Link (`/shares/`)
- **Und für uns entscheidend:** einen natürlichen Platz für den Verifier-Durchlauf und die
  Muraji-Freigabe, weil der Run ein Objekt bleibt, das man später noch anfassen kann.

Unser Entwurf hatte synchrones SSE. Das hier ist besser, und es ist kein Mehraufwand, wenn
man es von Anfang an so baut — die Job-Tabelle existiert ohnehin.

## Was sie nicht haben

- **Kein Rollen-Flag auf Span-Ebene.** Haupttext gegen Fußnote gegen zitierte Fremdposition
  — das hat QuranGallery, Shamela selbst nicht. Unser `span_role` bleibt der richtige Weg.
- **Kein sichtbares Abstain-Verhalten.** Keine Spur eines „dazu liegt nichts vor"-Pfades.
- **Anmeldepflicht.** Für uns ausgeschlossen: Fragen zu religiösen Themen sind Art.-9-Daten,
  und ohne Account sind sie gar nicht erst mit einer Identität verknüpfbar.
- **Nur ein knapper Disclaimer**, sinngemäß „nur ein Hilfsmittel, prüfe die Quellen" — kein
  Wort zu Fatwa oder Urteilen.

## Grenze der Analyse

Was hinter der Anmeldung liegt — die tatsächlichen Tool-Definitionen, das verwendete Modell,
die Prompts, die Retrieval-Parameter — ist von außen nicht beobachtbar, und ich habe nicht
versucht, dorthin zu kommen. Wer es genau wissen will, legt einen eigenen Account an und
schaut im Netzwerk-Tab seines Browsers mit. Das ist dann deine Entscheidung, nicht meine.

---

# Nachtrag 2: REA-Durchlauf gegen shamela.ws/ai

*REA 6.7.0 (`rea-agents`, MIT, github.com/morluto/rea), CLI direkt aufgerufen — nicht als
MCP-Server, weil dessen Registrierung die Agent-Konfiguration ändert und einen Neustart
verlangt. Analyse in einer isolierten headless-Chrome-Instanz mit eigenem Profil.*

## Was gelaufen ist

```
list-browser-targets          Target gefunden
analyze-web-bundle            5 Skripte, 57.269 AST-Knoten geparst
inspect-web-page              383 KB Capture: DOM, Skripte, Storage, Netzwerk
export-web-scripts            3 Quelldateien, 288 KB
analyze-javascript-application 30.704 Knoten, 37.078 Relationen, 601 Fingerprints
```

## Ergebnis: REA fand weniger als ein gezielter grep

**Erkannte Endpunkte: null.** Der manuelle Durchlauf über dasselbe Bundle hatte vierzehn
gefunden (`/api/ai/v1/runs`, `/threads`, `/shares/` …).

Der Grund steht in REAs eigener Unknown-Bilanz:

| Kategorie | Anzahl |
|---|---|
| `object-flow / ambiguous-target` | 5.020 |
| `data-flow / unknown-value` | 2.431 |
| `call-flow / dynamic-call` | 1.846 |
| `object-flow / dynamic-property` | 495 |

Shamelas KI-Frontend ist handgeschriebenes, stark dynamisches JavaScript. URLs werden zur
Laufzeit zusammengesetzt, und statische Analyse kann das prinzipiell nicht auflösen. REA
sagt das in seinen Limitations ausdrücklich — *„String-built routes and endpoints … may
remain unknown"* —, und dass es lieber Unknowns meldet als zu raten, ist ein Qualitäts-
merkmal, kein Mangel.

Dazu kommt: `analyze-javascript-application` ist auf **Electron** ausgelegt. Sein gesamter
Summary-Block (browser_windows, IPC-Kanäle, preload-Entrypoints, context_bridge) steht bei
einer normalen Webseite auf null.

## Was REA trotzdem geliefert hat

- Verifiziertes Skript-Inventar mit SHA-256 je Datei — brauchbar als Grundlage für
  Versionsvergleiche (`compare-application-versions`), wenn man die Seite über Zeit beobachten will
- 601 Funktions-Fingerprints (normalisierter AST + Control-Flow-Hash) — damit erkennt man
  umbenannte oder verschobene Funktionen zwischen zwei Ständen wieder
- Eine saubere, maschinenlesbare Bilanz dessen, was *nicht* bestimmbar war
- Nebenbei: Cloudflare sitzt vor shamela.ws (`cdn-cgi/challenge-platform`), kein robots.txt

**Netzwerkmitschnitt der KI-Aufrufe: nicht möglich.** Die Endpunkte feuern erst nach
Anmeldung. Ich habe keinen Account angelegt und nichts umgangen.

## Einordnung

Für eine serverseitig gerenderte PHP-Seite mit dynamischem Frontend ist REA das falsche
Werkzeug — nicht weil es schlecht ist, sondern weil seine Stärke bei Binaries, APKs und
Electron liegt.

**Wo es für dieses Projekt wirklich passen würde:**

1. **Die Shamela-Android-App** (`com.arabdt.shamla`) — `decode-android-resources`,
   `inspect-android-class`, `inspect-android-method`. Mobile Apps tragen Endpunktlisten und
   Request-Schemata im Paket, anders als Web-Frontends. Das ist das richtige Ziel, wenn man
   die API-Form wirklich wissen will. Braucht JADX und ein volles JDK (beides nicht
   installiert).
2. **Die Shamela-4-Desktop-Datenbanken** — REA kann SQLite. Nur relevant, falls wir jemals
   Bücher aufnehmen.
3. **Unsere eigene App später** — prüfen, was unser Frontend-Bundle preisgibt, und
   Versionsstände vergleichen.

**Grenze, die ich nicht überschreite:** Dekompilieren zur Interoperabilitätsanalyse ist in
der EU unter engen Bedingungen zulässig (Art. 6 Softwarerichtlinie, § 69e UrhG). Eingebettete
Zugangsschlüssel herauszuziehen, um ihren Dienst ohne Erlaubnis zu nutzen, ist es nicht —
und wäre hier auch unsinnig, weil wir sie ohnehin per Mail um einen Key bitten wollen.
