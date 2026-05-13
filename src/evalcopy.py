"""
Avalua un puzzle de peces lliscants i li assigna una puntuació d'interès (0–5 estrelles).
Versió ultra-eficient: extrau el camí directament del graf per evitar errors de lògica.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import graph_tool.all as gt  # type: ignore[import-untyped]

from puzzle import Puzzle

# ── Configuració i Pesos ─────────────────────────────────────────────────────

W_PATH, W_ENTROPY, W_MODULARITY, W_ECCENTRICITY, W_GOAL_DIFF = 0.30, 0.20, 0.20, 0.15, 0.15
REF_PATH_LEN, MIN_PATH_LEN = 35, 10
NEAR_GOAL_THRESHOLD = 5
MAX_PENALTY_TOTAL = 0.20

# ── Mesures d'Alta Eficiència ────────────────────────────────────────────────

def measure_path_length(path_len: int) -> float:
    if path_len <= 0: return 0.0
    base = min(math.log(path_len + 1) / math.log(REF_PATH_LEN + 1), 1.0)
    if path_len < MIN_PATH_LEN: base *= (path_len / MIN_PATH_LEN)
    return base

def measure_entropy_fast(g: gt.Graph) -> float:
    n = g.num_vertices()
    if n <= 1: return 0.0
    
    try:
        _, counts = gt.vertex_hist(g, "out")
        # Gestió robusta: si és numpy array o si és property map de graph-tool
        counts_data = counts.a if hasattr(counts, 'a') else counts
        counts_nonzero = counts_data[counts_data > 0]
        
        entropy = sum(-(c / n) * math.log2(c / n) for c in counts_nonzero)
        max_entropy = math.log2(n)
        return entropy / max_entropy if max_entropy > 0 else 0.0
    except Exception:
        return 0.5 # Valor neutre en cas d'error imprevist

def measure_modularity_fast(g: gt.Graph) -> float:
    try:
        # Louvain/Label propagation per a velocitat en grafs massius
        prop = gt.label_propagation(g)
        q = gt.modularity(g, prop)
        return float(max(0.0, min(q, 1.0)))
    except: return 0.2

def measure_eccentricity_fast(g: gt.Graph, dist_map_arr: gt.PropertyMap) -> float:
    finite_dists = dist_map_arr.a[dist_map_arr.a < 2**30]
    if len(finite_dists) == 0: return 0.0
    ecc_start = finite_dists.max()
    # pseudo_diameter és gairebé instantani
    diam, _ = gt.pseudo_diameter(g)
    return ecc_start / diam if diam > 0 else 0.0

def measure_goal_difficulty_fast(g: gt.Graph, goal_indices: list[int], dist_map_arr: gt.PropertyMap) -> float:
    if not goal_indices: return 0.0
    dists = dist_map_arr.a[goal_indices]
    valid_dists = dists[dists < 2**30]
    if len(valid_dists) == 0: return 0.0
    fractions = [min(d / REF_PATH_LEN, 1.0) for d in valid_dists]
    avg_fraction = sum(fractions) / len(fractions)
    scarcity = 1.0 / math.log2(len(goal_indices) + 1)
    return avg_fraction * scarcity

# ── Avaluació Global ──────────────────────────────────────────────────────────

def evaluate(puzzle: Puzzle, g: gt.Graph, verbose: bool = False) -> float:
    # 1. Identificació de nodes clau (Start i Goals)
    is_start_arr = g.vp["is_start"].a
    is_goal_arr = g.vp["is_goal"].a
    
    start_idx = int(is_start_arr.argmax())
    goal_indices = list(is_goal_arr.nonzero()[0])
    
    if not goal_indices:
        if verbose: print("No s'han trobat estats finals al graf.")
        return 0.0

    # 2. Càlcul de distàncies (UN SOL BFS/Dijkstra)
    # Això ens dóna la distància de l'inici a TOTS els nodes
    dist_map = gt.shortest_distance(g, source=g.vertex(start_idx))

    # 3. Reconstrucció del camí òptim (SENSE apply_move)
    # Trobem quin goal està més a prop segons el graf
    target_goal_idx = min(goal_indices, key=lambda idx: dist_map.a[idx])
    
    # Extraiem la llista de vèrtexs del camí més curt
    v_list, _ = gt.shortest_path(g, g.vertex(start_idx), g.vertex(target_goal_idx))
    path_vertices = [int(v) for v in v_list]
    path_len = len(path_vertices) - 1 if path_vertices else 0

    # 4. Mesures individuals
    m1 = measure_path_length(path_len)
    m2 = measure_entropy_fast(g)
    m3 = measure_modularity_fast(g)
    m4 = measure_eccentricity_fast(g, dist_map)
    m5 = measure_goal_difficulty_fast(g, goal_indices, dist_map)

    # --- 5. PENALITZACIONS ---
    # P2: Linealitat
    p2_val = 0.0
    if path_vertices:
        # Grau mitjà global vs grau mitjà del camí de la solució
        global_avg = float(g.get_out_degrees(g.get_vertices()).mean())
        path_avg = float(g.get_out_degrees(path_vertices).mean())
        if global_avg > 0:
            p2_val = 0.25 * max(0.0, 1.0 - (path_avg / global_avg))

    # P3: Goal proper (accidentalitat)
    # Busquem la distància mínima a qualsevol goal
    valid_goal_dists = dist_map.a[goal_indices]
    min_dist_val = float(valid_goal_dists[valid_goal_dists < 2**30].min()) if goal_indices else 999.0
    p3_val = 0.30 * (1.0 - min_dist_val/NEAR_GOAL_THRESHOLD) if min_dist_val < NEAR_GOAL_THRESHOLD else 0.0

    # --- 6. PUNTUACIÓ FINAL CORREGIDA ---
    # Sumem les mesures amb els seus pesos
    score_raw = float(W_PATH*m1 + W_ENTROPY*m2 + W_MODULARITY*m3 + W_ECCENTRICITY*m4 + W_GOAL_DIFF*m5)
    
    # Limitem el total de les penalitzacions perquè no "matin" el puzzle (màxim 0.20)
    total_penalty = min(p2_val + p3_val, 0.20)
    
    score_penalized = max(0.0, score_raw - total_penalty)
    
    # Escalat amb arrel quadrada: puja les notes mitjanes (0.5 -> 0.70 -> 3.5 estrelles)
    stars = round(math.sqrt(score_penalized) * 5.0, 2)

    # Seguretat: no passar de 5 ni baixar de 0
    stars = max(0.0, min(5.0, stars))

    if verbose:
        print(f"Mètrica Base (Raw): {score_raw:.3f}")
        print(f"Penalització Aplicada: {total_penalty:.3f}")
        print(f"Puntuació Final: {stars} ★")

    return stars

# ── Interfície de línia de comandes ───────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Avalua la qualitat estructural d'un puzzle.")
    parser.add_argument("puzzle_file", type=Path, help="Fitxer .json o .graphml")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if not args.puzzle_file.exists():
        print(f"Error: No s'ha trobat {args.puzzle_file}")
        sys.exit(1)

    # Si passem un .graphml, carreguem directament el graf (molt ràpid)
    if args.puzzle_file.suffix == ".graphml":
        g = gt.load_graph(str(args.puzzle_file))
        # Recuperem la definició del puzzle guardada dins del graf
        puzzle = Puzzle.from_json(g.gp["puzzle"])
    else:
        # Si passem un .json, hem de construir el graf primer
        from graph import build_graph
        puzzle = Puzzle.from_json(args.puzzle_file.read_text())
        print("Construint graf d'estats...")
        g = build_graph(puzzle)

    evaluate(puzzle, g, verbose=args.verbose)