"""
Generador de puzzles ultra-optimitzat per a 4★ i 5★.
Garanteix l'ordre canònic correcte combinant peces i posicions d'inici.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import deque, Counter
from pathlib import Path

# ── Configuració de Peces d'Alta Dificultat ───────────────────────────────────

POLYOMINOES = [
    [[0, 0]],
    [[0, 0], [0, 1]], [[0, 0], [1, 0]],
    [[0, 0], [0, 1], [0, 2]], [[0, 0], [1, 0], [2, 0]],
    [[0, 0], [0, 1], [1, 1]], [[0, 0], [1, 0], [1, 1]],
    [[0, 0], [0, 1], [0, 2], [1, 2]], [[0, 0], [1, 0], [2, 0], [2, 1]]
]

BOARD_SIZES = [(5, 5), (5, 6), (6, 5), (6, 6)]
PIECE_COUNTS = [6, 7, 8]

BFS_NODE_LIMIT = 250_000

# ── Lògica de Moviment Interna ────────────────────────────────────────────────

def get_piece_cells(coords: list[list[int]], pos: tuple[int, int]) -> set[tuple[int, int]]:
    return {(pos[0] + c[0], pos[1] + c[1]) for c in coords}

def is_valid_placement(coords: list[list[int]], pos: tuple[int, int], W: int, H: int, occupied: set[tuple[int, int]]) -> bool:
    for cx, cy in coords:
        x, y = pos[0] + cx, pos[1] + cy
        if not (0 <= x < W and 0 <= y < H) or (x, y) in occupied:
            return False
    return True

def generate_valid_goal_layout(W: int, H: int, n_pieces: int):
    occupied = set()
    pieces_coords = []
    positions = []
    
    for _ in range(n_pieces):
        placed = False
        for _ in range(50):
            coords = random.choice(POLYOMINOES)
            pos = (random.randint(0, W - 1), random.randint(0, H - 1))
            if is_valid_placement(coords, pos, W, H, occupied):
                pieces_coords.append(coords)
                positions.append(pos)
                occupied |= get_piece_cells(coords, pos)
                placed = True
                break
        if not placed:
            return None
            
    if len(occupied) / (W * H) < 0.60:
        return None
        
    return pieces_coords, positions

def get_allowed_moves(W: int, H: int, pieces_coords: list[list[list[int]]], current_positions: tuple[tuple[int, int], ...]) -> list[tuple[int, tuple[int, int]]]:
    moves = []
    occupied = {}
    for i, pos in enumerate(current_positions):
        for cx, cy in pieces_coords[i]:
            occupied[(pos[0] + cx, pos[1] + cy)] = i

    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    
    for i, pos in enumerate(current_positions):
        for dx, dy in directions:
            nx, ny = pos[0] + dx, pos[1] + dy
            
            possible = True
            for cx, cy in pieces_coords[i]:
                tx, ty = nx + cx, ny + cy
                if not (0 <= tx < W and 0 <= ty < H):
                    possible = False
                    break
                idx = occupied.get((tx, ty))
                if idx is not None and idx != i:
                    possible = False
                    break
            
            if possible:
                moves.append((i, (nx, ny)))
    return moves

# ── BFS Invers ────────────────────────────────────────────────────────────────

def inverse_bfs_and_evaluate(W: int, H: int, pieces: list[list[list[int]]], goal_positions: list[tuple[int, int]], goal_idx: int):
    start_tuple = tuple(goal_positions)
    visited = {start_tuple: (0, None)}
    queue = deque([start_tuple])
    
    out_degrees = {}
    n_edges = 0
    max_dist = -1
    furthest_state = start_tuple

    while queue:
        curr = queue.popleft()
        curr_dist, _ = visited[curr]
        
        moves = get_allowed_moves(W, H, pieces, curr)
        out_degrees[curr] = len(moves)
        
        if curr_dist > max_dist:
            max_dist = curr_dist
            furthest_state = curr

        for p_idx, nxt_pos in moves:
            n_edges += 1
            nxt_list = list(curr)
            nxt_list[p_idx] = nxt_pos
            nxt_tuple = tuple(nxt_list)
            
            if nxt_tuple not in visited:
                if len(visited) >= BFS_NODE_LIMIT:
                    return None
                visited[nxt_tuple] = (curr_dist + 1, curr)
                queue.append(nxt_tuple)

    if max_dist < 25:
        return 0, furthest_state, len(visited), max_dist

    path_degrees = []
    curr_path = furthest_state
    while curr_path is not None:
        path_degrees.append(out_degrees.get(curr_path, 0))
        _, curr_path = visited[curr_path]

    n_nodes = len(visited)
    n_edges_normalized = n_edges // 2
    
    target_pos = goal_positions[goal_idx]
    n_goals = sum(1 for state in visited if state[goal_idx] == target_pos)

    # Fórmules reals de eval.py
    m1 = 1.0 / (1.0 + math.exp(-0.10 * (max_dist - 15.0)))
    density = n_edges_normalized / n_nodes if n_nodes > 0 else 0
    m2 = min((math.log2(n_nodes) * density) / 75.0, 1.0) if n_nodes > 1 else 0.0

    if len(path_degrees) >= 2:
        mean_deg = sum(path_degrees) / len(path_degrees)
        variance = sum((x - mean_deg) ** 2 for x in path_degrees) / len(path_degrees) if mean_deg > 0 else 0
        m3 = min(math.sqrt(variance) / mean_deg, 1.0) if mean_deg > 0 else 0.0
    else:
        m3 = 0.0

    ratio = n_goals / n_nodes if n_nodes > 0 else 1.0
    m4 = math.exp(-5.0 * ratio)

    score = (0.45 * m1) + (0.25 * m2) + (0.20 * m3) + (0.10 * m4)

    if max_dist < 10: score -= 0.25 * (1.0 - max_dist / 10.0)
    if n_nodes < 100: score -= 0.20 * (1.0 - n_nodes / 100.0)
    if ratio > 0.30:  score -= 0.15 * min((ratio - 0.30) / 0.70, 1.0)

    stars = max(1, min(5, round(max(0.0, score) * 5.0)))
    
    return stars, furthest_state, n_nodes, max_dist

# ── Generador principal amb normalització canònica de Puzzle ──────────────────

def run_generator(min_stars: int, total_to_save: int, output_dir: Path):
    output_dir.mkdir(exist_ok=True)
    saved = 0
    attempts = 0
    discarded_layouts = 0
    
    star_dist: Counter[int] = Counter()
    last_max_dist = 0
    last_nodes = 0

    print(f"🚀 Iniciant cerca profunda canònica. Buscant {total_to_save} puzzles de >= {min_stars}★...")

    while saved < total_to_save:
        attempts += 1
        
        W, H = random.choice(BOARD_SIZES)
        n_pieces = random.choice(PIECE_COUNTS)
        
        layout = generate_valid_goal_layout(W, H, n_pieces)
        if layout is None:
            discarded_layouts += 1
            continue
            
        pieces, goal_positions = layout
        goal_idx = 0  # Peça objectiu inicial
        
        # Guardem dades per identificar-la després de l'ordenació canònica
        target_piece_shape = pieces[goal_idx]
        target_goal_pos = goal_positions[goal_idx]
        
        res = inverse_bfs_and_evaluate(W, H, pieces, goal_positions, goal_idx)
        if res is None:
            continue
            
        stars, start_state, nodes, path_len = res
        
        if path_len > 0:
            last_max_dist = path_len
            last_nodes = nodes
        if stars > 0:
            star_dist[stars] += 1

        sys.stdout.write(
            f"\r[Intents: {attempts}] [Geometria Rebutjada: {discarded_layouts}] "
            f"[Últim camí: {last_max_dist}m / {last_nodes}n] "
            f"[Trobats: { {k: star_dist[k] for k in sorted(star_dist) if k >= 3} }]"
        )
        sys.stdout.flush()
        
        if stars >= min_stars:
            # ── CANÒNICA ESTRICTA (IGUAL QUE CRIDA PUZZLE.PY) ──────────────────
            # L'ordre canònic del projecte demana ordenar les tuples (peça, posicio_inicial).
            # Això evita que desquadrin les dimensions.
            start_list = [list(pos) for pos in start_state]
            
            # Creem blocs complets per ordenar-los en conjunt
            items_to_sort = []
            for i in range(len(pieces)):
                items_to_sort.append({
                    "piece": pieces[i],
                    "start_pos": start_list[i]
                })
            
            # Ordenem exactament per la forma de la peça, i si empaten, per la posició d'inici
            items_sorted = sorted(items_to_sort, key=lambda x: (x["piece"], x["start_pos"]))
            
            # Extraiem les llistes finals ordenades canònicament
            pieces_canonical = [x["piece"] for x in items_sorted]
            start_canonical = [x["start_pos"] for x in items_sorted]
            
            # Retrobem on ha anat a parar la nostra peça objectiu (Goal)
            # El seu comportament s'ha de mantenir vinculat a la forma original
            new_goal_idx = -1
            for idx, item in enumerate(items_sorted):
                if item["piece"] == target_piece_shape:
                    new_goal_idx = idx
                    break
                    
            # Si per algun motiu hi ha formes idèntiques i empaten, ens assegurem un index vàlid
            if new_goal_idx == -1:
                new_goal_idx = 0
            
            # Construcció del JSON de sortida exacte sol·licitat
            puzzle_json = {
                "W": W,
                "H": H,
                "walls": [],
                "pieces": pieces_canonical,
                "start": start_canonical,
                "goals": [{"i": new_goal_idx, "pos": list(target_goal_pos)}]
            }
            
            file_name = f"puzzle_{stars}stars_{path_len}mov_{random.randint(1000,9999)}.json"
            file_path = output_dir / file_name
            file_path.write_text(json.dumps(puzzle_json))
            saved += 1
            
            print("\n" + "─" * 70)
            print(f"✨ 🎉 ¡TROBAT PUZZLE CANÒNIC DE {stars} ESTRELLES!")
            print(f" 📂 Fitxer: {file_path}")
            print(f" 📏 Longitud de camí real: {path_len} moviments")
            print(f" 🖧  Mida de l'espai d'estats (nodes): {nodes}")
            print("─" * 70 + "\n")
            
            attempts = 0
            discarded_layouts = 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", type=int, default=1, help="Puzzles a generar")
    parser.add_argument("--min-stars", type=int, default=4, choices=[3, 4, 5])
    parser.add_argument("--output", type=Path, default=Path("puzzles"))
    args = parser.parse_args()
    
    run_generator(args.min_stars, args.n, args.output)