# Bug Report: `load_adventure` - Fallimento caricamento avventure da 5etools

**Data:** 2026-02-17
**Avventura testata:** Baldur's Gate: Descent Into Avernus (BGDIA)
**Componente:** `dm20_protocol.adventures.parser.AdventureParser`
**Severita:** Alta - il tool `load_adventure` non funziona per nessuna avventura

---

## Sintesi

Il tool `load_adventure` presenta **due bug distinti** che impediscono il corretto caricamento delle avventure da 5etools:

1. **BUG 1 - Case Sensitivity nell'URL di download** → il download fallisce con 404
2. **BUG 2 - Parsing errato della struttura JSON** → anche con il file in cache, i capitoli non vengono riconosciuti

---

## BUG 1: Case Sensitivity nell'URL di download

### Problema

Il campo `adventure_id` viene passato **senza normalizzazione** alla costruzione dell'URL e del path di cache.

**File:** `adventures/parser.py`

```python
# Riga 36-39 — Template URL
ADVENTURE_BASE_URL = (
    "https://raw.githubusercontent.com/5etools-mirror-3/"
    "5etools-src/main/data/adventure/adventure-{id}.json"
)

# Riga 164 (ORIGINALE) — Download: l'ID viene usato così com'è
url = ADVENTURE_BASE_URL.format(id=adventure_id)

# Riga 138 (ORIGINALE) — Cache: l'ID viene usato così com'è
cache_file = self.cache_dir / f"{adventure_id}.json"

# Riga 187 (ORIGINALE) — Salvataggio cache: idem
cache_file = self.cache_dir / f"{adventure_id}.json"
```

### Catena di inconsistenze

| Sorgente | ID usato | Formato |
|----------|----------|---------|
| `adventures.json` (indice 5etools) | `BGDIA` | UPPERCASE |
| Docstring `load_adventure` in `main.py:3929` | `BGDiA` | mixedCase |
| URL file su GitHub 5etools | `adventure-bgdia.json` | lowercase |
| `index.py:get_by_id()` | case-insensitive | `.lower()` |
| `parser.py:_download_adventure()` | **case-sensitive (bug)** | nessuna normalizzazione |

### Verifica

```
# URL con ID uppercase (come da indice) → 404
curl -I "https://raw.githubusercontent.com/5etools-mirror-3/5etools-src/main/data/adventure/adventure-BGDIA.json"
# → HTTP 404

# URL con ID lowercase → 200 OK
curl -I "https://raw.githubusercontent.com/5etools-mirror-3/5etools-src/main/data/adventure/adventure-bgdia.json"
# → HTTP 200 (1.3MB)
```

### Fix applicato (hotfix locale)

```python
# Riga 164 — Download URL
url = ADVENTURE_BASE_URL.format(id=adventure_id.lower())

# Riga 138 — Lettura cache
cache_file = self.cache_dir / f"{adventure_id.lower()}.json"

# Riga 187 — Scrittura cache
cache_file = self.cache_dir / f"{adventure_id.lower()}.json"
```

### Nota: hotfix non efficace a runtime

Il fix è stato applicato al file `.py`, ma il server MCP era già in esecuzione con il modulo caricato in memoria. I file `.pyc` sono stati eliminati, ma il processo Python non ricarica i moduli automaticamente. **Il fix richiede un restart del server MCP per avere effetto.**

### Workaround usato

Download manuale del file JSON nella directory di cache con il nome uppercase (che il server in esecuzione si aspettava):

```bash
curl -o data/adventures/cache/content/BGDIA.json \
  "https://raw.githubusercontent.com/5etools-mirror-3/5etools-src/main/data/adventure/adventure-bgdia.json"
```

Questo ha permesso a `_get_adventure_data()` di trovare il file in cache e saltare il download.

---

## BUG 2: Parsing errato della struttura JSON

### Problema

Dopo aver risolto il download, `load_adventure` ritorna con **zero capitoli** e il titolo sbagliato ("About the Adventure" invece di "Baldur's Gate: Descent Into Avernus").

**File:** `adventures/parser.py`, metodo `_parse_adventure_data()` (riga 221)

### Struttura reale del JSON 5etools

```json
{
  "data": [
    { "type": "section", "name": "About the Adventure", "entries": [...] },
    { "type": "section", "name": "Chapter 1: A Tale of Two Cities", "entries": [...] },
    { "type": "section", "name": "Chapter 2: Elturel Has Fallen", "entries": [...] },
    ...18 sezioni totali...
  ]
}
```

I capitoli sono **elementi diretti dell'array `data`**. Ogni sezione ha chiavi: `type`, `name`, `page`, `id`, `entries`. **Non hanno una chiave `data` annidata.**

### Cosa fa il parser (errato)

```python
# Riga 234 — Prende SOLO il primo elemento come "root"
adventure_root = data.get("data", [{}])[0] if data.get("data") else {}
# adventure_root = { "type": "section", "name": "About the Adventure", ... }

# Riga 235 — Usa il nome del primo elemento come titolo
title = adventure_root.get("name", adventure_id)
# title = "About the Adventure"  ← SBAGLIATO, dovrebbe essere il titolo dell'avventura

# Riga 243 — Cerca una chiave "data" DENTRO il primo elemento
data_entries = adventure_root.get("data", [])
# data_entries = []  ← VUOTO! Le sezioni non hanno una chiave "data", hanno "entries"
```

### Risultato

- `title` = "About the Adventure" (il nome della prima sezione, non dell'avventura)
- `chapters` = [] (lista vuota, nessun capitolo trovato)
- `npcs` = [] (vuoto)
- `locations` = [] (vuoto)

### Comportamento atteso

Il parser dovrebbe:
1. Iterare su **tutti gli elementi** di `data["data"]` come capitoli
2. Ricavare il titolo dell'avventura dall'indice (`adventures.json`) o da un campo metadata, non dal primo elemento
3. Trattare le `entries` di ogni sezione come il contenuto del capitolo

### Fix proposto

```python
def _parse_adventure_data(
    self, adventure_id: str, data: dict[str, Any]
) -> ModuleStructure:
    # Tutte le sezioni sono elementi diretti dell'array "data"
    all_sections = data.get("data", [])

    # Il titolo NON è nel JSON del contenuto — va preso dall'indice
    # Fallback: se la prima sezione è "About the Adventure", usa l'adventure_id
    first_section = all_sections[0] if all_sections else {}
    title = first_section.get("name", adventure_id)
    if title == "About the Adventure":
        title = adventure_id  # O meglio: passare il titolo dall'indice

    source = first_section.get("source", adventure_id)

    context = ParserContext()
    chapters: list[ModuleElement] = []

    # Itera su TUTTE le sezioni, non solo sulle sotto-entries della prima
    for idx, entry in enumerate(all_sections):
        if isinstance(entry, dict) and entry.get("type") == "section":
            chapter = self._parse_chapter(entry, idx + 1, context)
            if chapter:
                chapters.append(chapter)

    return ModuleStructure(
        module_id=adventure_id,
        title=title,
        source_file=f"adventure-{adventure_id.lower()}.json",
        chapters=chapters,
        npcs=list(context.npcs.values()),
        encounters=context.encounters,
        locations=list(context.locations.values()),
        metadata={"source": source},
        read_aloud=context.read_aloud,
    )
```

### Suggerimento migliorativo

Il titolo dell'avventura dovrebbe essere passato come parametro dal flusso `load_adventure_flow`, che può ottenerlo dall'indice:

```python
# In tools.py, prima di chiamare parse_adventure:
index = AdventureIndex(cache_dir=data_path)
await index.ensure_loaded()
entry = index.get_by_id(adventure_id)
adventure_title = entry.name if entry else adventure_id

# Passare il titolo al parser
module = await parser.parse_adventure(adventure_id, title=adventure_title)
```

---

## BUG 3 (minore): Docstring con ID inconsistente

**File:** `main.py:3929`

```python
# Nella docstring del tool load_adventure:
- BGDiA: Baldur's Gate: Descent into Avernus
```

L'ID suggerito è `BGDiA` (mixedCase), ma:
- L'indice 5etools usa `BGDIA` (uppercase)
- L'URL del file richiede `bgdia` (lowercase)

Questo confonde l'LLM che usa il tool. Dovrebbe riportare l'ID esatto dall'indice (`BGDIA`) dato che la normalizzazione a lowercase dovrebbe essere fatta internamente.

---

## Riepilogo fix necessari

| # | File | Riga | Fix | Priorità |
|---|------|------|-----|----------|
| 1 | `parser.py` | 164 | `.lower()` su adventure_id nell'URL | **Critica** |
| 2 | `parser.py` | 138 | `.lower()` su adventure_id nel path cache (lettura) | **Critica** |
| 3 | `parser.py` | 187 | `.lower()` su adventure_id nel path cache (scrittura) | **Critica** |
| 4 | `parser.py` | 234 | Iterare su `data["data"]` direttamente, non su `data["data"][0]["data"]` | **Critica** |
| 5 | `parser.py` | 235 | Titolo dall'indice, non dalla prima sezione | Media |
| 6 | `parser.py` | 255 | `.lower()` nel `source_file` | Bassa |
| 7 | `main.py` | 3929 | Correggere `BGDiA` → `BGDIA` nel docstring | Bassa |
| 8 | `tools.py` | — | Passare il titolo dall'indice al parser | Media |

---

## File coinvolti

```
dm20_protocol/
├── main.py                    # Tool MCP definition (riga 3899-3974)
├── adventures/
│   ├── parser.py              # Download, cache e parsing del JSON (BUG 1 + BUG 2)
│   ├── tools.py               # Orchestrazione load_adventure_flow
│   ├── index.py               # Indice avventure (get_by_id è già case-insensitive)
│   ├── models.py              # Data models (ModuleStructure, ModuleElement)
│   └── discovery.py           # Ricerca avventure per tema/livello
```

## Come riprodurre

```python
# Qualsiasi ID che non sia già lowercase fallisce
load_adventure("BGDIA")   # 404 — ID dall'indice
load_adventure("BGDiA")   # 404 — ID dalla docstring
load_adventure("CoS")     # 404 — ID dalla docstring (il file è adventure-cos.json)

# Anche con file in cache, zero capitoli vengono estratti
# perché il parser cerca data[0]["data"] invece di data["data"]
```
