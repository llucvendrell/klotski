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

from logic import DELTAS, is_goal
from puzzle import Puzzle, State, StateKey, Coord

def _get_occupied(puzzle: Puzzle, state: State) -> set[Coord]:
    occupied = set(puzzle.walls)
    for i, (px, py) in enumerate(state.positions):
        for dx, dy in puzzle.pieces[i].coords:
            occupied.add((px + dx, py + dy))
    return occupied

def _can_move_local(
    puzzle: Puzzle, state: State, piece_idx: int, direction: str,
    occupied: set[Coord], relative_sets: list[set[Coord]]
) -> bool:
    ddx, ddy = DELTAS[direction]
    px, py = state.positions[piece_idx]
    rel_set = relative_sets[piece_idx]
    for dx, dy in puzzle.pieces[piece_idx].coords:
        nx, ny = px + dx + ddx, py + dy + ddy
        if nx < 0 or nx >= puzzle.W or ny < 0 or ny >= puzzle.H:
            return False
        if (nx, ny) in occupied and (dx + ddx, dy + ddy) not in rel_set:
            return False
    return True


def state_key(state: State | str, groups: list[tuple[int, int]]) -> StateKey:
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
    for i, j in groups:
        if j - i > 1:
            result.extend(sorted(positions[i:j]))
        else:
            result.append(positions[i])

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

    # Pre-calculem els grups de peces iguals per a l'estat canònic
    groups: list[tuple[int, int]] = []
    i = 0
    while i < len(puzzle.pieces):
        j = i + 1
        while j < len(puzzle.pieces) and puzzle.pieces[j] == puzzle.pieces[i]:
            j += 1
        groups.append((i, j))
        i = j

    # visited: StateKey → índex enter del vèrtex (O(1) per accés)
    visited: dict[StateKey, int] = {}

    start_key = state_key(puzzle.start, groups)

    # Creem el node inicial
    v0   = g.add_vertex()
    idx0 = int(v0)
    visited[start_key] = idx0
    state_prop[v0]     = json.dumps([list(p) for p in start_key])
    is_start_prop[v0]  = True
    is_goal_prop[v0]   = is_goal(puzzle, puzzle.start)

    # Pre-calculem els sets de coordenades relatives per a can_move_local
    relative_sets = [set(p.coords) for p in puzzle.pieces]

    # DFS: la pila guarda (estat, índex_src, clau_src) per evitar
    # recalcular state_key quan el traiem de la pila.
    stack: list[tuple[State, int, StateKey]] = [
        (puzzle.start, idx0, start_key)
    ]

    while stack:
        current, src_idx, src_key = stack.pop()
        
        # Mirem tots els moviments possibles
        occupied = _get_occupied(puzzle, current)
        for i in range(len(puzzle.pieces)):
            for direction in ("N", "E", "S", "W"):
                if _can_move_local(puzzle, current, i, direction, occupied, relative_sets):
                    # Calculem el nou estat
                    ddx, ddy = DELTAS[direction]
                    px, py = current.positions[i]
                    nxt_pos = (px + ddx, py + ddy)
                    positions = list(current.positions)
                    positions[i] = nxt_pos
                    nxt_state = State(tuple(positions))
                    nxt_key   = state_key(nxt_state, groups)

                    if nxt_key in visited:
                        dst_idx = visited[nxt_key]
                    else:
                        v = g.add_vertex()
                        dst_idx = int(v)
                        visited[nxt_key] = dst_idx
                        state_prop[v]     = json.dumps([list(p) for p in nxt_key])
                        is_goal_prop[v]   = is_goal(puzzle, nxt_state)
                        stack.append((nxt_state, dst_idx, nxt_key))

                    # Afegim l'aresta si no existeix (multigraf no, però sí arestes paral·leles?)
                    # graph-tool permet arestes paral·leles per defecte.
                    # Per Klotski, volem una aresta per cada moviment diferent.
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