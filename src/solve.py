"""
Resol un trencaclosques de peces lliscants usant el graf d'estats.

Troba el camí mínim entre l'estat inicial i un estat final mitjançant
un sol BFS des de l'inici, evitant fer un BFS per cada estat final.

Ús:
    pixi run python src/solve.py puzzles/sample1.graphml
    pixi run python src/movie.py puzzles/sample1.json puzzles/sample1.sol.json
    pixi run python src/3D_view.py puzzles/sample1.graphml puzzles/sample1.sol.json
"""

from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path

import numpy as np
import graph_tool.all as gt  # type: ignore[import-untyped]

from logic import possible_moves, apply_move
from puzzle import Puzzle, State


def solve(g: gt.Graph, puzzle: Puzzle) -> list[tuple[int, str, int]] | None:
    """
    Troba el camí mínim des de l'estat inicial fins al goal més proper.

    Estratègia: BFS directament sobre els estats del joc (no sobre el graf).
    Això garanteix que cada moviment és vàlid per apply_move i movie.py,
    independentment de si el graf té arestes incorrectes o duplicades.

    El graf s'usa NOMÉS per saber quins nodes són goals, evitant haver
    de cridar is_goal() en cada pas (que requeriria conèixer els objectius
    del puzzle, cosa que ja tenim via puzzle.goals).

    Complexitat: O(V+E) — BFS estàndard sobre l'espai d'estats.
    """
    from logic import is_goal as _is_goal

    # BFS sobre estats del joc, no sobre nodes del graf
    # Cada element de la cua és (estat_actual, moviments_fets)
    # Usem un diccionari per evitar visitar el mateix estat dues vegades
    visited: dict[tuple, list[tuple[int, str, int]]] = {}
    queue: deque[tuple[State, list[tuple[int, str, int]]]] = deque()

    start = puzzle.start
    visited[start.positions] = []
    queue.append((start, []))

    while queue:
        current, path = queue.popleft()

        # Comprovem si és un estat final
        if _is_goal(puzzle, current):
            return path

        # Expandim tots els moviments vàlids
        for move in possible_moves(puzzle, current):
            next_state = apply_move(puzzle, current, move)
            key = next_state.positions
            if key not in visited:
                new_path = path + [move]
                visited[key] = new_path
                queue.append((next_state, new_path))

    return None  # no hi ha solució


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Ús: python {sys.argv[0]} <graf.graphml> [sortida.sol.json]")
        sys.exit(1)

    graphml_path = Path(sys.argv[1])
    if not graphml_path.exists():
        print(f"Error: no s'ha trobat {graphml_path}")
        sys.exit(1)

    print(f"Carregant graf '{graphml_path.stem}'...")
    g = gt.load_graph(str(graphml_path))
    puzzle = Puzzle.from_json(g.gp["puzzle"])

    print("Resolent...")
    moves = solve(g, puzzle)

    if moves is None:
        print("El puzzle no té solució!")
        sys.exit(1)

    print(f"Solució trobada: {len(moves)} moviments")

    out_path = (
        Path(sys.argv[2]) if len(sys.argv) >= 3
        else graphml_path.with_suffix(".sol.json")
    )
    out_path.write_text(json.dumps([[p, d, dist] for p, d, dist in moves]))
    print(f"Solució desada: {out_path}")