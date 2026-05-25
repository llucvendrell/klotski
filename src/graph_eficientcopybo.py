"""
Construeix el graf d'estats d'un trencaclosques de peces lliscants.

Cada node representa una disposició de les peces, i cada aresta representa
un moviment vàlid d'una peça entre dues disposicions.

L'exploració es fa amb DFS des de l'estat inicial.

El graf es desa en format .graphml per poder-lo carregar amb altres eines.

Millores respecte la versió original:
  - state_key agrupa peces amb la mateixa forma i ordena les seves posicions
    dins de cada grup: dos estats que difereixen només en l'intercanvi de
    peces iguals es consideren el MATEIX node → graf més petit.
  - if src_idx < dst_idx: evita arestes duplicades.
  - La pila del DFS guarda (state, src_idx, state_key) per evitar
    recalcular state_key dues vegades per node.
  - max_nodes: permet aturar el DFS si el graf és massa gran.

Ús:
    pixi run python src/graph.py puzzles/sample1.json
    pixi run python src/3D_view.py puzzles/sample1.graphml
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import graph_tool.all as gt  # type: ignore[import-untyped]

from logic import possible_moves, apply_move, is_goal
from puzzle import Puzzle, State

StateKey = tuple[tuple[int, int], ...]


def state_key(puzzle: Puzzle, state: State | str) -> StateKey:
    """
    Retorna la clau canònica d'un estat.

    Peces amb la mateixa forma es consideren intercanviables: les seves
    posicions s'ordenen dins de cada grup. Dos estats que difereixen
    només en l'intercanvi de peces iguals tenen la mateixa clau →
    mateix node al graf → graf més petit i ràpid.

    Si l'estat és un string JSON (com el que desa graph-tool), el parseja.
    """
    if isinstance(state, str):
        positions: list[tuple[int, int]] = [tuple(p) for p in json.loads(state)]
    else:
        positions = list(state.positions)

    result: list[tuple[int, int]] = []
    i = 0
    while i < len(puzzle.pieces):
        j = i + 1
        while j < len(puzzle.pieces) and puzzle.pieces[j] == puzzle.pieces[i]:
            j += 1
        result.extend(sorted(positions[i:j]))
        i = j

    return tuple(result)


def build_graph(puzzle: Puzzle, max_nodes: int = 0) -> gt.Graph | None:
    """
    Construeix el graf d'estats del puzzle mitjançant DFS iteratiu.

    Retorna un graf no dirigit amb:
    - vp['state']   : posicions de cada node (JSON)
    - vp['is_start']: True si és l'estat inicial
    - vp['is_goal'] : True si és un estat final
    - gp['puzzle']  : JSON del puzzle (metadada del graf)

    Si max_nodes > 0, retorna None si el graf supera aquest límit.
    """
    g = gt.Graph(directed=False)

    state_prop    = g.new_vertex_property("string")
    is_start_prop = g.new_vertex_property("bool")
    is_goal_prop  = g.new_vertex_property("bool")

    # visited: StateKey → índex enter del vèrtex (O(1) per accés)
    visited: dict[StateKey, int] = {}

    start_key = state_key(puzzle, puzzle.start)

    # Creem el node inicial
    v0   = g.add_vertex()
    idx0 = int(v0)
    visited[start_key] = idx0
    state_prop[v0]     = json.dumps([list(p) for p in start_key])
    is_start_prop[v0]  = True
    is_goal_prop[v0]   = is_goal(puzzle, puzzle.start)

    # DFS: la pila guarda (estat, índex_src, clau_src) per evitar
    # recalcular state_key quan el traiem de la pila.
    stack: list[tuple[State, int, StateKey]] = [
        (puzzle.start, idx0, start_key)
    ]

    while stack:
        current, src_idx, _ = stack.pop()

        if max_nodes > 0 and g.num_vertices() > max_nodes:
            return None

        for move in possible_moves(puzzle, current):
            nxt     = apply_move(puzzle, current, move)
            nxt_key = state_key(puzzle, nxt)

            if nxt_key in visited:
                dst_idx = visited[nxt_key]
            else:
                # Node nou: creem el vèrtex i les seves propietats
                v       = g.add_vertex()
                dst_idx = int(v)
                visited[nxt_key]  = dst_idx
                state_prop[v]     = json.dumps([list(p) for p in nxt_key])
                is_start_prop[v]  = (nxt_key == start_key)
                is_goal_prop[v]   = is_goal(puzzle, nxt)
                stack.append((nxt, dst_idx, nxt_key))

            # Afegim l'aresta exactament una vegada (sense duplicats)
            if src_idx < dst_idx:
                g.add_edge(src_idx, dst_idx)

    # Desem propietats al graf
    g.vp["state"]    = state_prop
    g.vp["is_start"] = is_start_prop
    g.vp["is_goal"]  = is_goal_prop
    g.gp["puzzle"]   = g.new_graph_property("string", puzzle.to_json())

    return g


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Ús: python {sys.argv[0]} <puzzle.json> [output.graphml]")
        sys.exit(1)

    puzzle_path = Path(sys.argv[1])
    puzzle      = Puzzle.from_json(puzzle_path.read_text())

    out_path = (
        Path(sys.argv[2]) if len(sys.argv) >= 3
        else puzzle_path.with_suffix(".graphml")
    )

    print(f"Construint graf de '{puzzle_path.stem}'...")
    g = build_graph(puzzle)

    n_nodes = g.num_vertices()
    n_edges = g.num_edges()
    n_goals = int(g.vp["is_goal"].a.sum())
    print(f"Nodes: {n_nodes}, Arestes: {n_edges}, Estats finals: {n_goals}")

    g.save(str(out_path))
    print(f"Graf desat: {out_path}")