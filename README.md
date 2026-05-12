# Raspberry Pi 433 MHz RF Switch

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

> 🇩🇪 [Deutsche Version](#deutsche-version) | 🇬🇧 English version below

Home Assistant custom integration for 433 MHz radio outlets via a GPIO transmitter on Raspberry Pi — **fully configurable through the UI**, no YAML needed.

## Features

- ✅ **UI-based setup** — Add devices via *Settings → Devices & Services → Add Integration*
- ✅ **DIP switch mode** — Enter system code (5 switches) + unit code (A–E), codes are calculated automatically (PT2262)
- ✅ **Direct code mode** — Enter decimal RF codes manually (e.g. sniffed via `rpi-rf_receive`)
- ✅ **Learn mode** — Press buttons on your remote, codes are detected automatically (requires receiver module)
- ✅ **Passive state sync** — Receiver monitors RF traffic and updates switch state when someone uses the physical remote
- ✅ **TX guard** — Prevents self-reception when transmitting (0.5s ignore window)
- ✅ **Editable after setup** — Change settings via "Configure" in the UI
- ✅ **State restore** — Remembers last switch state across HA restarts
- ✅ **German & English** — UI fully localized
- ✅ **Shared GPIO** — Multiple outlets share one transmitter (thread-safe)

## Requirements

- Raspberry Pi (3B, 3B+, 4, Zero W — **not** Pi 5)
- Home Assistant OS on the Pi
- 433 MHz transmitter module (3-pin: VCC, DATA, GND + antenna)
- 433 MHz receiver module (optional, for learn mode + state sync)

## Wiring

### Transmitter (required)

```
Transmitter module (left to right, antenna on the right):
  GND    DATA    VCC    [ANT]

Raspberry Pi              433 MHz Transmitter
─────────────             ────────────────────
Pin 2  (5V)      ───→    VCC  (right)
Pin 9  (GND)     ───→    GND  (left)
Pin 11 (GPIO17)  ───→    DATA (middle)
                          + 17cm wire on ANT
```

> GPIO 17 is the default TX pin. You can select any other GPIO pin in the UI.

### Receiver (optional)

```
Receiver module (many pins — only use these 3):
  VCC    DATA    DATA    GND
  (the middle DATA pins are identical — use either one)

Raspberry Pi              433 MHz Receiver
─────────────             ──────────────────
Pin 4  (5V)      ───→    VCC
Pin 6  (GND)     ───→    GND
Pin 13 (GPIO27)  ───→    DATA (either one)
                          + 17cm wire on ANT
```

> GPIO 27 is the default RX pin. TX and RX must use **different** GPIO pins.

## Installation

### Via HACS (recommended)

1. HACS → Integrations → ⋮ (top right) → **Custom repositories**
2. URL: `https://github.com/MaxXLive/rpi-rf-ha-integration`
3. Category: **Integration**
4. → Add → Install → **Restart Home Assistant**

### Manual

1. Copy the `custom_components/rpi_rf_switch/` folder to your HA `config/custom_components/`
2. Restart Home Assistant

## Setup

1. **Settings** → **Devices & Services** → **Add Integration**
2. Search for **"Raspberry Pi 433 MHz RF Switch"**
3. Enter a name, select the TX GPIO pin, optionally set an RX GPIO pin, and choose a mode:

### DIP Switch Mode

For typical radio outlets (Brennenstuhl, Mumbi, Etekcity, …) with DIP switches:

- **System Code**: The 5 DIP switches as `0` and `1` (e.g. `10101`)
  - `1` = switch up / ON
  - `0` = switch down / OFF
- **Unit Code**: The letter of the outlet (`A`, `B`, `C`, `D` or `E`)

RF codes are calculated automatically (PT2262 protocol).

### Direct Code Mode

If you know the decimal codes (e.g. sniffed via `rpi-rf_receive`):

- **Code ON**: Decimal code to turn on
- **Code OFF**: Decimal code to turn off
- **Protocol**: 1–6 (default: 1)
- **Pulse length**: Optional, in microseconds
- **Code length**: Default 24 bits

### Learn Mode (requires receiver)

If you have a 433 MHz receiver module connected:

1. Select **"Anlernen"** as mode and set the RX GPIO pin
2. Press the **ON** button on your remote repeatedly, then click Submit
3. Press the **OFF** button on your remote repeatedly, then click Submit
4. The codes, protocol, and pulse length are detected automatically
5. If PT2262 encoding is detected, the system/unit codes are also extracted

### Passive State Sync (requires receiver)

When an RX GPIO pin is configured, the integration runs a background listener that monitors RF traffic. When someone uses a physical remote, the matching switch state in HA is updated automatically. This works for all modes (DIP, direct, learn).

## Adding More Outlets

Simply add the integration again — each outlet is created as a separate device.

## Supported Protocols

| No. | Pulse length | Description |
|-----|-------------|-------------|
| 1   | 350 µs      | PT2262 (default, most outlets) |
| 2   | 650 µs      |             |
| 3   | 100 µs      |             |
| 4   | 380 µs      |             |
| 5   | 500 µs      |             |
| 6   | 200 µs      | HT6P20B / NEXA |

## Technical Details

- Based on the Python library [`rpi-rf`](https://github.com/milaq/rpi-rf)
- Thread-safe: multiple outlets on the same GPIO don't block each other
- State restore: remembers last sent state across restarts
- Passive state sync via background RX listener (optional)
- TX guard: 0.5s after transmitting, received codes are ignored to prevent self-reception
- PT2262 reverse decoding: learned codes are automatically analyzed for system/unit structure
- GPIO access via `RPi.GPIO` (works on Pi 3/4/Zero, **not** on Pi 5)

## Roadmap

- [ ] **Raspberry Pi 5 support** — `RPi.GPIO` doesn't support the Pi 5's RP1 chip. Potential fix: use `rpi-lgpio` as drop-in replacement. Needs testing on Pi 5 hardware.

## License

MIT License

---

# Deutsche Version

Home Assistant Custom Integration für 433 MHz Funksteckdosen über einen GPIO-Sender am Raspberry Pi — **komplett über die UI konfigurierbar**, kein YAML nötig.

## Features

- ✅ **UI-basiertes Setup** — Geräte über *Einstellungen → Geräte & Dienste → Integration hinzufügen* konfigurieren
- ✅ **DIP-Schalter Modus** — System-Code (5 Schalter) + Unit-Code (A–E) eingeben, Codes werden automatisch berechnet (PT2262)
- ✅ **Direkter Code Modus** — Dezimale RF-Codes manuell eingeben (z.B. per `rpi-rf_receive` gesnifft)
- ✅ **Anlernmodus** — Fernbedienung drücken, Codes werden automatisch erkannt (benötigt Empfänger-Modul)
- ✅ **Passiver State Sync** — Empfänger überwacht den Funkverkehr und aktualisiert den Schaltzustand wenn jemand die Fernbedienung benutzt
- ✅ **TX Guard** — Verhindert Selbstempfang beim Senden (0,5s Ignorier-Fenster)
- ✅ **Nachträglich bearbeitbar** — Einstellungen über "Konfigurieren" in der UI ändern
- ✅ **State Restore** — Merkt sich den letzten Schaltzustand über HA-Neustarts
- ✅ **Deutsch & Englisch** — UI komplett lokalisiert
- ✅ **Shared GPIO** — Mehrere Steckdosen teilen sich einen Sender (thread-safe)

## Voraussetzungen

- Raspberry Pi (3B, 3B+, 4, Zero W — **nicht** Pi 5)
- Home Assistant OS auf dem Pi
- 433 MHz Sender-Modul (3-Pin: VCC, DATA, GND + Antenne)
- 433 MHz Empfänger-Modul (optional, für Anlernmodus + State Sync)

## Verkabelung

### Sender (erforderlich)

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

> GPIO 17 ist der Standard TX-Pin. Du kannst jeden anderen GPIO-Pin in der UI auswählen.

### Empfänger (optional)

```
Empfänger-Modul (viele Pins — nur diese 3 benutzen):
  VCC    DATA    DATA    GND
  (die mittleren DATA-Pins sind identisch — einen davon benutzen)

Raspberry Pi              433 MHz Empfänger
─────────────             ──────────────────
Pin 4  (5V)      ───→    VCC
Pin 6  (GND)     ───→    GND
Pin 13 (GPIO27)  ───→    DATA (einer davon)
                          + 17cm Draht an ANT
```

> GPIO 27 ist der Standard RX-Pin. TX und RX müssen **verschiedene** GPIO-Pins verwenden.

## Installation

### Via HACS (empfohlen)

1. HACS → Integrationen → ⋮ (oben rechts) → **Benutzerdefinierte Repositories**
2. URL: `https://github.com/MaxXLive/rpi-rf-ha-integration`
3. Kategorie: **Integration**
4. → Hinzufügen → Installieren → **Home Assistant neu starten**

### Manuell

1. Kopiere den Ordner `custom_components/rpi_rf_switch/` in dein HA `config/custom_components/`
2. Starte Home Assistant neu

## Einrichtung

1. **Einstellungen** → **Geräte & Dienste** → **Integration hinzufügen**
2. Suche nach **"Raspberry Pi 433 MHz RF Switch"**
3. Gib einen Namen ein, wähle den TX GPIO-Pin, optional einen RX GPIO-Pin, und den Modus:

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

### Anlernmodus (benötigt Empfänger)

Wenn ein 433 MHz Empfänger-Modul angeschlossen ist:

1. Wähle **"Anlernen"** als Modus und setze den RX GPIO-Pin
2. Drücke wiederholt den **EIN**-Knopf auf der Fernbedienung, dann klicke Absenden
3. Drücke wiederholt den **AUS**-Knopf auf der Fernbedienung, dann klicke Absenden
4. Codes, Protokoll und Pulslänge werden automatisch erkannt
5. Falls PT2262-Kodierung erkannt wird, werden auch System-/Unit-Codes extrahiert

### Passiver State Sync (benötigt Empfänger)

Wenn ein RX GPIO-Pin konfiguriert ist, läuft ein Hintergrund-Listener der den Funkverkehr überwacht. Wenn jemand die physische Fernbedienung benutzt, wird der passende Schaltzustand in HA automatisch aktualisiert. Dies funktioniert mit allen Modi (DIP, direkt, angelernt).

## Weitere Steckdosen hinzufügen

Einfach die Integration nochmal hinzufügen — jede Steckdose wird als eigenes Gerät angelegt.

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
- State Restore: Merkt sich den letzten Zustand über Neustarts
- Passiver State Sync über Hintergrund-RX-Listener (optional)
- TX Guard: 0,5s nach dem Senden werden empfangene Codes ignoriert um Selbstempfang zu verhindern
- PT2262 Rückwärts-Dekodierung: Angelernte Codes werden automatisch auf System-/Unit-Struktur analysiert
- GPIO-Zugriff über `RPi.GPIO` (funktioniert auf Pi 3/4/Zero, **nicht** auf Pi 5)

## Roadmap

- [ ] **Raspberry Pi 5 Unterstützung** — `RPi.GPIO` unterstützt den RP1-Chip des Pi 5 nicht. Möglicher Fix: `rpi-lgpio` als Drop-in Ersatz. Muss auf Pi 5 Hardware getestet werden.

## Lizenz

MIT License
