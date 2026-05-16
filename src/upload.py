"""
Puja un puzzle nou al repositori compartit.

El token d'autenticació es llegeix de la variable d'entorn KLOTSKI_TOKEN
o d'un fitxer .token al directori arrel del projecte.

Ús:
    python src/upload.py <puzzle.json>
    python src/upload.py <puzzle.json> --verbose
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

BASE_URL   = "https://klotski.pauek.dev/api"
TOKEN_FILE = Path(".token")


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


# ── CLI ───────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Puja un puzzle nou al repositori compartit"
    )
    parser.add_argument("puzzle", type=Path, help="Fitxer .json del puzzle a pujar")
    parser.add_argument("--verbose", "-v", action="store_true", help="Mostra el JSON del puzzle")
    args = parser.parse_args()

    if not args.puzzle.exists():
        print(f"Error: no s'ha trobat {args.puzzle}", file=sys.stderr)
        sys.exit(1)

    puzzle = Puzzle.from_json(args.puzzle.read_text())
    print(f"Puzzle: {puzzle.W}×{puzzle.H}, {len(puzzle.pieces)} peces")
    print(f"Hash: {puzzle.hash()[:8]}...")

    if args.verbose:
        print(puzzle.to_json(indent=2))

    token = load_token()

    print("Pujant puzzle...")
    try:
        response = upload_puzzle(puzzle, token)
        print(f"Puzzle pujat correctament! ID: {response.get('id', '?')[:8]}...")
    except urllib.error.HTTPError as e:
        print(f"Error HTTP {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error de connexió: {e.reason}", file=sys.stderr)
        sys.exit(1)