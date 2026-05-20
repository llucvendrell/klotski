"""
Construeix el graf d'estats d'un trencaclosques de peces lliscants.

Cada node representa una disposició de les peces, i cada aresta representa
un moviment vàlid d'una peça entre dues disposicions.

L'exploració es fa amb DFS des de l'estat inicial.

El graf es desa en format .graphml per poder-lo carregar amb altres eines.

Millora respecte la versió anterior: state_key agrupa peces amb la mateixa
forma i ordena les seves posicions dins de cada grup. Això fa que dos estats
on s'han intercanviat peces iguals es considerin el MATEIX node, reduint
significativament la mida del graf quan hi ha peces repetides.

Exemple: si hi ha dues peces iguals a les posicions (1,0) i (3,2),
intercanviar-les dona el mateix estat canònic → el graf és més petit.

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

# Clau d'estat: tupla de posicions canòniques de totes les peces.
StateKey = tuple[tuple[int, int], ...]


def state_key(puzzle: Puzzle, state: State | str) -> StateKey:
    """
    Retorna la clau canònica d'un estat.

    Si l'estat és un string JSON (com el que desa graph-tool), el parseja.
    Si és un State, usa directament les posicions.

    Millora clau: peces amb la mateixa forma es consideren intercanviables.
    Les seves posicions s'ordenen dins de cada grup, de manera que dos
    estats que difereixen només en l'intercanvi de peces iguals tenen
    la mateixa clau → mateix node al graf → graf més petit i ràpid.

    Exemple:
        Peces [A, A, B] a posicions [(3,2), (1,0), (0,1)]
        Grup A: ordena [(3,2),(1,0)] → [(1,0),(3,2)]
        Clau: ((1,0),(3,2),(0,1))   ← independent de l'ordre de les A
    """
    if isinstance(state, str):
        positions: list[tuple[int, int]] = [tuple(p) for p in json.loads(state)]
    else:
        positions = list(state.positions)

    result: list[tuple[int, int]] = []
    i = 0
    while i < len(puzzle.pieces):
        # Troba el final del grup de peces amb la mateixa forma
        j = i + 1
        while j < len(puzzle.pieces) and puzzle.pieces[j] == puzzle.pieces[i]:
            j += 1
        # Ordena les posicions dins del grup (peces intercanviables)
        result.extend(sorted(positions[i:j]))
        i = j

    return tuple(result)


def build_graph(puzzle: Puzzle) -> gt.Graph:
    """
    Construeix el graf d'estats del puzzle mitjançant DFS iteratiu.

    Optimitzacions:
    - state_key agrupa peces iguals: el graf pot ser molt més petit quan
      hi ha peces repetides (menys nodes → menys temps i memòria).
    - visited mapeja StateKey → int: accés O(1) sense overhead de gt.Vertex.
    - if src_idx < dst_idx: evita arestes duplicades (cada aresta s'afegeix
      exactament una vegada, eliminant el bug del graph_eficient original).
    - Les propietats es desen al graf únicament al final, en bloc.

    Retorna un graf no dirigit amb:
    - vp['state']   : posicions de cada node (JSON)
    - vp['is_start']: True si és l'estat inicial
    - vp['is_goal'] : True si és un estat final
    - gp['puzzle']  : JSON del puzzle (metadada del graf)
    """
    g = gt.Graph(directed=False)

    state_prop    = g.new_vertex_property("string")
    is_start_prop = g.new_vertex_property("bool")
    is_goal_prop  = g.new_vertex_property("bool")

    # visited: StateKey canònica → índex enter del vèrtex
    visited: dict[StateKey, int] = {}

    # Clau de l'estat inicial (per marcar is_start correctament)
    start_key = state_key(puzzle, puzzle.start)

    def get_or_create(state: State) -> tuple[int, bool]:
        """
        Retorna (índex, és_nou) del vèrtex corresponent a state.
        Usa la clau canònica amb grups de peces iguals.
        """
        key = state_key(puzzle, state)
        if key in visited:
            return visited[key], False

        v   = g.add_vertex()
        idx = int(v)
        visited[key] = idx

        # Desem les posicions en l'ordre de la clau canònica
        state_prop[v]    = json.dumps([list(p) for p in key])
        is_start_prop[v] = (key == start_key)
        is_goal_prop[v]  = is_goal(puzzle, state)

        return idx, True

    # ── DFS iteratiu ──────────────────────────────────────────────────
    get_or_create(puzzle.start)
    stack: list[State] = [puzzle.start]

    while stack:
        current = stack.pop()
        src_idx = visited[state_key(puzzle, current)]

        for move in possible_moves(puzzle, current):
            nxt     = apply_move(puzzle, current, move)
            dst_idx, is_new = get_or_create(nxt)

            # Afegim l'aresta exactament una vegada (sense duplicats).
            # La guarda src < dst garanteix que cada parell (A,B) s'afegeix
            # una sola vegada independentment de l'ordre en que es visiten.
            if src_idx < dst_idx:
                g.add_edge(src_idx, dst_idx)

            if is_new:
                stack.append(nxt)

    # ── Desem propietats al graf ──────────────────────────────────────
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