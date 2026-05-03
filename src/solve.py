"""
Resol un trencaclosques de peces lliscants usant el graf d'estats.

Troba el camí mínim entre l'estat inicial i un estat final mitjançant BFS
natiu de graph-tool (implementat en C++), i desa la seqüència de moviments
en format .sol.json.

Ús:
    pixi run python src/solve.py puzzles/sample1.graphml
    pixi run python src/movie.py puzzles/sample1.json puzzles/sample1.sol.json
    pixi run python src/3D_view.py puzzles/sample1.graphml puzzles/sample1.sol.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import graph_tool.all as gt  # type: ignore[import-untyped]

from puzzle import Puzzle, State


def find_move(state_a: State, state_b: State) -> tuple[int, str, int]:
    """
    Donats dos estats consecutius, retorna el moviment (peça, direcció, distància)
    que porta de state_a a state_b.

    Només una peça pot haver canviat de posició entre dos estats adjacents
    (per construcció del graf), de manera que n'hi ha prou amb trobar
    el primer índex on difereixen les posicions.
    """
    for i, (pos_a, pos_b) in enumerate(zip(state_a.positions, state_b.positions)):
        if pos_a != pos_b:
            dx = pos_b[0] - pos_a[0]
            dy = pos_b[1] - pos_a[1]
            if   dx > 0: return (i, "E",  dx)
            elif dx < 0: return (i, "W", -dx)
            elif dy > 0: return (i, "S",  dy)
            else:        return (i, "N", -dy)
    raise ValueError("Els dos estats són iguals: no hi ha moviment entre ells")


def solve(g: gt.Graph, puzzle: Puzzle) -> list[tuple[int, str, int]] | None:
    """
    Troba el camí mínim des de l'estat inicial fins a un estat final.

    Optimitzacions respecte la versió original:
    - Usa `gt.shortest_path` (BFS en C++) en comptes d'un BFS manual en Python.
      Per a grafs grans (puzzles 9×9) la diferència és d'ordres de magnitud.
    - Si hi ha múltiples estats finals, busca el més proper a l'inicial
      comparant les distàncies i quedant-se amb el camí més curt.
    - `find_move` ja no rep `puzzle` com a paràmetre perquè no l'usa;
      eliminant l'argument innecessari.
    - Els estats es parsegen des de JSON només per als nodes del camí òptim,
      no per a tots els nodes del graf.

    Retorna la llista de moviments (peça, direcció, distància),
    o None si el puzzle no té solució.
    """
    is_start_prop = g.vp["is_start"]
    is_goal_prop  = g.vp["is_goal"]
    state_prop    = g.vp["state"]

    # Identifiquem el node inicial i els nodes finals en una sola passada
    start_v: gt.Vertex | None = None
    goal_vertices: list[gt.Vertex] = []

    for v in g.vertices():
        if is_start_prop[v]:
            start_v = v
        if is_goal_prop[v]:
            goal_vertices.append(v)

    if start_v is None:
        raise ValueError("No s'ha trobat l'estat inicial al graf")
    if not goal_vertices:
        raise ValueError("No s'ha trobat cap estat final al graf")

    # ── Camí mínim amb BFS natiu de graph-tool (C++) ──────────────────
    # gt.shortest_path retorna (llista_de_vèrtexs, llista_d'arestes).
    # Si no hi ha camí, la llista de vèrtexs és buida.
    # Quan hi ha múltiples estats finals, provem tots i ens quedem el més curt.
    best_path: list[gt.Vertex] = []

    for goal_v in goal_vertices:
        vlist, _ = gt.shortest_path(g, start_v, goal_v)
        if vlist and (not best_path or len(vlist) < len(best_path)):
            best_path = vlist

    if not best_path:
        return None  # puzzle sense solució

    # ── Convertim el camí de nodes a moviments ────────────────────────
    # Parsegem JSON només per als nodes del camí (no per a tots els nodes).
    def parse_state(v: gt.Vertex) -> State:
        return State(tuple(tuple(p) for p in json.loads(state_prop[v])))

    moves = [
        find_move(parse_state(best_path[i]), parse_state(best_path[i + 1]))
        for i in range(len(best_path) - 1)
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