# GhostLine for LMU — lap analysis for Le Mans Ultimate

🇫🇷 *Version française : [LISEZ-MOI.md](LISEZ-MOI.md)*

A local tool to see what you do behind the wheel in **Le Mans Ultimate**, built
from the telemetry recordings the game already makes on its own.

The tool **shows**, it does not judge: no setup advice, no automatic
diagnosis — only measured facts.

**[⬇ Download the latest version](https://github.com/Jimmyn0/lmu-telemetry/releases/latest)**
— take the `.zip` file: it contains the `.exe` and its user guide.

---

## What it does

* **Session list** — every session you have driven, with car, track, session
  type and best lap. Filter by track, sort by date or by best lap time. Track
  layout variants (Monza and Monza Curva Grande, for example) are kept apart.
* **Lap times** — your best lap in every car on every track, class by class,
  with its sectors, one click away from its telemetry.
* **Laps of a session** — lap times, sectors, validity. Best lap and best
  sectors in purple, as on a race timing screen. Notes on each lap: pit lane
  visit, off track, contacts, near stop.
* **Lap comparison** — any two laps, even from different sessions:
  cumulative delta, speed, brake, throttle, steering angle in degrees, gear.
  One shared cursor across all charts, zoom, lap playback, a track map coloured
  by time lost or gained, speed, pedals or sector, and a close-up road view with
  both racing lines.
* **Corner by corner** — corners numbered T1, T2… like official track maps.
  For each one: time lost or gained, braking point, entry speed, braking time
  and pressure, minimum speed, back on throttle, exit speed, and time spent
  coasting.
* **Consistency** — lap time spread, the *ideal lap* (your best run through
  every corner, strung together), drift over the session, and the corners where
  you are least consistent.
* **Car model, brand logo and track flag.**
* **French and English** — switch the whole interface in the settings.

## Getting started

1. [Download](https://github.com/Jimmyn0/lmu-telemetry/releases/latest) the
   `.zip`, unzip it, and double-click `GhostLine.exe` in the `GhostLine`
   folder. Nothing to install.
2. The tool opens in its own window. Closing it stops the tool.
3. Pick a session, then two laps, and hit **Compare**. The very first start reads
   all your sessions in the background, which can take a minute or two; after
   that, only new sessions are read.

On the first launch, Windows may show *"Windows protected your PC"*: click
**More info**, then **Run anyway**. Some antivirus programs also flag it by
mistake — a common false alarm with programs packaged this way.

**Nothing to set up in the game**: Le Mans Ultimate records your telemetry on
its own, for every session. The tool finds the game by itself in your Steam
libraries, on any drive. If it cannot, it asks you for the folder and explains
how to find it:

```
...\steamapps\common\Le Mans Ultimate\UserData\Telemetry
```

## Privacy and safety

* **Nothing leaves your computer unless you join a group.** The tool runs a
  small web server that only listens on your own machine (`127.0.0.1`), and the
  page loads nothing from the internet. In a group, only your online qualifying
  and race results, and the telemetry of your best laps, go to the group
  service.
* **The game files are read in place, read-only.** Nothing is copied, moved,
  changed or deleted.
* What the tool writes — your settings, your thresholds, your corner maps, your own logos — goes
  to `%LOCALAPPDATA%\GhostLine`, and survives updates. The tool was called LMU
  Telemetry until 10 November 2026: its old folder takes the new name on first launch.

⚠️ Your telemetry files live inside the Steam folder: a *Verify integrity of
game files* or a major update may erase them. Copy that folder somewhere else
from time to time if you care about your history.

## Updating

New versions are published on the
[Releases](https://github.com/Jimmyn0/lmu-telemetry/releases) page. Replace the
old `GhostLine` folder with the new one: your settings and corner maps are kept. The version
number is shown in the settings (the gear at the top right); see
[NOTES-DE-VERSION.md](NOTES-DE-VERSION.md) for what changed (in French).

## Manufacturer logos

The logos of the 20 brands in the game that have one ship with the tool
(`lmu_telemetry/ressources/logos/`, with each file's origin and licence in
`SOURCES.md`); only ADESS, which has none anywhere, gets a badge with its
initials. These logos are trademarks of their owners, shown only to recognise
the cars: the tool is not affiliated with any manufacturer, nor with the game.
A manufacturer who asks will have its logo removed.

To replace one, or add one for a new brand, drop an image file in
`%LOCALAPPDATA%\GhostLine\logos`, named after the brand as the tool displays
it: `Porsche.png`, `Ferrari.png`, `Aston Martin.png`… Yours take precedence.
Dark logos are automatically lightened so they stay visible on the dark
background.

## Corner maps

Each track is split into corners once, from the curvature of the track, and
saved as an editable JSON file in `%LOCALAPPDATA%\GhostLine\virages`. You
can move the boundaries, remove a corner, or give it a name — what you write is
never overwritten. At Monza, the detection finds exactly the 11 official
corners.

---

## For developers

The code, its comments and the technical documentation are in **French**.

**Run from source** (Python 3.11 or later, Windows):

```bash
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m lmu_telemetry.lanceur
```

`python -m lmu_telemetry web` opens the same page in your browser instead.

**Tests** — they run without the game, on a synthetic session built by
`tests/fixtures/construire.py`:

```bash
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest
```

**Build the `.exe`** — double-click `construire-exe.bat`. It installs
PyInstaller, runs the tests (a failing version is never built), then produces
the `dist/GhostLine` folder and the `.zip` to share.

**Translations** — every piece of text lives in
`lmu_telemetry/web/statique/langues/fr.json` and `en.json`. A test fails if a
sentence is missing in one of the two languages. See
[docs/11-langues.md](docs/11-langues.md).

**Layout**

| Path | Role |
|---|---|
| `lmu_telemetry/sources/reader.py` | the only module that knows the game's `.duckdb` telemetry format |
| `lmu_telemetry/sources/resultats.py` | reads the game's results `.xml` files, for the car model |
| `lmu_telemetry/domaine/session.py` | splits a session into laps: times, validity, notes |
| `lmu_telemetry/domaine/comparaison.py` | aligns two laps on distance and computes the delta |
| `lmu_telemetry/domaine/piste.py`, `virages.py` | track geometry, corner detection and per-corner metrics |
| `lmu_telemetry/domaine/regularite.py` | consistency analysis and ideal lap |
| `lmu_telemetry/domaine/circuits.py` | finds or detects the corner map of a track |
| `lmu_telemetry/parametres.py` | the adjustable thresholds and their settings file |
| `lmu_telemetry/stockage/index.py` | remembers what each session contains, so the list is instant |
| `lmu_telemetry/web/` | local server and web interface, charts drawn by hand on canvas |
| `lmu_telemetry/fenetre.py` | the frameless application window (pywebview) |
| `lmu_telemetry/lanceur.py` | what happens when the `.exe` is double-clicked |
| `docs/` | how everything was found and measured, step by step (in French) |

The `docs/` folder records every decision with the measurements behind it —
starting with [docs/01-decouverte.md](docs/01-decouverte.md), the reverse
engineering of the game's telemetry format.
