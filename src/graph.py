"""
Construeix el graf d'estats d'un trencaclosques de peces lliscants.
 
Cada node representa una disposició de les peces, i cada aresta representa
un moviment vàlid d'una peça entre dues disposicions.
 
L'exploració es fa amb DFS des de l'estat inicial.
 
El graf es desa en format .graphml per poder-lo carregar amb altres eines.
 
Ús:
    pixi run python src/graph.py puzzles/sample1.json (genera el .graphml de sample1.json)
    pixi run python src/3D_view.py puzzles/sample1.graphml (visualitzar el graf de sample1)
"""
 
from __future__ import annotations
 
import json
import sys
from pathlib import Path
 
import graph_tool.all as gt  # type: ignore[import-untyped]
 
from logic import possible_moves, apply_move, is_goal
from puzzle import Puzzle, State
 
# Tipus per a la clau d'estat: la tupla de posicions de totes les peces
StateKey = tuple[tuple[int, int], ...]
 
 
def state_key(puzzle: Puzzle, state: State) -> StateKey:
    """ Agrupa les peces per forma i ordena les posicions dins de cada grup. """
    positions = list(state.positions)
    result = []
    i = 0
    while i < len(puzzle.pieces):
        j = i + 1
        while j < len(puzzle.pieces) and puzzle.pieces[j] == puzzle.pieces[i]:
            j += 1
        # Les peces i..j-1 tenen la mateixa forma, ordenem les seves posicions
        group = sorted(positions[i:j])
        result.extend(group)
        i = j
    return tuple(result)
 
def build_graph(puzzle: Puzzle) -> gt.Graph:
    """
    Construeix el graf d'estats del puzzle mitjançant DFS.
 
    Retorna un graf no dirigit amb les següents propietats:
    - 'state': la llista de posicions de cada node (en JSON)
    - 'is_start': True si el node és l'estat inicial
    - 'is_goal': True si el node és un estat final
    - 'puzzle': el JSON del puzzle (propietat del graf)
    """
    g = gt.Graph(directed=False)
 
    # Propietats dels nodes
    state_prop = g.new_vertex_property("string")   # estat en JSON
    is_start_prop = g.new_vertex_property("bool")  # és l'estat inicial?
    is_goal_prop = g.new_vertex_property("bool")   # és un estat final?
 
    # Mapatge: clau d'estat → vèrtex del graf
    visited: dict[StateKey, gt.Vertex] = {}
 
    def get_or_create_vertex(state: State) -> tuple[gt.Vertex, bool]:
        """Retorna el vèrtex corresponent a l'estat, creant-lo si cal."""
        key = state_key(puzzle, state)
        if key in visited:
            return visited[key], False
        v = g.add_vertex()
        state_prop[v] = json.dumps([list(p) for p in state.positions])
        is_start_prop[v] = (state == puzzle.start)
        is_goal_prop[v] = is_goal(puzzle, state)
        visited[key] = v
        return v, True
 
    # DFS iteratiu des de l'estat inicial
    stack: list[State] = [puzzle.start]
    get_or_create_vertex(puzzle.start)
    i = 1
    while stack:
        print(i)
        i += 1
        current_state = stack.pop()
        current_v = visited[state_key(puzzle, current_state)]
 
        for move in possible_moves(puzzle, current_state):
            next_state = apply_move(puzzle, current_state, move)
            next_v, is_new = get_or_create_vertex(next_state)
 
            # Afegim l'aresta si no existeix ja
            if g.edge(current_v, next_v) is None:
                g.add_edge(current_v, next_v)
 
            # Si l'estat és nou, l'afegim a la pila per explorar-lo
            if is_new:
                stack.append(next_state)
 
    # Desem les propietats al graf
    g.vp["state"] = state_prop
    g.vp["is_start"] = is_start_prop
    g.vp["is_goal"] = is_goal_prop
    g.gp["puzzle"] = g.new_graph_property("string", puzzle.to_json())
 
    return g
 
 
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Ús: python {sys.argv[0]} <puzzle.json> [output.graphml]")
        sys.exit(1)
 
    puzzle_path = Path(sys.argv[1])
    puzzle = Puzzle.from_json(puzzle_path.read_text())
 
    # Nom del fitxer de sortida
    out_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else puzzle_path.with_suffix(".graphml")
 
    print(f"Construint graf de '{puzzle_path.stem}'...")
    g = build_graph(puzzle)
 
    n_nodes = g.num_vertices()
    n_edges = g.num_edges()
    n_goals = sum(1 for v in g.vertices() if g.vp["is_goal"][v])
    print(f"Nodes: {n_nodes}, Arestes: {n_edges}, Estats finals: {n_goals}")
 
    g.save(str(out_path))
    print(f"Graf desat: {out_path}")