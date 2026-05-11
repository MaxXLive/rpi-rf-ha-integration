# Raspberry Pi 433 MHz RF Switch

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant Custom Integration für 433 MHz Funksteckdosen über einen GPIO-Sender am Raspberry Pi — **komplett über die UI konfigurierbar**, kein YAML nötig.

## Features

- ✅ **UI-basiertes Setup** — Geräte über *Einstellungen → Geräte & Dienste → Integration hinzufügen* konfigurieren
- ✅ **DIP-Schalter Modus** — System-Code (5 Schalter) + Unit-Code (A–E) eingeben, Codes werden automatisch berechnet (PT2262)
- ✅ **Direkter Code Modus** — Dezimale RF-Codes manuell eingeben (z.B. per `rpi-rf_receive` gesnifft)
- ✅ **Nachträglich bearbeitbar** — Einstellungen über "Konfigurieren" in der UI ändern
- ✅ **Deutsch & Englisch** — UI komplett lokalisiert
- ✅ **Shared GPIO** — Mehrere Steckdosen teilen sich einen Sender (thread-safe)

## Voraussetzungen

- Raspberry Pi (3B, 3B+, 4, Zero W — **nicht** Pi 5)
- Home Assistant OS auf dem Pi
- 433 MHz Sender-Modul (3-Pin: VCC, DATA, GND + Antenne)

## Verkabelung

```
Sender-Modul (von links, Antenne rechts):
  GND    DATA    VCC    [ANT]

Raspberry Pi              433 MHz Sender
─────────────             ──────────────
Pin 2  (5V)      ───→    VCC  (rechts)
Pin 9  (GND)     ───→    GND  (links)
Pin 11 (GPIO17)  ───→    DATA (mitte)
                          + 17cm Draht an ANT
```

> GPIO 17 ist der Standard. Du kannst jeden anderen GPIO-Pin verwenden und ihn in der UI auswählen.

## Installation

### Via HACS (empfohlen)

1. HACS → Integrationen → ⋮ (oben rechts) → **Benutzerdefinierte Repositories**
2. URL: `https://github.com/DEIN-USER/ha-rpi-rf-switch`
3. Kategorie: **Integration**
4. → Hinzufügen → Installieren → **Home Assistant neu starten**

### Manuell

1. Kopiere den Ordner `custom_components/rpi_rf_switch/` in dein HA `config/custom_components/`
2. Starte Home Assistant neu

## Einrichtung

1. **Einstellungen** → **Geräte & Dienste** → **Integration hinzufügen**
2. Suche nach **"Raspberry Pi 433 MHz RF Switch"**
3. Gib einen Namen ein, wähle den GPIO-Pin und den Modus:

### DIP-Schalter Modus

Für typische Funksteckdosen (Brennenstuhl, Mumbi, Etekcity, …) mit DIP-Schaltern:

- **System-Code**: Die 5 DIP-Schalter als `0` und `1` (z.B. `10101`)
  - `1` = Schalter oben/ON
  - `0` = Schalter unten/OFF
- **Unit-Code**: Der Buchstabe der Steckdose (`A`, `B`, `C`, `D` oder `E`)

Die RF-Codes werden automatisch berechnet (PT2262-Protokoll).

### Direkter Code Modus

Wenn du die dezimalen Codes kennst (z.B. per `rpi-rf_receive` gesnifft):

- **Code ON**: Dezimaler Code zum Einschalten
- **Code OFF**: Dezimaler Code zum Ausschalten
- **Protokoll**: 1–6 (Standard: 1)
- **Pulslänge**: Optional, in Mikrosekunden
- **Code-Länge**: Standard 24 Bit

## Weitere Steckdosen hinzufügen

Einfach die Integration nochmal hinzufügen — jede Steckdose wird als eigenes Gerät angelegt.

## Codes herausfinden (optional)

Wenn du die Codes deiner Fernbedienung sniffern möchtest, brauchst du einen 433 MHz **Empfänger**. SSH auf den Pi:

```bash
pip install rpi-rf
rpi-rf_receive -g 27    # GPIO 27 für Empfänger
```

Drücke die Tasten auf der Fernbedienung — die Codes werden angezeigt.

## Unterstützte Protokolle

| Nr. | Pulslänge | Beschreibung |
|-----|-----------|--------------|
| 1   | 350 µs    | PT2262 (Standard, die meisten Steckdosen) |
| 2   | 650 µs    |              |
| 3   | 100 µs    |              |
| 4   | 380 µs    |              |
| 5   | 500 µs    |              |
| 6   | 200 µs    | HT6P20B / NEXA |

## Technische Details

- Basiert auf der Python-Bibliothek [`rpi-rf`](https://github.com/milaq/rpi-rf)
- Thread-safe: Mehrere Steckdosen am gleichen GPIO blockieren sich nicht
- `assumed_state`: HA nimmt den letzten gesendeten Zustand an (433 MHz ist unidirektional)
- GPIO-Zugriff über `RPi.GPIO` (funktioniert auf Pi 3/4/Zero, **nicht** auf Pi 5)

## Lizenz

MIT License
