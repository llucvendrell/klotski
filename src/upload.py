"""
Puja un puzzle nou al repositori compartit.

El token d'autenticació es llegeix de la variable d'entorn KLOTSKI_TOKEN
o d'un fitxer .token al directori arrel del projecte.

Ús:
    python src/upload.py puzzles/<puzzle.json>           # puja un puzzle
    python src/upload.py puzzles/<puzzle.json> --verbose # mostra el JSON
    python src/upload.py --all                   # puja tots els puzzles generats
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from puzzle import Puzzle

BASE_URL    = "https://klotski.pauek.dev/api"
TOKEN_FILE  = Path(".token")
PUZZLES_DIR = Path("generats")


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


# ── Enviament ─────────────────────────────────────────────────────────────────


def upload_puzzle(puzzle: Puzzle, token: str) -> dict:
    """Envia un puzzle nou al repositori i retorna la resposta del servidor."""
    url  = f"{BASE_URL}/puzzles"
    body = puzzle.to_json().encode()
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
        return json.loads(response.read())


def upload_one(path: Path, token: str, *, verbose: bool = False) -> bool:
    """
    Carrega, valida i puja un puzzle.
    Retorna True si s'ha pujat correctament, False si hi ha hagut un error.
    """
    try:
        puzzle = Puzzle.from_json(path.read_text())
    except Exception as e:
        print(f"  [✗] {path.name}: JSON invàlid ({e})", file=sys.stderr)
        return False

    print(f"  Puzzle: {puzzle.W}×{puzzle.H}, {len(puzzle.pieces)} peces  "
          f"[{puzzle.hash()[:8]}]")

    if verbose:
        print(puzzle.to_json(indent=2))

    try:
        response = upload_puzzle(puzzle, token)
        # L'ID pot venir com a string o com a altre tipus segons el servidor
        puzzle_id = str(response.get("id", "?"))
        print(f"  [✓] Pujat correctament! ID: {puzzle_id[:8]}...")
        return True
    except urllib.error.HTTPError as e:
        print(f"  [✗] Error HTTP {e.code}: {e.reason}", file=sys.stderr)
        return False
    except urllib.error.URLError as e:
        print(f"  [✗] Error de connexió: {e.reason}", file=sys.stderr)
        return False


# ── CLI ───────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Puja puzzles nous al repositori compartit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python src/upload.py puzzles/sample1.json
  python src/upload.py puzzles/sample1.json --verbose
  python src/upload.py --all
        """,
    )
    parser.add_argument(
        "puzzle", nargs="?", type=Path,
        help="Fitxer .json del puzzle a pujar",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Puja tots els puzzles .json de la carpeta generats/",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Mostra el JSON del puzzle",
    )
    args = parser.parse_args()

    if not args.puzzle and not args.all:
        parser.print_help()
        sys.exit(1)

    token = load_token()

    # ── Pujar un sol puzzle ───────────────────────────────────────────
    if args.puzzle:
        if not args.puzzle.exists():
            print(f"Error: no s'ha trobat {args.puzzle}", file=sys.stderr)
            sys.exit(1)
        print(f"Pujant '{args.puzzle.name}'...")
        ok = upload_one(args.puzzle, token, verbose=args.verbose)
        if not ok:
            sys.exit(1)

    # ── Pujar tots els puzzles ────────────────────────────────────────
    elif args.all:
        files = sorted(PUZZLES_DIR.glob("*.json"))
        if not files:
            print(f"No s'ha trobat cap .json a '{PUZZLES_DIR}/'.")
            sys.exit(1)

        print(f"Pujant {len(files)} puzzle(s) de '{PUZZLES_DIR}/'...\n")
        ok_count = sum(
            1 for f in files
            if upload_one(f, token, verbose=args.verbose)
        )
        print(f"\nPujats: {ok_count}  |  Fallits: {len(files) - ok_count}")