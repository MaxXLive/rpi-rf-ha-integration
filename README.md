# Raspberry Pi 433 MHz RF Switch

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

> 🇩🇪 [Deutsche Version](#deutsche-version) | 🇬🇧 English version below

Home Assistant custom integration for 433 MHz radio outlets via a GPIO transmitter on Raspberry Pi — **fully configurable through the UI**, no YAML needed.

## Features

- ✅ **Modular architecture** — TX module, RX module, and devices are separate config entries
- ✅ **UI-based setup** — Add devices via *Settings → Devices & Services → Add Integration*
- ✅ **Device types** — Outlet, Light, or Switch (proper HA entity categories)
- ✅ **DIP switch mode** — Enter system code (5 switches) + unit code (A–E), codes are calculated automatically (PT2262)
- ✅ **Direct code mode** — Enter decimal RF codes manually (e.g. sniffed via `rpi-rf_receive`)
- ✅ **Learn mode** — Press buttons on your remote, codes are detected automatically (requires RX module)
- ✅ **Passive state sync** — RX module monitors RF traffic and updates state when someone uses the physical remote
- ✅ **TX guard** — Prevents self-reception when transmitting (0.5s ignore window)
- ✅ **Editable after setup** — Change settings via "Configure" in the UI
- ✅ **State restore** — Remembers last switch state across HA restarts
- ✅ **German & English** — UI fully localized
- ✅ **Shared GPIO** — Multiple devices share one TX module (thread-safe)

## Requirements

- Raspberry Pi (3B, 3B+, 4, 5, Zero W)
- Home Assistant OS on the Pi (Bookworm / kernel 6.x+)
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

### Step 1: Add Transmitter Module (TX)

1. **Settings** → **Devices & Services** → **Add Integration**
2. Search for **"Raspberry Pi 433 MHz RF Switch"**
3. The first time, you'll be asked to set up the **TX module** — select the GPIO pin connected to your transmitter

### Step 2: Add Receiver Module (RX) — optional

After adding the TX module, add the integration again:

1. You'll see a choice menu — select **"Receiver Module (RX)"**
2. Select the GPIO pin for your receiver (must be different from TX)

### Step 3: Add Devices

Add the integration again to add devices:

1. Select **"RF Device"** from the choice menu
2. Enter a name, choose the device type (Outlet / Light / Switch) and mode:

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

### Learn Mode (requires RX module)

If you have added a receiver module:

1. Select **"Anlernen"** as mode when adding a device
2. Press the **ON** button on your remote repeatedly, then click Submit
3. Press the **OFF** button on your remote repeatedly, then click Submit
4. The codes, protocol, and pulse length are detected automatically
5. If PT2262 encoding is detected, the system/unit codes are also extracted

### Passive State Sync (requires RX module)

When an RX module is configured, the integration runs a background listener that monitors RF traffic. When someone uses a physical remote, the matching device state in HA is updated automatically. This works for all modes (DIP, direct, learn).

## Adding More Devices

Simply add the integration again and select "RF Device" — each device is created as a separate config entry with its own HA entity.

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

- Uses [`rpi-rf-gpiod2`](https://pypi.org/project/rpi-rf-gpiod2/) — a modern GPIO library using `gpiod` v2 (kernel character device)
- **Works on all Pi models** including Pi 5 (auto-detects `/dev/gpiochip0` vs `/dev/gpiochip4`)
- **Works on kernel 6.12+** where `RPi.GPIO` and `lgpio` edge detection are broken
- **Modular architecture**: TX module, RX module, and devices are separate config entries
- TX module: one per integration, manages GPIO transmitter (thread-safe via RLock)
- RX module: optional, uses kernel edge-detection with nanosecond timestamps (no CPU-intensive polling)
- Devices look up the TX module dynamically at send time (no stale references)
- State restore: remembers last sent state across restarts
- Passive state sync via background RX listener (optional)
- TX guard: 0.5s after transmitting, received codes are ignored to prevent self-reception
- PT2262 reverse decoding: learned codes are automatically analyzed for system/unit structure

## Alexa Integration

If you use the DIY Alexa Smart Home integration (Lambda-based, without Nabu Casa), Alexa may show the **old** state after switching. To fix this, enable **Proactive Events**:

1. [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask) → Your Skill → Build → Permissions → **"Send Alexa Events"** ✅
2. Copy the **Client ID** and **Client Secret** from the permissions page
3. Add to `configuration.yaml`:
   ```yaml
   alexa:
     smart_home:
       locale: de-DE  # or en-US
       endpoint: https://api.eu.amazonalexa.com/v3/events  # eu for Europe
       client_id: "YOUR_CLIENT_ID"
       client_secret: "YOUR_CLIENT_SECRET"
   ```
4. Restart Home Assistant
5. In the Alexa app: **deactivate** the skill, **re-enable** it, and rediscover devices

> This is not specific to this integration — it affects all HA entities with DIY Alexa setups.

## Roadmap

- [x] ~~**Raspberry Pi 5 support**~~ — Solved! v3.0.0 uses `gpiod` which works on all Pi models including Pi 5.

## License

MIT License

---

# Deutsche Version

Home Assistant Custom Integration für 433 MHz Funksteckdosen über einen GPIO-Sender am Raspberry Pi — **komplett über die UI konfigurierbar**, kein YAML nötig.

## Features

- ✅ **Modulare Architektur** — TX-Modul, RX-Modul und Geräte sind getrennte Konfigurationseinträge
- ✅ **UI-basiertes Setup** — Geräte über *Einstellungen → Geräte & Dienste → Integration hinzufügen* konfigurieren
- ✅ **Gerätetypen** — Steckdose, Licht oder Schalter (richtige HA Entity-Kategorien)
- ✅ **DIP-Schalter Modus** — System-Code (5 Schalter) + Unit-Code (A–E) eingeben, Codes werden automatisch berechnet (PT2262)
- ✅ **Direkter Code Modus** — Dezimale RF-Codes manuell eingeben (z.B. per `rpi-rf_receive` gesnifft)
- ✅ **Anlernmodus** — Fernbedienung drücken, Codes werden automatisch erkannt (benötigt RX-Modul)
- ✅ **Passiver State Sync** — RX-Modul überwacht den Funkverkehr und aktualisiert den Zustand wenn jemand die Fernbedienung benutzt
- ✅ **TX Guard** — Verhindert Selbstempfang beim Senden (0,5s Ignorier-Fenster)
- ✅ **Nachträglich bearbeitbar** — Einstellungen über "Konfigurieren" in der UI ändern
- ✅ **State Restore** — Merkt sich den letzten Schaltzustand über HA-Neustarts
- ✅ **Deutsch & Englisch** — UI komplett lokalisiert
- ✅ **Shared GPIO** — Mehrere Geräte teilen sich ein TX-Modul (thread-safe)

## Voraussetzungen

- Raspberry Pi (3B, 3B+, 4, 5, Zero W)
- Home Assistant OS auf dem Pi (Bookworm / Kernel 6.x+)
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

### Schritt 1: Sender-Modul (TX) hinzufügen

1. **Einstellungen** → **Geräte & Dienste** → **Integration hinzufügen**
2. Suche nach **"Raspberry Pi 433 MHz RF Switch"**
3. Beim ersten Mal wird das **TX-Modul** eingerichtet — wähle den GPIO-Pin deines Senders

### Schritt 2: Empfänger-Modul (RX) hinzufügen — optional

Nach dem TX-Modul, füge die Integration nochmal hinzu:

1. Du siehst ein Auswahlmenü — wähle **"Empfänger-Modul (RX)"**
2. Wähle den GPIO-Pin für deinen Empfänger (muss anders sein als TX)

### Schritt 3: Geräte hinzufügen

Füge die Integration nochmal hinzu um Geräte anzulegen:

1. Wähle **"Funkgerät"** im Auswahlmenü
2. Gib einen Namen ein, wähle den Gerätetyp (Steckdose / Licht / Schalter) und den Modus:

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

### Anlernmodus (benötigt RX-Modul)

Wenn ein Empfänger-Modul hinzugefügt wurde:

1. Wähle **"Anlernen"** als Modus beim Gerät hinzufügen
2. Drücke wiederholt den **EIN**-Knopf auf der Fernbedienung, dann klicke Absenden
3. Drücke wiederholt den **AUS**-Knopf auf der Fernbedienung, dann klicke Absenden
4. Codes, Protokoll und Pulslänge werden automatisch erkannt
5. Falls PT2262-Kodierung erkannt wird, werden auch System-/Unit-Codes extrahiert

### Passiver State Sync (benötigt RX-Modul)

Wenn ein RX-Modul konfiguriert ist, läuft ein Hintergrund-Listener der den Funkverkehr überwacht. Wenn jemand die physische Fernbedienung benutzt, wird der passende Gerätezustand in HA automatisch aktualisiert. Dies funktioniert mit allen Modi (DIP, direkt, angelernt).

## Weitere Geräte hinzufügen

Einfach die Integration nochmal hinzufügen und "Funkgerät" wählen — jedes Gerät wird als eigener Konfigurationseintrag mit eigenem HA Entity angelegt.

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

- Nutzt [`rpi-rf-gpiod2`](https://pypi.org/project/rpi-rf-gpiod2/) — eine moderne GPIO-Bibliothek basierend auf `gpiod` v2 (Kernel Character Device)
- **Funktioniert auf allen Pi-Modellen** inkl. Pi 5 (erkennt automatisch `/dev/gpiochip0` vs `/dev/gpiochip4`)
- **Funktioniert auf Kernel 6.12+** wo `RPi.GPIO` und `lgpio` Edge-Detection kaputt sind
- **Modulare Architektur**: TX-Modul, RX-Modul und Geräte sind getrennte Konfigurationseinträge
- TX-Modul: einmal pro Integration, verwaltet GPIO-Sender (thread-safe via RLock)
- RX-Modul: optional, nutzt Kernel Edge-Detection mit Nanosekunden-Timestamps (kein CPU-intensives Polling)
- Geräte suchen das TX-Modul dynamisch beim Senden (keine veralteten Referenzen)
- State Restore: Merkt sich den letzten Zustand über Neustarts
- Passiver State Sync über Hintergrund-RX-Listener (optional)
- TX Guard: 0,5s nach dem Senden werden empfangene Codes ignoriert um Selbstempfang zu verhindern
- PT2262 Rückwärts-Dekodierung: Angelernte Codes werden automatisch auf System-/Unit-Struktur analysiert

## Alexa Integration

Wenn du die DIY Alexa Smart Home Integration (Lambda-basiert, ohne Nabu Casa) nutzt, zeigt Alexa nach dem Schalten möglicherweise den **alten** Zustand an. Um das zu beheben, aktiviere **Proactive Events**:

1. [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask) → Dein Skill → Build → Permissions → **"Send Alexa Events"** ✅
2. **Client ID** und **Client Secret** von der Permissions-Seite kopieren
3. In `configuration.yaml` ergänzen:
   ```yaml
   alexa:
     smart_home:
       locale: de-DE
       endpoint: https://api.eu.amazonalexa.com/v3/events  # eu für Europa
       client_id: "DEINE_CLIENT_ID"
       client_secret: "DEIN_CLIENT_SECRET"
   ```
4. Home Assistant neu starten
5. In der Alexa App: Skill **deaktivieren**, neu **verknüpfen** und Geräte neu entdecken

> Das ist kein Problem dieser Integration — es betrifft alle HA Entities mit DIY Alexa Setups.

## Roadmap

- [x] ~~**Raspberry Pi 5 Unterstützung**~~ — Gelöst! v3.0.0 nutzt `gpiod`, das auf allen Pi-Modellen inkl. Pi 5 funktioniert.

## Lizenz

MIT License
