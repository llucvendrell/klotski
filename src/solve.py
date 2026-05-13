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
from pathlib import Path

import numpy as np
import graph_tool.all as gt  # type: ignore[import-untyped]

from puzzle import Puzzle, State


def find_moves(state_a: State, state_b: State) -> list[tuple[int, str, int]]:
    """
    Donats dos estats consecutius, retorna la llista de moviments d'1 pas
    que porten de state_a a state_b.

    Sempre retorna moviments amb distància=1 per compatibilitat amb
    apply_move i movie.py, que apliquen els moviments pas a pas.

    Si la distància és >1 (la peça ha lliscat múltiples caselles),
    es descompon en múltiples moviments d'1 pas.
    """
    for i, (pos_a, pos_b) in enumerate(zip(state_a.positions, state_b.positions)):
        if pos_a != pos_b:
            dx = pos_b[0] - pos_a[0]
            dy = pos_b[1] - pos_a[1]
            if   dx > 0: return [(i, "E", 1)] * dx
            elif dx < 0: return [(i, "W", 1)] * (-dx)
            elif dy > 0: return [(i, "S", 1)] * dy
            else:        return [(i, "N", 1)] * (-dy)
    raise ValueError("Els dos estats són iguals: no hi ha moviment entre ells")


def solve(g: gt.Graph, puzzle: Puzzle) -> list[tuple[int, str, int]] | None:
    """
    Troba el camí mínim des de l'estat inicial fins al goal més proper.

    Optimització clau respecte la versió anterior:
    La versió anterior feia un gt.shortest_path per a CADA goal:
        88.965 goals × O(V+E) = O(88.965 × 3.5M) → hores de càlcul

    Aquesta versió fa UN SOL gt.shortest_distance des de l'inici,
    que calcula les distàncies a TOTS els nodes en O(V+E).
    Després troba el goal més proper amb np.argmin sobre l'array
    de distàncies filtrat pels índexs dels goals: O(n_goals).

    Finalment, reconstrueix el camí cap al goal més proper amb
    gt.shortest_path (un sol BFS addicional): O(V+E).

    Total: 2 BFS en comptes de n_goals BFS.
    Per a 88.965 goals: 44.482× més ràpid.
    """
    is_start_prop = g.vp["is_start"]
    is_goal_prop  = g.vp["is_goal"]
    state_prop    = g.vp["state"]

    # ── Arrays numpy d'una passada ────────────────────────────────────
    is_start_arr = is_start_prop.a
    is_goal_arr  = is_goal_prop.a

    start_indices = np.where(is_start_arr)[0]
    goal_indices  = np.where(is_goal_arr)[0]

    if len(start_indices) == 0:
        raise ValueError("No s'ha trobat l'estat inicial al graf")
    if len(goal_indices) == 0:
        raise ValueError("No s'ha trobat cap estat final al graf")

    start_v = g.vertex(int(start_indices[0]))

    # ── BFS 1: distàncies des de l'inici a tots els nodes ────────────
    dist_prop = gt.shortest_distance(g, source=start_v)
    dist_arr  = dist_prop.a                          # numpy array, O(1) per node

    # ── Goal més proper: argmin sobre l'array filtrat ─────────────────
    goal_dists = dist_arr[goal_indices]              # distàncies als goals, O(n_goals)
    best_local = int(np.argmin(goal_dists))          # índex local al array de goals
    best_dist  = int(goal_dists[best_local])

    if best_dist >= 2**30:
        return None  # cap goal és accessible des de l'inici

    best_goal_v = g.vertex(int(goal_indices[best_local]))

    # ── BFS 2: camí fins al goal més proper ───────────────────────────
    # gt.shortest_path és O(V+E) però molt ràpid en C++.
    # Alternativa: reconstruir el camí des de dist_prop amb predecessor_map,
    # però shortest_path ja ho fa internament de forma òptima.
    best_path, _ = gt.shortest_path(g, start_v, best_goal_v)

    if not best_path:
        return None

    # ── Convertim el camí a moviments ─────────────────────────────────
    # Parsegem JSON només per als nodes del camí òptim (no tots els nodes).
    def parse_state(v: gt.Vertex) -> State:
        return State(tuple(tuple(p) for p in json.loads(state_prop[v])))

    moves = [
        m
        for i in range(len(best_path) - 1)
        for m in find_moves(parse_state(best_path[i]), parse_state(best_path[i + 1]))
    ]

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

    out_path = (
        Path(sys.argv[2]) if len(sys.argv) >= 3
        else graphml_path.with_suffix(".sol.json")
    )
    out_path.write_text(json.dumps([[p, d, dist] for p, d, dist in moves]))
    print(f"Solució desada: {out_path}")