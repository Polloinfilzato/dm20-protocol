# Bug Report: Import da D&D Beyond + Mancato supporto Multiclass

**Data:** 2026-02-17
**Personaggio testato:** Tassly (Rogue 5 / Artificer 4 — Lightfoot Halfling)
**URL D&D Beyond:** https://www.dndbeyond.com/characters/89112463
**Componenti:** `importers.dndbeyond`, `models.Character`, `main._format_import_summary`, `create_character`, `CharacterBuilder`
**Severita:** Alta — l'import D&D Beyond è completamente rotto; il multiclass non è supportato dal modello dati

---

## Indice

1. [BUG 1: Crash di `_format_import_summary` — import impossibile](#bug-1)
2. [BUG 2: Modello `Character` non supporta multiclass](#bug-2)
3. [BUG 3: `create_character` accetta solo una classe](#bug-3)
4. [BUG 4: Il mapper DDB perde le classi secondarie](#bug-4)
5. [Conseguenze sul personaggio Tassly](#conseguenze)
6. [Workaround adottato (e suoi limiti)](#workaround)
7. [Piano di fix proposto](#piano-fix)

---

<a id="bug-1"></a>
## BUG 1: Crash di `_format_import_summary` — import impossibile

### Errore

```
❌ Import failed: 'Character' object has no attribute 'classes'
```

### Causa

Il tool `import_from_dndbeyond` (`main.py:4429`) chiama:
1. `fetch_character()` — scarica il JSON dalla API di D&D Beyond ✅ funziona
2. `map_ddb_to_character()` — crea un oggetto `Character` ✅ funziona
3. `_format_import_summary()` — formatta il risultato ❌ **CRASH QUI**

La funzione `_format_import_summary` (`main.py:4373-4425`) è scritta per un modello `Character` **che non esiste**:

```python
# main.py:4389 — ERRORE: Character non ha .classes (ha .character_class)
if char.classes:
    class_info = char.classes[0]

# main.py:4401 — ERRORE: Character non ha .hit_points (ha .hit_points_max e .hit_points_current)
if char.hit_points:
    lines.append(f"  HP: {char.hit_points.current}/{char.hit_points.maximum}")

# main.py:4398 — PROBLEMATICO: stampa l'oggetto Race, non il nome
lines.append(f"  Race: {char.race}")
```

### Fix immediato

```python
def _format_import_summary(result) -> str:
    char = result.character
    lines = [f"✅ Character imported: {char.name}\n"]
    lines.append("Summary:")

    # Class
    if char.character_class:
        cc = char.character_class
        class_str = f"{cc.name} {cc.level}"
        if cc.subclass:
            class_str += f" ({cc.subclass})"
        lines.append(f"  Class: {class_str}")

    # Race
    if char.race:
        race_str = char.race.name
        if char.race.subrace:
            race_str += f" ({char.race.subrace})"
        lines.append(f"  Race: {race_str}")

    # HP and AC
    lines.append(f"  HP: {char.hit_points_current}/{char.hit_points_max}")
    lines.append(f"  AC: {char.armor_class}")

    # ... rest of the function ...
```

### Nota

La funzione sembra scritta per un refactor **pianificato ma mai implementato** del modello Character (con `classes: list[CharacterClass]` e `hit_points: HitPoints`). Il modello attuale non corrisponde.

---

<a id="bug-2"></a>
## BUG 2: Modello `Character` non supporta multiclass

### Il problema fondamentale

Il modello `Character` (`models.py:294`) ha:

```python
class Character(BaseModel):
    character_class: CharacterClass  # ← SINGOLARE, non una lista
```

Dove `CharacterClass` è:

```python
class CharacterClass(BaseModel):
    name: str
    level: int = Field(ge=1, le=20)
    hit_dice: str = "1d4"
    subclass: str | None = None
```

**Non c'è modo di rappresentare un personaggio multiclasse.** Un Rogue 5 / Artificer 4 può solo essere salvato come Rogue 5 O Artificer 4 — non entrambi.

### Cosa si perde senza multiclass

Per il personaggio Tassly (Rogue 5 / Artificer 4 = livello 9):

| Campo | Valore attuale (errato) | Valore corretto |
|-------|------------------------|-----------------|
| Livello visualizzato | 5 | 9 |
| Proficiency bonus | +3 (livello 5) | +4 (livello 9) |
| Hit Dice | 5d8 | 5d8 (Rogue) + 4d8 (Artificer) |
| Spell slots | nessuno | 3 slot Lv1 (Artificer 4) |
| Spellcasting ability | nessuna | Intelligence (Artificer) |
| Saving throws | DEX, INT (Rogue) | DEX, INT (Rogue primaria) + CON (multiclass Artificer) — nota: i ST addizionali NON si aggiungono con multiclass per regole RAW |
| Class features | solo Rogue 1-5 | Rogue 1-5 + Artificer 1-4 |

### Proposta di refactor: `character_class` → `classes`

```python
class Character(BaseModel):
    # PRIMA (singola classe):
    # character_class: CharacterClass

    # DOPO (multiclass nativo):
    classes: list[CharacterClass] = Field(default_factory=list)

    @property
    def total_level(self) -> int:
        """Livello totale del personaggio (somma di tutte le classi)."""
        return sum(c.level for c in self.classes)

    @property
    def primary_class(self) -> CharacterClass | None:
        """Classe primaria (quella con il livello più alto)."""
        return max(self.classes, key=lambda c: c.level) if self.classes else None

    @property
    def proficiency_bonus(self) -> int:
        """Bonus di competenza basato sul livello totale."""
        return (self.total_level - 1) // 4 + 2

    @property
    def hit_dice_summary(self) -> str:
        """Riepilogo Hit Dice per tutte le classi. Es: '5d8 + 4d8'."""
        return " + ".join(f"{c.level}{c.hit_dice}" for c in self.classes)
```

### Impatto del refactor

Cambiare `character_class` → `classes` è un **breaking change** che tocca moltissimi file. Elenco delle aree impattate:

| Area | File | Cosa cambia |
|------|------|-------------|
| Modello | `models.py` | `character_class: CharacterClass` → `classes: list[CharacterClass]` |
| Builder | `character_builder.py` | `build()` restituisce Character con `classes=[...]` |
| Tool create | `main.py:create_character()` | Accetta `additional_classes` param opzionale |
| Tool level_up | `main.py:level_up_character()` | Specifica QUALE classe sale di livello |
| DDB Mapper | `importers/dndbeyond/mapper.py` | `map_identity` mappa TUTTE le classi, non solo la primaria |
| Format summary | `main.py:_format_import_summary()` | Itera su `char.classes` |
| Sheet renderer | `sheets/renderer.py` | Visualizza tutte le classi |
| Sheet parser | `sheets/parser.py` | Parsa classi multiple |
| Validators | `rulebooks/validators.py` | Valida regole multiclass (prerequisiti, HP, proficiencies) |
| Combat | `main.py` (combat tools) | Spell slot calculation per multiclass |
| Get character | `main.py:get_character()` | Visualizza tutte le classi |
| Claudmaster agents | `claudmaster/` | CharacterSummary, agents che leggono la classe |
| Serializzazione | Storage/JSON | Migrazione dati campagne esistenti |

### Regole D&D 5e per Multiclass (da implementare)

Riferimento: PHB 2014, Capitolo 6 "Customization Options" — Multiclassing

1. **Prerequisiti**: Per prendere una seconda classe, servono 13+ nell'abilità primaria della classe ATTUALE e della NUOVA classe
2. **HP**: Si usa il Hit Die della NUOVA classe per i livelli successivi
3. **Proficiency bonus**: Basato sul livello TOTALE, non su una singola classe
4. **Spell slots**: I caster multiclasse hanno spell slot combinati secondo la tabella Multiclass Spellcaster (PHB p.165). Non si sommano semplicemente.
5. **Proficiencies guadagnate**: La seconda classe dà MENO proficiencies della prima (tabella specifica nel PHB)
6. **Extra Attack**: NON si cumula da classi diverse
7. **Channel Divinity**: Se due classi lo danno, usi totali = somma, ma le opzioni restano separate

---

<a id="bug-3"></a>
## BUG 3: `create_character` accetta solo una classe

### Stato attuale

```python
# main.py:192
def create_character(
    character_class: str,    # ← UNA sola classe
    class_level: int,        # ← UN solo livello
    subclass: str | None,    # ← UNA sola sottoclasse
    ...
)
```

### Proposta: aggiungere parametro `additional_classes`

```python
def create_character(
    character_class: str,
    class_level: int,
    subclass: str | None = None,
    additional_classes: str | None = None,  # JSON: [{"name": "Artificer", "level": 4, "subclass": "Battle Smith"}]
    ...
)
```

Oppure, per personaggi importati, un tool dedicato `add_class_to_character`:

```python
@mcp.tool
def add_class_to_character(
    name_or_id: str,
    class_name: str,
    class_level: int,
    subclass: str | None = None,
) -> str:
    """Add a new class to an existing character (multiclass)."""
```

---

<a id="bug-4"></a>
## BUG 4: Il mapper DDB perde le classi secondarie

### Stato attuale

```python
# mapper.py:54-73 — map_identity()
classes = ddb.get("classes", [])
if classes:
    # Sort by level descending, take first   ← PERDE TUTTE LE ALTRE CLASSI
    primary_class = max(classes, key=lambda c: c.get("level", 0))
    ...
    result["character_class"] = CharacterClass(
        name=class_name,
        level=class_level,  # ← Solo il livello della classe primaria
        ...
    )
```

Per Tassly, il JSON D&D Beyond contiene:
```json
"classes": [
  {"definition": {"name": "Rogue"}, "level": 5, "subclassDefinition": {"name": "Assassin"}},
  {"definition": {"name": "Artificer"}, "level": 4, "subclassDefinition": {"name": "Battle Smith"}}
]
```

Il mapper prende SOLO Rogue (level 5, il massimo) e **scarta completamente Artificer 4**.

### Inoltre: il livello per HP è sbagliato

```python
# mapper.py:692 — map_combat usa il livello della classe primaria, non il totale
level = character_data.get("character_class").level  # = 5, non 9
combat, warnings = map_combat(ddb, ..., level)

# mapper.py:179 — HP calcolato con il livello sbagliato
hp_max = base_hp + bonus_hp + (con_mod * level)  # con_mod * 5 invece di * 9
```

D&D Beyond fornisce direttamente `baseHitPoints: 63` (che è il valore corretto calcolato per livello 9), quindi l'errore è mitigato dal fatto che D&D Beyond fa già il calcolo. Ma il `con_mod * level` aggiunge un delta sbagliato se il CON modifier non è 0.

Per Tassly (CON 10, mod +0): `63 + 0 + (0 * 5) = 63` ← corretto per caso.
Per un personaggio con CON 14 (mod +2): `base_hp + 0 + (2 * 5) = base + 10` invece di `base + 18` (2 * 9).

### Fix per il mapper

```python
def map_identity(ddb: dict) -> tuple[dict, list[str]]:
    classes = ddb.get("classes", [])
    if classes:
        # Mappa TUTTE le classi, non solo la primaria
        mapped_classes = []
        total_level = 0
        for cls in sorted(classes, key=lambda c: c.get("level", 0), reverse=True):
            class_def = cls.get("definition", {})
            class_name = class_def.get("name", "Unknown")
            class_level = cls.get("level", 1)
            subclass_def = cls.get("subclassDefinition")
            subclass_name = subclass_def.get("name") if subclass_def else None
            hit_dice = CLASS_HIT_DICE.get(class_name, "d8")

            mapped_classes.append(CharacterClass(
                name=class_name,
                level=class_level,
                hit_dice=hit_dice,
                subclass=subclass_name,
            ))
            total_level += class_level

        # Quando il modello supporta multiclass:
        result["classes"] = mapped_classes
        result["_total_level"] = total_level  # per uso interno

        # Spellcasting: potrebbe avere multiple abilità
        for cls in mapped_classes:
            if cls.name in CLASS_SPELLCASTING_ABILITY:
                result["spellcasting_ability"] = CLASS_SPELLCASTING_ABILITY[cls.name]
                break  # usa la primaria
```

---

<a id="conseguenze"></a>
## Conseguenze sul personaggio Tassly

### Cosa è stato importato (manualmente, con workaround)

| Aspetto | Stato | Note |
|---------|-------|------|
| Nome, razza, background | ✅ Corretto | |
| Ability scores | ✅ Corretto | STR 10, DEX 17, CON 10, INT 13, WIS 10, CHA 15 |
| HP | ✅ Corretto (forzato) | 63/63 — impostato manualmente via `update_character` |
| AC | ✅ Corretto (forzato) | 17 — impostato manualmente |
| Classe primaria | ⚠️ Parziale | "Rogue 5" — manca Artificer 4 |
| Livello totale | ❌ Errato | Mostra 5 invece di 9 |
| Proficiency bonus | ❌ Errato | +3 (livello 5) invece di +4 (livello 9) |
| Hit Dice | ❌ Errato | "5d8" invece di "5d8 + 4d8" |
| Spell slots (Artificer) | ❌ Assenti | Dovrebbe avere 3 slot Lv1 |
| Spellcasting ability | ❌ Assente | Dovrebbe essere Intelligence |
| Features Rogue 1-5 | ✅ Auto-populate | Dal rulebook |
| Features Artificer 1-4 | ⚠️ Forzato | Aggiunte manualmente come stringhe in features_and_traits |
| Inventario | ✅ Corretto | 10 oggetti principali aggiunti manualmente |
| Incantesimi | ✅ Corretto | 5 spell aggiunte manualmente |
| Multiclass info | ⚠️ Solo testo | Nelle note e nella bio, non strutturale |

---

<a id="workaround"></a>
## Workaround adottato (e suoi limiti)

Poiché sia `import_from_dndbeyond` che `create_character` non funzionano per multiclass, ho dovuto:

1. **Fetch manuale** dell'API D&D Beyond via `curl` al character-service endpoint
2. **Parsing manuale** del JSON con script Python inline
3. **Creazione** con `create_character` come Rogue 5 (classe primaria)
4. **Update manuale** con `update_character` per:
   - HP: 63 (override)
   - AC: 17 (override)
   - Speed: 25ft (halfling)
   - Features Artificer aggiunte come stringhe
   - Notes con info multiclass
5. **Inventario** aggiunto oggetto per oggetto con `add_item_to_character` (10 call)
6. **Incantesimi** aggiunti uno per uno con `add_spell` (5 call)

**Totale tool call necessarie:** ~20 call manuali per un'operazione che dovrebbe essere 1 (`import_from_dndbeyond`).

### Limiti del workaround

- Il personaggio è strutturalmente un Rogue 5, non un Rogue 5/Artificer 4
- Il `level_up_character` tool non sa che esiste una seconda classe
- Il proficiency bonus non si può correggere (è derivato dal livello della classe)
- Gli spell slot Artificer non esistono nel sistema
- Se il DM usa `get_character` per fare check di regole, vede informazioni incomplete
- Il combat system calcola iniziativa e check basandosi su dati incompleti

---

<a id="piano-fix"></a>
## Piano di fix proposto (in ordine di priorità)

### Fase 1 — Fix immediati (non-breaking)

| # | Fix | File | Effort |
|---|-----|------|--------|
| 1.1 | Fix `_format_import_summary` per usare `character_class` invece di `classes` | `main.py:4373` | 10 min |
| 1.2 | Fix `_format_import_summary` per usare `hit_points_max/current` | `main.py:4401` | 5 min |
| 1.3 | Fix `map_combat.level` per usare livello totale (`sum(c.level for c in classes)`) | `mapper.py:692` | 10 min |
| 1.4 | Aggiungere note multiclass nel mapper (salva info classi secondarie nelle notes) | `mapper.py:map_identity` | 15 min |

**Risultato:** l'import da D&D Beyond funziona, ma multiclass è solo informativo nelle notes.

### Fase 2 — Supporto multiclass nel modello (breaking change)

| # | Fix | File | Effort |
|---|-----|------|--------|
| 2.1 | Refactor `Character.character_class` → `Character.classes: list[CharacterClass]` | `models.py` | 30 min |
| 2.2 | Aggiungere properties: `total_level`, `primary_class`, `proficiency_bonus` (computed) | `models.py` | 20 min |
| 2.3 | Migrazione dati: script per convertire campagne esistenti | nuovo file | 30 min |
| 2.4 | Aggiornare `CharacterBuilder.build()` per multiclass | `character_builder.py` | 1 ora |
| 2.5 | Aggiornare `create_character` tool con param `additional_classes` | `main.py` | 30 min |
| 2.6 | Nuovo tool `add_class_to_character` | `main.py` | 30 min |
| 2.7 | Aggiornare `level_up_character` per specificare quale classe sale | `main.py` | 30 min |
| 2.8 | Aggiornare `get_character` display per mostrare tutte le classi | `main.py` | 15 min |
| 2.9 | Aggiornare DDB mapper per mappare TUTTE le classi | `mapper.py` | 30 min |
| 2.10 | Spell slot multiclass: tabella combinata PHB p.165 | `character_builder.py` o nuovo module | 1 ora |
| 2.11 | Fix tutti i riferimenti a `character_class` nel codebase | grep & replace | 1 ora |

### Fase 3 — Validazione regole multiclass

| # | Fix | File | Effort |
|---|-----|------|--------|
| 3.1 | Prerequisiti multiclass (13+ nelle abilità richieste) | `validators.py` | 30 min |
| 3.2 | Proficiencies multiclass (tabella ridotta PHB) | `character_builder.py` | 30 min |
| 3.3 | Extra Attack non cumula tra classi | `validators.py` | 15 min |
| 3.4 | Hit dice pool composito per rest | combat/rest tools | 20 min |

---

## File coinvolti

```
dm20_protocol/
├── main.py                           # Tools MCP: create_character, import_from_dndbeyond,
│                                     #   _format_import_summary (BUG 1), get_character, level_up
├── models.py                         # Character model (BUG 2: character_class singolare)
├── character_builder.py              # CharacterBuilder.build() (BUG 3: una sola classe)
├── importers/
│   └── dndbeyond/
│       ├── fetcher.py                # Fetch API + read file (funziona)
│       ├── mapper.py                 # map_ddb_to_character (BUG 4: scarta classi secondarie)
│       └── schema.py                 # Costanti e lookup tables (ok)
├── rulebooks/
│   └── validators.py                 # CharacterValidator (manca validazione multiclass)
├── sheets/
│   ├── renderer.py                   # Sheet display (riferimento a character_class)
│   └── parser.py                     # Sheet parsing (riferimento a character_class)
└── claudmaster/
    └── agents/archivist.py           # CharacterStats (riferimento a character_class)
```

## Come riprodurre

```bash
# 1. BUG 1: Import crash
import_from_dndbeyond("https://www.dndbeyond.com/characters/89112463")
# → ❌ Import failed: 'Character' object has no attribute 'classes'

# 2. BUG 2-3: Multiclass impossibile
create_character(name="Test", character_class="Rogue", class_level=5, race="Halfling")
# → Crea un Rogue 5. Non c'è modo di aggiungere Artificer 4.

# 3. BUG 4: Anche con fix di BUG 1, il mapper ignora le classi secondarie
# Perché map_identity() prende solo max(classes, key=level)
```

## Dati API D&D Beyond per test

Endpoint: `https://character-service.dndbeyond.com/character/v5/character/89112463`

Struttura chiave per multiclass:
```json
{
  "data": {
    "name": "Tassly",
    "classes": [
      {
        "definition": {"name": "Rogue"},
        "level": 5,
        "subclassDefinition": {"name": "Assassin"},
        "classFeatures": [...]
      },
      {
        "definition": {"name": "Artificer"},
        "level": 4,
        "subclassDefinition": {"name": "Battle Smith"},
        "classFeatures": [...]
      }
    ],
    "stats": [
      {"id": 1, "value": 10},
      {"id": 2, "value": 15},
      ...
    ],
    "baseHitPoints": 63,
    ...
  }
}
```
