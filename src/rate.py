"""
Envia la valoració d'un puzzle al repositori compartit.

Usa eval.py propi: evaluate(puzzle, g, verbose).
Prioritza .graphml si existeix (més ràpid); si no, construeix el graf.

El token d'autenticació es llegeix de la variable d'entorn KLOTSKI_TOKEN
o d'un fitxer .token al directori arrel del projecte.

Ús:
    python src/rate.py <id>               # avalua i envia la valoració
    python src/rate.py <id> --dry-run     # avalua però no envia
    python src/rate.py <id> --verbose     # mostra detall de les mesures
    python src/rate.py --all              # avalua i envia tots els puzzles
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import graph_tool.all as gt  # type: ignore[import-untyped]

from eval import evaluate
from graph import build_graph
from puzzle import Puzzle

BASE_URL    = "https://klotski.pauek.dev/api"
PUZZLES_DIR = Path("puzzles")
TOKEN_FILE  = Path(".token")


# ── Token ─────────────────────────────────────────────────────────────────────


def load_token() -> str:
    """
    Carrega el token d'autenticació.

    Ordre de prioritat:
      1. Variable d'entorn KLOTSKI_TOKEN
      2. Fitxer .token al directori arrel del projecte
    """
    token = os.environ.get("KLOTSKI_TOKEN")
    if token:
        return token.strip()
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    print(
        "Error: no s'ha trobat el token d'autenticació.\n"
        "Opcions:\n"
        "  1. Crea un fitxer .token amb el teu token\n"
        "  2. Exporta la variable: export KLOTSKI_TOKEN=el_teu_token",
        file=sys.stderr,
    )
    sys.exit(1)


# ── Càrrega del puzzle i el graf ─────────────────────────────────────────────


def load_puzzle_and_graph(puzzle_id: str) -> tuple[Puzzle, gt.Graph | None] | None:
    """
    Carrega el puzzle i opcionalment el graf a partir de l'ID.

    Prioritza el .graphml si existeix: en aquest cas retorna el graf ja
    construït i evaluate no l'ha de reconstruir. Si només hi ha .json,
    retorna el graf com a None i evaluate el construirà internament.
    """
    candidates: list[tuple[Path, str]] = [
        (PUZZLES_DIR / f"{puzzle_id[:8]}.graphml", "graphml"),
        (PUZZLES_DIR / f"{puzzle_id}.graphml",     "graphml"),
        (PUZZLES_DIR / f"{puzzle_id[:8]}.json",    "json"),
        (PUZZLES_DIR / f"{puzzle_id}.json",         "json"),
    ]

    for path, fmt in candidates:
        if not path.exists():
            continue
        if fmt == "graphml":
            print(f"  Carregant graf '{path.name}'...")
            g = gt.load_graph(str(path))
            puzzle = Puzzle.from_json(g.gp["puzzle"])
            return puzzle, g
        else:
            puzzle = Puzzle.from_json(path.read_text())
            return puzzle, None  # evaluate construirà el graf

    print(
        f"  [✗] {puzzle_id[:8]}: fitxer no trobat a '{PUZZLES_DIR}/'.\n"
        f"      Executa primer: python src/download.py {puzzle_id}",
        file=sys.stderr,
    )
    return None


# ── Comunicació amb el servidor ───────────────────────────────────────────────


def send_rating(puzzle_id: str, stars: int, token: str) -> None:
    """Envia una valoració (enter 1-5) al repositori via POST."""
    url  = f"{BASE_URL}/puzzles/{puzzle_id}/votes"
    body = json.dumps({"rating": stars}).encode()
    request = urllib.request.Request(
        url,
        data    = body,
        method  = "POST",
        headers = {
            "Content-Type" : "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(request) as response:
        response.read()


# ── Lògica d'alt nivell ───────────────────────────────────────────────────────


def rate_one(
    puzzle_id: str,
    token: str,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> int | None:
    """
    Avalua un puzzle i envia la valoració al servidor.
    Retorna la puntuació (enter 1-5) o None si hi ha hagut un error.
    """
    result = load_puzzle_and_graph(puzzle_id)
    if result is None:
        return None

    puzzle, g = result

    try:
        # verbose és posicional a evaluate(puzzle, g, verbose)
        stars = evaluate(puzzle, g, verbose)
    except Exception as e:
        print(f"  [✗] {puzzle_id[:8]}: error avaluant ({e})", file=sys.stderr)
        return None

    # stars és un enter 1-5
    print(f"  [★] {puzzle_id[:8]}: {stars} / 5", end="")

    if dry_run:
        print("  (dry-run, no s'ha enviat)")
        return stars

    try:
        send_rating(puzzle_id, stars, token)
        print("  → enviat")
    except urllib.error.HTTPError as e:
        print(f"\n  [✗] Error HTTP {e.code} en enviar la valoració", file=sys.stderr)
        return None
    except urllib.error.URLError as e:
        print(f"\n  [✗] Error de connexió: {e.reason}", file=sys.stderr)
        return None

    return stars


def rate_all(
    token: str,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    """Avalua i envia la valoració de tots els puzzles descarregats."""
    ids = sorted({
        p.stem for p in PUZZLES_DIR.glob("*")
        if p.suffix in (".json", ".graphml")
    })
    if not ids:
        print(f"No s'ha trobat cap puzzle a '{PUZZLES_DIR}/'.")
        return

    print(f"Avaluant {len(ids)} puzzle(s)...\n")
    ok, failed = 0, 0

    for i, puzzle_id in enumerate(ids, start=1):
        print(f"[{i:3}/{len(ids)}]", end=" ")
        result = rate_one(puzzle_id, token, dry_run=dry_run, verbose=verbose)
        if result is not None:
            ok += 1
        else:
            failed += 1

    print(f"\nEnviats: {ok}  |  Fallits: {failed}")


# ── CLI ───────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Avalua i envia la valoració d'un puzzle (usa eval.py propi)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python src/rate.py abc12345              # avalua i envia
  python src/rate.py abc12345 --dry-run    # avalua sense enviar
  python src/rate.py abc12345 --verbose    # mostra detall de les mesures
  python src/rate.py --all                 # envia tots els descarregats
        """,
    )
    parser.add_argument("id", nargs="?", metavar="ID", help="Identificador del puzzle")
    parser.add_argument("--all", action="store_true", help="Avalua tots els puzzles descarregats")
    parser.add_argument("--dry-run", action="store_true", help="Avalua però no envia")
    parser.add_argument("--verbose", "-v", action="store_true", help="Mostra detall de les mesures")
    args = parser.parse_args()

    if not args.id and not args.all:
        parser.print_help()
        sys.exit(1)

    token = load_token()

    if args.all:
        rate_all(token, dry_run=args.dry_run, verbose=args.verbose)
    else:
        print(f"Avaluant '{args.id[:8]}'...")
        result = rate_one(args.id, token, dry_run=args.dry_run, verbose=args.verbose)
        if result is None:
            sys.exit(1)