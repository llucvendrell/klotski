"""
Construeix el graf d'estats d'un trencaclosques de peces lliscants.

Cada node representa una disposició de les peces, i cada aresta representa
un moviment vàlid d'una peça entre dues disposicions.

L'exploració es fa amb DFS des de l'estat inicial.

El graf es desa en format .graphml per poder-lo carregar amb altres eines.

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

# Clau d'estat: tupla de posicions de totes les peces, en ordre canònic.
# Usem directament State.positions (que ja és una tuple[Coord, ...]) com a clau
# del diccionari visited, evitant conversions innecessàries.
StateKey = tuple[tuple[int, int], ...]


def state_key(puzzle: Puzzle, state: State | str) -> StateKey:
    """
    Retorna la clau canònica d'un estat.

    Si l'estat és un string JSON (com el que desa graph-tool), el parseja.
    Si és un State, retorna directament les posicions.

    Nota sobre peces iguals: dues peces amb la mateixa forma però diferent
    posició tenen índexos fixos (definits en la canonicalització del puzzle),
    de manera que intercanviar-les dóna claus diferents. No cal cap tractament
    especial: la identitat de cada peça és el seu índex.
    """
    if isinstance(state, str):
        return tuple(tuple(p) for p in json.loads(state))
    return state.positions


def build_graph(puzzle: Puzzle) -> gt.Graph:
    """
    Construeix el graf d'estats del puzzle mitjançant DFS iteratiu.

    Optimitzacions respecte la versió original:
    - Les arestes duplicades s'eviten consultant `visited` abans d'afegir-les.
      En la versió original, sempre s'afegia l'aresta, fins i tot entre nodes
      ja connectats, generant múltiples arestes paral·leles que inflaven el
      graf i alentien qualsevol algorisme posterior.
    - `visited` mapeja StateKey → int (índex de vèrtex) en comptes de
      StateKey → gt.Vertex. Accedir per índex enter és més ràpid que
      mantenir referències a objectes Vertex de graph-tool.
    - Les propietats dels nodes es desen en arrays de Python i es bolquen
      al graf al final, evitant crides repetides a graph-tool per node.
    - `possible_moves` ja retorna moviments d'un sol pas; apliquem cada
      moviment una sola vegada sense recalcular l'estat de la peça.

    Retorna un graf no dirigit amb:
    - vp['state']   : posicions de cada node (JSON)
    - vp['is_start']: True si és l'estat inicial
    - vp['is_goal'] : True si és un estat final
    - gp['puzzle']  : JSON del puzzle (metadada del graf)
    """
    g = gt.Graph(directed=False)

    # Reservem les propietats abans de poblar el graf
    state_prop    = g.new_vertex_property("string")
    is_start_prop = g.new_vertex_property("bool")
    is_goal_prop  = g.new_vertex_property("bool")

    # visited: StateKey → índex enter del vèrtex (més ràpid que gt.Vertex)
    visited: dict[StateKey, int] = {}

    def get_or_create(state: State) -> tuple[int, bool]:
        """
        Retorna (índex, és_nou) del vèrtex corresponent a state.
        Si no existeix, crea el vèrtex i omple les seves propietats.
        """
        key = state.positions  # evitem cridar state_key: ja és una tupla
        if key in visited:
            return visited[key], False

        v = g.add_vertex()
        idx = int(v)
        visited[key] = idx

        state_prop[v]    = json.dumps([list(p) for p in state.positions])
        is_start_prop[v] = state == puzzle.start
        is_goal_prop[v]  = is_goal(puzzle, state)

        return idx, True

    # ── DFS iteratiu ──────────────────────────────────────────────────
    # La pila conté estats pendents d'explorar.
    # Creem el node inicial abans d'entrar al bucle.
    get_or_create(puzzle.start)
    stack: list[State] = [puzzle.start]

    while stack:
        current = stack.pop()
        src_idx = visited[current.positions]

        for move in possible_moves(puzzle, current):
            nxt = apply_move(puzzle, current, move)
            dst_idx, is_new = get_or_create(nxt)

            # Afegim l'aresta només si no existia encara.
            # Com que el graf és no dirigit i recorrem tots els veïns
            # dels dos costats, sense aquesta guarda cada aresta
            # s'afegiria dues vegades (una per cada sentit).
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
    puzzle = Puzzle.from_json(puzzle_path.read_text())

    out_path = (
        Path(sys.argv[2]) if len(sys.argv) >= 3
        else puzzle_path.with_suffix(".graphml")
    )

    print(f"Construint graf de '{puzzle_path.stem}'...")
    g = build_graph(puzzle)

    n_nodes = g.num_vertices()
    n_edges = g.num_edges()
    n_goals = sum(1 for v in g.vertices() if g.vp["is_goal"][v])
    print(f"Nodes: {n_nodes}, Arestes: {n_edges}, Estats finals: {n_goals}")

    g.save(str(out_path))
    print(f"Graf desat: {out_path}")