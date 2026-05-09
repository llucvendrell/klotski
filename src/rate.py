"""
Envia la valoració d'un puzzle al repositori compartit.

Calcula la puntuació automàticament a partir del graf i l'envia al servidor.

Ús:
    python src/rate.py <puzzle.json> <token>
    python src/rate.py <puzzle.json> <token> --id <id_puzzle>
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

import graph_tool.all as gt  # type: ignore[import-untyped]

from eval3 import evaluate # IMPORTANTÍÍÍÍÍSSIM: s'importa d'(eval3), el que genera també grphml i té el M2 com a la mitjana de veïns!! Quan ho fem definitiu caldrà canviar-ho
from graph import build_graph
from puzzle import Puzzle

BASE_URL = "https://klotski.pauek.dev/api"


def send_rating(puzzle_id: str, stars: float, token: str) -> None:
    """Envia la valoració d'un puzzle al servidor."""
    url = f"{BASE_URL}/puzzles/{puzzle_id}/votes"
    data = json.dumps({"stars": stars}).encode()
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def get_puzzle_id(puzzle: Puzzle) -> str:
    """Retorna el hash SHA256 del puzzle, que és el seu ID al repositori."""
    return puzzle.hash()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Envia la valoració d'un puzzle al repositori compartit"
    )
    parser.add_argument("puzzle", type=Path, help="Fitxer .json o .graphml del puzzle")
    parser.add_argument("token", help="Token d'autenticació")
    parser.add_argument("--id", help="ID del puzzle (opcional, es calcula automàticament)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Mostra el detall de les mesures")
    args = parser.parse_args()

    if not args.puzzle.exists():
        print(f"Error: no s'ha trobat {args.puzzle}", file=sys.stderr)
        sys.exit(1)

    # Carreguem el graf i el puzzle
    if args.puzzle.suffix == ".graphml":
        print(f"Carregant graf '{args.puzzle.stem}'...")
        g = gt.load_graph(str(args.puzzle))
        puzzle = Puzzle.from_json(g.gp["puzzle"])
    else:
        puzzle = Puzzle.from_json(args.puzzle.read_text())
        print(f"Construint graf de '{args.puzzle.stem}'...")
        g = build_graph(puzzle)

    # Calculem la puntuació
    print(f"Avaluant '{args.puzzle.stem}'...")
    stars = evaluate(puzzle, g, verbose=args.verbose)
    print(f"★ Puntuació: {stars:.2f} / 5.00")

    # Obtenim l'ID del puzzle
    puzzle_id = args.id if args.id else get_puzzle_id(puzzle)
    print(f"ID: {puzzle_id[:8]}...")

    # Enviem la valoració
    print("Enviant valoració...")
    send_rating(puzzle_id, stars, args.token)
    print("Valoració enviada correctament!")