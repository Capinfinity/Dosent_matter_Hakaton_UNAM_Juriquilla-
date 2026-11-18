"""Prepara los datos del proyecto en data/.

Uso (desde la raíz del proyecto):
    .venv/bin/python scripts/prepare_data.py            # descarga lo que falte
    .venv/bin/python scripts/prepare_data.py --force    # vuelve a descargar todo

Genera:
  data/games.csv, data/plays.csv, data/pffScoutingData.csv  (copias sin cambios de Big Data Bowl)
  data/nflverse_pbp_filtered.csv                            (play-by-play nflverse 2018-2023, filtrado)

Solo usa pandas y la biblioteca estándar.
"""
from __future__ import annotations

import argparse
import http.client
import io
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
DATA = RAIZ / "data"

BDB_BASE = "https://raw.githubusercontent.com/ThompsonJamesBliss/nfl-big-data-bowl-regional-event-data/main/data"
BDB_ARCHIVOS = ["games.csv", "plays.csv", "pffScoutingData.csv"]

NFLVERSE_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{anio}.csv"
TEMPORADAS = list(range(2018, 2024))
SALIDA_PBP = DATA / "nflverse_pbp_filtered.csv"

TIPOS_JUGADA = {"pass", "run", "punt", "field_goal"}

COLUMNAS_PBP = [
    "season", "week", "old_game_id", "play_id", "posteam", "defteam",
    "qtr", "down", "ydstogo", "yardline_100",
    "game_seconds_remaining", "half_seconds_remaining", "score_differential",
    "posteam_timeouts_remaining", "defteam_timeouts_remaining",
    "play_type", "pass_length", "pass_location", "run_location",
    "yards_gained", "epa", "wp", "wpa", "success",
    "fourth_down_converted", "fourth_down_failed",
    "field_goal_result", "kick_distance", "return_yards",
    "qb_scramble", "sack", "interception", "touchdown", "penalty", "punt_blocked",
]


def log(msg: str) -> None:
    print(msg, flush=True)


def descargar(url: str, intentos: int = 3) -> bytes:
    ultimo: Exception | None = None
    for i in range(1, intentos + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "hackathon-unam"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except (OSError, http.client.HTTPException) as e:
            ultimo = e
            log(f"    intento {i}/{intentos} falló: {e}")
            time.sleep(2 * i)
    raise RuntimeError(f"No se pudo descargar {url}: {ultimo}")


def preparar_bdb(force: bool) -> None:
    log("[1/2] Big Data Bowl")
    DATA.mkdir(exist_ok=True)
    for nombre in BDB_ARCHIVOS:
        destino = DATA / nombre
        if destino.exists() and not force:
            log(f"    {nombre}: ya existe, se conserva")
            continue
        log(f"    {nombre}: descargando")
        destino.write_bytes(descargar(f"{BDB_BASE}/{nombre}"))
        log(f"    {nombre}: {destino.stat().st_size / 1e6:.1f} MB")


def preparar_nflverse(force: bool) -> None:
    log("[2/2] nflverse play-by-play")
    if SALIDA_PBP.exists() and not force:
        log(f"    {SALIDA_PBP.name}: ya existe, se conserva")
        return
    partes = []
    for anio in TEMPORADAS:
        log(f"    {anio}: descargando")
        crudo = descargar(NFLVERSE_URL.format(anio=anio))
        disponibles = pd.read_csv(io.BytesIO(crudo), nrows=0).columns
        faltan = [c for c in COLUMNAS_PBP if c not in disponibles]
        if faltan:
            log(f"    {anio}: columnas ausentes (se dejan vacías): {faltan}")
        df = pd.read_csv(io.BytesIO(crudo), usecols=[c for c in COLUMNAS_PBP if c in disponibles], low_memory=False)
        for c in faltan:
            df[c] = pd.NA
        df = df[df["play_type"].isin(TIPOS_JUGADA)]
        df = df.dropna(subset=["down", "yardline_100", "game_seconds_remaining", "epa"])
        df["down"] = df["down"].astype(int)
        partes.append(df[COLUMNAS_PBP])
        log(f"    {anio}: {len(df)} jugadas")
    todo = pd.concat(partes, ignore_index=True)
    for c in todo.select_dtypes("float").columns:
        todo[c] = todo[c].round(4)
    todo.to_csv(SALIDA_PBP, index=False)
    log(f"    escrito {SALIDA_PBP.relative_to(RAIZ)}: {len(todo)} filas, {SALIDA_PBP.stat().st_size / 1e6:.1f} MB")


def resumen() -> None:
    log("\nResumen")
    pbp = pd.read_csv(SALIDA_PBP, low_memory=False)
    log("  Jugadas por temporada:")
    for anio, n in pbp.groupby("season").size().items():
        log(f"    {anio}: {n}")
    log("  Jugadas por tipo:")
    for tipo, n in pbp.groupby("play_type").size().items():
        log(f"    {tipo}: {n}")
    log(f"  Jugadas de 4o down: {int((pbp['down'] == 4).sum())}")

    plays = pd.read_csv(DATA / "plays.csv", usecols=["gameId", "playId"])
    llaves = pbp[pbp["season"] == 2021][["old_game_id", "play_id"]].rename(
        columns={"old_game_id": "gameId", "play_id": "playId"}
    )
    unidas = plays.merge(llaves, on=["gameId", "playId"], how="inner")
    pct = 100 * len(unidas) / max(len(plays), 1)
    log(f"  Union BDB-nflverse (2021): {len(unidas)} de {len(plays)} jugadas BDB ({pct:.1f}%)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="vuelve a descargar todo")
    args = ap.parse_args()
    preparar_bdb(args.force)
    preparar_nflverse(args.force)
    resumen()
    return 0


if __name__ == "__main__":
    sys.exit(main())
