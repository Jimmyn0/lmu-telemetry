"""
Balaye tous les fichiers .duckdb de telemetrie LMU et dresse l'inventaire.

Objectif : verifier qu'on sait ouvrir TOUS les fichiers, et produire la liste
de sessions qui servira d'ecran d'accueil.

Les fichiers sont ouverts en lecture seule, sur place, jamais modifies.

Usage :  python tools/inventory.py [dossier]
"""

import sys
import time
from collections import Counter
from pathlib import Path

import duckdb

DEFAULT_DIR = Path(
    r"D:\SteamLibrary\steamapps\common\Le Mans Ultimate\UserData\Telemetry"
)


def scan_one(path: Path) -> dict:
    con = duckdb.connect(str(path), read_only=True)
    try:
        meta = dict(con.execute("SELECT * FROM metadata").fetchall())
        laps = con.execute('SELECT ts, value FROM "Lap" ORDER BY ts').fetchall()
        times = con.execute('SELECT ts, value FROM "Lap Time" ORDER BY ts').fetchall()
        # Un chrono a 0 = tour non chronometre (sortie des stands, tour tronque).
        real = [v for _, v in times if v and v > 0]
        n = con.execute('SELECT count(*) FROM "Ground Speed"').fetchone()[0]
        return {
            "schema": meta.get("Version"),
            "track": meta.get("TrackName", "?"),
            "type": meta.get("SessionType", "?"),
            "car": meta.get("CarName", "?"),
            "cls": meta.get("CarClass", "?"),
            "when": meta.get("RecordingTime", "?"),
            "weather": meta.get("WeatherConditions", "?"),
            "laps": len(laps),
            "timed": len(real),
            "best": min(real) if real else None,
            "minutes": n / 100 / 60,
        }
    finally:
        con.close()


def fmt_time(s: float | None) -> str:
    if s is None:
        return "     -"
    return f"{int(s // 60)}:{s % 60:06.3f}"


def main(folder: Path) -> None:
    files = sorted(folder.glob("*.duckdb"))
    print(f"Dossier : {folder}")
    print(f"{len(files)} fichiers .duckdb\n")

    ok, failed, rows = 0, [], []
    t_start = time.time()
    for f in files:
        try:
            rows.append((f, scan_one(f)))
            ok += 1
        except Exception as exc:  # on veut savoir QUELS fichiers resistent
            failed.append((f.name, f"{type(exc).__name__}: {exc}"))

    print(f"Lus sans erreur : {ok} / {len(files)}   ({time.time() - t_start:.1f} s)")
    if failed:
        print(f"En echec : {len(failed)}")
        for name, err in failed:
            print(f"   {name}\n      {err[:150]}")
    print()

    schemas = Counter(r["schema"] for _, r in rows)
    print(f"Versions de schema rencontrees : {dict(schemas)}")
    print(f"Duree totale enregistree : {sum(r['minutes'] for _, r in rows) / 60:.1f} heures")
    print()

    print("Par circuit :")
    print(f"  {'circuit':<34}{'sessions':>9}{'tours chrono':>14}{'meilleur':>12}")
    print("  " + "-" * 68)
    tracks = {}
    for _, r in rows:
        t = tracks.setdefault(r["track"], {"n": 0, "timed": 0, "best": None})
        t["n"] += 1
        t["timed"] += r["timed"]
        if r["best"] and (t["best"] is None or r["best"] < t["best"]):
            t["best"] = r["best"]
    for name, t in sorted(tracks.items(), key=lambda kv: -kv[1]["n"]):
        print(f"  {name:<34}{t['n']:>9}{t['timed']:>14}{fmt_time(t['best']):>12}")
    print()

    print("10 sessions les plus recentes :")
    print(f"  {'date':<22}{'circuit':<30}{'type':<10}{'tours':>6}{'chrono':>6}{'meilleur':>11}  voiture")
    print("  " + "-" * 116)
    for f, r in sorted(rows, key=lambda x: x[1]["when"], reverse=True)[:10]:
        print(f"  {r['when']:<22}{r['track'][:28]:<30}{r['type']:<10}"
              f"{r['laps']:>6}{r['timed']:>6}{fmt_time(r['best']):>11}  {r['car'][:34]}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR)
