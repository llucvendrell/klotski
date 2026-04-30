"""
Resol un trencaclosques de peces lliscants usant el graf d'estats.

Troba el camí mínim entre l'estat inicial i un estat final mitjançant BFS,
i desa la seqüència de moviments en format .sol.json.

Ús:
    pixi run python src/solve.py puzzles/sample1.graphml (Resol el puzzle a partir del graf, ja generat)
    pixi run python src/movie.py puzzles/sample1.json puzzles/sample1.sol.json
    pixi run python src/3D_view.py puzzles/sample1.graphml puzzles/sample1.sol.json
"""
# Canvis: canviar la variable (queue) que era de tipus llista a una deque, per a evitar el pop(0) usant popleft, temps constant.


from __future__ import annotations

from collections import deque
import json
import sys
from pathlib import Path

import graph_tool.all as gt  # type: ignore[import-untyped]

from graph import state_key
from puzzle import Puzzle, State


def find_move(puzzle: Puzzle, state_a: State, state_b: State) -> tuple[int, str, int]:
    """
    Donats dos estats consecutius, retorna el moviment (peça, direcció, distància)
    que porta de state_a a state_b.
    """
    for i, (pos_a, pos_b) in enumerate(zip(state_a.positions, state_b.positions)):
        if pos_a != pos_b:
            dx = pos_b[0] - pos_a[0]
            dy = pos_b[1] - pos_a[1]
            if dx > 0:
                return (i, "E", dx)
            elif dx < 0:
                return (i, "W", -dx)
            elif dy > 0:
                return (i, "S", dy)
            else:
                return (i, "N", -dy)
    raise ValueError("Els dos estats són iguals")


def solve(g: gt.Graph, puzzle: Puzzle) -> list[tuple[int, str, int]] | None:
    """
    Troba el camí mínim des de l'estat inicial fins a un estat final.
    Retorna la llista de moviments, o None si no hi ha solució.
    """
    state_prop = g.vp["state"]
    is_start_prop = g.vp["is_start"]
    is_goal_prop = g.vp["is_goal"]

    # Trobem el node inicial i els nodes finals
    start_v = None
    goal_vertices = []
    for v in g.vertices():
        if is_start_prop[v]:
            start_v = v
        if is_goal_prop[v]:
            goal_vertices.append(v)

    if start_v is None:
        raise ValueError("No s'ha trobat l'estat inicial al graf")
    if not goal_vertices:
        raise ValueError("No s'ha trobat cap estat final al graf")

    # BFS des del node inicial
    # graph-tool té BFS integrat, però reconstruir el camí és més fàcil manualment
    visited = {int(start_v): None}  # node → node pare
    queue = deque([start_v])
    goal_v = None

    while queue:
        current = queue.popleft()
        if is_goal_prop[current]:
            goal_v = current
            break
        for neighbor in current.out_neighbors():
            if int(neighbor) not in visited:
                visited[int(neighbor)] = int(current)
                queue.append(neighbor)

    if goal_v is None:
        return None  # No hi ha solució

    # Reconstruïm el camí de nodes des de l'inicial fins al final
    path = []
    node = int(goal_v)
    while node is not None:
        path.append(node)
        node = visited[node]
    path.reverse()

    # Convertim el camí de nodes a moviments
    moves = []
    for i in range(len(path) - 1):
        v_a = g.vertex(path[i])
        v_b = g.vertex(path[i + 1])
        state_a = State(tuple(tuple(p) for p in json.loads(state_prop[v_a])))
        state_b = State(tuple(tuple(p) for p in json.loads(state_prop[v_b])))
        moves.append(find_move(puzzle, state_a, state_b))

    return moves


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

    # Nom del fitxer de sortida
    out_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else graphml_path.with_suffix(".sol.json")
    out_path.write_text(json.dumps([[p, d, dist] for p, d, dist in moves]))
    print(f"Solució desada: {out_path}")