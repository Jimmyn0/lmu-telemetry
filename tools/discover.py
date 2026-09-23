"""
Script de decouverte : ouvre un fichier .duckdb de telemetrie LMU et affiche
sa structure REELLE. Rien n'est suppose : tout vient du fichier.

Un fichier LMU contient trois formes de tables :

  1. metadata / channelsList / eventsList : les tables descriptives.
  2. Les CANAUX (listes dans channelsList). Ils n'ont AUCUNE colonne de temps :
     juste 'value' (ou value1..value4 pour les donnees par roue), une ligne par
     echantillon, a la frequence fixe declaree dans channelsList.
  3. Les EVENEMENTS (listes dans eventsList). Eux ont une colonne 'ts' en
     secondes, et sont enregistres uniquement quand la valeur change.

Le temps d'un canal se reconstruit donc par : t = t0 + indice / frequence,
ou t0 est le 'ts' du tout premier evenement du fichier.

Usage :  python tools/discover.py "chemin/vers/session.duckdb"
"""

import sys
from pathlib import Path

import duckdb

DESCRIPTIVE = ("metadata", "channelsList", "eventsList")


def q(name: str) -> str:
    """Echappe un nom de table qui contient des espaces."""
    return '"' + name.replace('"', '""') + '"'


def main(path: Path) -> None:
    print(f"Fichier : {path.name}")
    print(f"Taille  : {path.stat().st_size / 1024 / 1024:.1f} Mo")
    print()

    # read_only : on ne modifie jamais le fichier du jeu.
    con = duckdb.connect(str(path), read_only=True)

    # --- metadata -------------------------------------------------------
    print("=" * 78)
    print("METADATA")
    print("=" * 78)
    meta = dict(con.execute("SELECT * FROM metadata").fetchall())
    for k, v in meta.items():
        if len(v) > 90:
            print(f"  {k:<20} = <{len(v)} caracteres>")
        else:
            print(f"  {k:<20} = {v}")
    print()

    # --- t0 : premier evenement du fichier ------------------------------
    events = [r[0] for r in con.execute("SELECT eventName FROM eventsList").fetchall()]
    starts = []
    for ev in events:
        try:
            v = con.execute(f"SELECT min(ts) FROM {q(ev)}").fetchone()[0]
            if v is not None:
                starts.append(v)
        except duckdb.Error:
            pass
    t0 = min(starts) if starts else 0.0
    print(f"t0 (premier evenement du fichier) = {t0:.3f} s")
    print()

    # --- canaux ---------------------------------------------------------
    print("=" * 78)
    print("CANAUX (echantillonnage regulier, sans horodatage)")
    print("=" * 78)
    print(f"  {'nom':<26}{'Hz':>5}{'unite':>8}{'lignes':>9}{'duree':>9}  {'min':>11}{'max':>12}")
    print("  " + "-" * 82)
    for name, freq, unit in con.execute(
        "SELECT channelName, frequency, unit FROM channelsList ORDER BY channelName"
    ).fetchall():
        try:
            cols = [c[0] for c in con.execute(f"DESCRIBE {q(name)}").fetchall()]
            n = con.execute(f"SELECT count(*) FROM {q(name)}").fetchone()[0]
            # value1..value4 = une valeur par roue ; on agrege sur l'ensemble.
            mn = min(con.execute(f"SELECT min({c}) FROM {q(name)}").fetchone()[0] for c in cols)
            mx = max(con.execute(f"SELECT max({c}) FROM {q(name)}").fetchone()[0] for c in cols)
            wheels = " x4" if len(cols) == 4 else ""
            print(f"  {name + wheels:<26}{freq:>5}{unit:>8}{n:>9}{n / freq:>8.1f}s"
                  f"  {mn:>11.3f}{mx:>12.3f}")
        except (duckdb.Error, TypeError) as exc:
            print(f"  {name:<26}  [!] {exc}")
    print()

    # --- evenements -----------------------------------------------------
    print("=" * 78)
    print("EVENEMENTS (horodates, enregistres au changement)")
    print("=" * 78)
    print(f"  {'nom':<26}{'unite':>8}{'lignes':>9}  premieres valeurs")
    print("  " + "-" * 82)
    for name, unit in con.execute(
        "SELECT eventName, unit FROM eventsList ORDER BY eventName"
    ).fetchall():
        try:
            cols = [c[0] for c in con.execute(f"DESCRIBE {q(name)}").fetchall()]
            rows = con.execute(f"SELECT * FROM {q(name)} ORDER BY ts LIMIT 4").fetchall()
            n = con.execute(f"SELECT count(*) FROM {q(name)}").fetchone()[0]
            sample = "  ".join(
                f"[{r[0] - t0:+7.2f}s] {', '.join(str(v) for v in r[1:])}" for r in rows
            )
            print(f"  {name:<26}{unit:>8}{n:>9}  {sample}")
        except duckdb.Error as exc:
            print(f"  {name:<26}  [!] {exc}")
    print()

    # --- coherence ------------------------------------------------------
    print("=" * 78)
    print("CONTROLE DE COHERENCE : recalage canaux <-> evenements")
    print("=" * 78)
    laps = con.execute('SELECT ts, value FROM "Lap" ORDER BY ts').fetchall()
    dist = [r[0] for r in con.execute('SELECT value FROM "Lap Dist"').fetchall()]
    freq = con.execute(
        "SELECT frequency FROM channelsList WHERE channelName = 'Lap Dist'"
    ).fetchone()[0]
    print(f"  Lap Dist : {len(dist)} echantillons a {freq} Hz, longueur max {max(dist):.0f} m")
    print("  A chaque debut de tour, Lap Dist doit retomber a ~0 :")
    for ts, lap in laps:
        i = round((ts - t0) * freq)
        if 0 <= i < len(dist):
            print(f"    tour {lap:>3}  t={ts - t0:8.2f}s  indice {i:>6}  "
                  f"Lap Dist = {dist[i]:8.1f} m   (echantillon precedent {dist[i - 1]:8.1f} m)")
    con.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    target = Path(sys.argv[1])
    if not target.exists():
        print(f"Fichier introuvable : {target}")
        sys.exit(1)
    main(target)
