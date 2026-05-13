"""
Construeix el graf d'estats d'un trencaclosques de peces lliscants d'una manera eficient.
Aquest script optimitza la creació del graf evitant arestes duplicades i 
accelerant la generació de la clau d'estat (canonicalització).

python src/graph_eficient.py puzzles/sample1.json



"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import graph_tool.all as gt  # type: ignore[import-untyped]

from logic import possible_moves, apply_move, is_goal
from puzzle import Puzzle, State

# Tipus per a la clau d'estat: posicions de les peces com a tupla
StateKey = tuple[tuple[int, int], ...]

def get_shape_groups(puzzle: Puzzle) -> list[list[int]]:
    """
    Pre-calcula quins índexs de peces tenen la mateixa forma.
    Això permet ordenar només les peces idèntiques durant la canonicalització.
    """
    groups = []
    if not puzzle.pieces:
        return groups
    
    current_group = [0]
    for i in range(1, len(puzzle.pieces)):
        if puzzle.pieces[i] == puzzle.pieces[i-1]:
            current_group.append(i)
        else:
            groups.append(current_group)
            current_group = [i]
    groups.append(current_group)
    return groups

def get_fast_state_key(state: State, groups: list[list[int]]) -> StateKey:
    """
    Genera una clau única (canònica) per a l'estat actual.
    Ordena les posicions de les peces dins de cada grup de formes idèntiques.
    """
    positions = list(state.positions)
    for group in groups:
        # Ordenem el subsegment de posicions que corresponen a peces iguals
        start_idx = group[0]
        end_idx = group[-1] + 1
        positions[start_idx:end_idx] = sorted(positions[start_idx:end_idx])
    return tuple(positions)

def build_graph(puzzle: Puzzle) -> gt.Graph:
    """
    Construeix el graf d'estats fent un DFS iteratiu.
    """
    g = gt.Graph(directed=False)

    # Propietats del graf i nodes
    state_prop = g.new_vertex_property("string")   # Posicions en format JSON
    is_start_prop = g.new_vertex_property("bool")  # Marca l'inici
    is_goal_prop = g.new_vertex_property("bool")   # Marca els finals
    
    # Grups de formes per a la canonicalització ràpida
    groups = get_shape_groups(puzzle)
    
    # Diccionari per evitar duplicar nodes: StateKey -> Vertex
    visited: dict[StateKey, gt.Vertex] = {}

    def add_node_to_graph(state: State, key: StateKey) -> gt.Vertex:
        v = g.add_vertex()
        # Guardem l'estat com a JSON string per a les eines de visualització
        state_prop[v] = json.dumps([list(p) for p in key])
        is_start_prop[v] = (state == puzzle.start)
        is_goal_prop[v] = is_goal(puzzle, state)
        visited[key] = v
        return v

    # DFS Iteratiu
    start_key = get_fast_state_key(puzzle.start, groups)
    v_start = add_node_to_graph(puzzle.start, start_key)
    
    stack: list[tuple[State, gt.Vertex]] = [(puzzle.start, v_start)]

    while stack:
        curr_state, curr_v = stack.pop()

        for move in possible_moves(puzzle, curr_state):
            next_state = apply_move(puzzle, curr_state, move)
            next_key = get_fast_state_key(next_state, groups)

            if next_key not in visited:
                # Creem node nou i aresta
                next_v = add_node_to_graph(next_state, next_key)
                g.add_edge(curr_v, next_v)
                stack.append((next_state, next_v))
            else:
                # El node ja existeix, comprovem si hem de posar l'aresta
                next_v = visited[next_key]
                # Només afegim l'aresta si no existeix prèviament entre aquests dos vèrtexs
                if g.edge(curr_v, next_v) is None:
                    g.add_edge(curr_v, next_v)

    # Assignem les propietats al graf
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
    try:
        puzzle = Puzzle.from_json(puzzle_path.read_text())
    except Exception as e:
        print(f"Error llegint el puzzle: {e}")
        sys.exit(1)

    out_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else puzzle_path.with_suffix(".graphml")

    print(f"Construint graf de '{puzzle_path.name}'...")
    graph = build_graph(puzzle)

    print(f"Nodes: {graph.num_vertices()}")
    print(f"Arestes: {graph.num_edges()}")
    
    # Comptar estats finals ràpidament
    n_goals = sum(1 for v in graph.vertices() if graph.vp["is_goal"][v])
    print(f"Estats finals trobats: {n_goals}")

    graph.save(str(out_path))
    print(f"Graf desat correctament a: {out_path}")