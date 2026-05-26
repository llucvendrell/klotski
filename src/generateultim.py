"""
Genera puzzles de peces lliscants amb BFS invers intel·ligent.

Basat en el codi del company (que funcionava) amb millores mínimes:
  - M3 real (coeficient de variació) en comptes d'aproximació
  - Comptatge de goals dins del BFS (sense passada extra)
  - Sortida més clara

Ús:
    python src/generateultim.py                        # busca puzzles de 4.3★+
    python src/generateultim.py --min-stars 3.0        # busca puzzles de 3.0★+
    python src/generateultim.py --min-stars 4.0 -n 3  # busca 3 puzzles de 4.0★+
    python src/generateultim.py --output my_puzzles/
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import deque
from pathlib import Path

from graph_eficientcopybo import state_key
from puzzle import Puzzle, State

# ── Configuració ──────────────────────────────────────────────────────────────

POLYOMINOES = [
    [[0, 0]],
    [[0, 0], [0, 1]], [[0, 0], [1, 0]],
    [[0, 0], [0, 1], [0, 2]], [[0, 0], [1, 0], [2, 0]],
    [[0, 0], [0, 1], [1, 1]], [[0, 0], [1, 0], [1, 1]],
    [[0, 0], [0, 1], [0, 2], [1, 2]],
    [[0, 0], [1, 0], [2, 0], [2, 1]],
    [[0, 0], [1, 0], [0, 1], [1, 1]],
]

BOARD_SIZES  = [(5, 6), (6, 5), (6, 6), (5, 5)]
BOARD_WEIGHTS = [0.30,   0.30,   0.20,   0.20 ]

PIECE_COUNTS  = [6,    7,    8   ]
PIECE_WEIGHTS = [0.35, 0.40, 0.25]

BFS_NODE_LIMIT = 3_000_000

DEFAULT_MIN_STARS = 4.3
DEFAULT_MAX_STARS = 5.0
DEFAULT_OUTPUT    = Path("puzzles")


# ── Lògica de moviments ───────────────────────────────────────────────────────


def get_moves(
    W: int, H: int,
    pieces: list[list[list[int]]],
    state: tuple,
    walls: set[tuple[int, int]],
) -> list[tuple[int, tuple[int, int]]]:
    occupied: dict[tuple[int, int], int] = {w: -1 for w in walls}
    for i, pos in enumerate(state):
        for cx, cy in pieces[i]:
            occupied[(pos[0] + cx, pos[1] + cy)] = i

    moves = []
    for i, pos in enumerate(state):
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = pos[0] + dx, pos[1] + dy
            valid = True
            for cx, cy in pieces[i]:
                tx, ty = nx + cx, ny + cy
                if not (0 <= tx < W and 0 <= ty < H):
                    valid = False
                    break
                nb = occupied.get((tx, ty))
                if nb is not None and nb != i:
                    valid = False
                    break
            if valid:
                moves.append((i, (nx, ny)))
    return moves


# ── BFS invers ────────────────────────────────────────────────────────────────


# Distància mínima necessària per a cada llindar d'estrelles.
# Permet descartar BFS primerenc si veiem que no hi ha cap camí prou llarg.
# Calculat a partir de la sigmoide inversa: si volem X★, necessitem path_len Y.
_MIN_PATH_FOR_STARS = {1: 0, 2: 8, 3: 15, 4: 25, 5: 40}


def inverse_bfs(
    W: int, H: int,
    pieces: list[list[list[int]]],
    goal_positions: list[tuple[int, int]],
    goal_idx: int,
    walls: set[tuple[int, int]],
    groups: list[tuple[int, int]],
    min_path: int = 0,
) -> dict | None:
    """
    BFS invers des del goal: explora tots els estats accessibles.
    Retorna estadístiques per avaluar el puzzle, o None si és massa gran.
    """
    start_positions = tuple(goal_positions)
    goal_pos = goal_positions[goal_idx]
    
    # Usem State object per poder fer servir state_key
    start_state = State(start_positions)
    start_key   = state_key(start_state, groups)

    visited: dict[tuple, tuple[int, State | None, tuple]] = {start_key: (0, None, start_positions)}
    queue: deque[tuple[State, tuple]] = deque([(start_state, start_key)])

    out_degrees: dict[tuple, int] = {}
    n_edges   = 0
    early_check = max(500, BFS_NODE_LIMIT // 200)

    while queue:
        curr_state, curr_key = queue.popleft()
        curr_dist = visited[curr_key][0]
        
        # moves retorna (peça_idx, nova_posicio)
        moves = get_moves(W, H, pieces, curr_state.positions, walls)
        out_degrees[curr_key] = len(moves)

        if min_path > 0 and len(visited) == early_check:
            # Aproximació: si en early_check encara estem molt lluny del min_path, descartem
            if curr_dist < min_path // 3:
                return None

        for p_idx, nxt_pos in moves:
            n_edges += 1
            nxt_positions_list = list(curr_state.positions)
            nxt_positions_list[p_idx] = nxt_pos
            nxt_state = State(tuple(nxt_positions_list))
            nxt_key   = state_key(nxt_state, groups)

            if nxt_key not in visited:
                if len(visited) >= BFS_NODE_LIMIT:
                    return None
                visited[nxt_key] = (curr_dist + 1, curr_state, nxt_state.positions)
                queue.append((nxt_state, nxt_key))

    # ── Segona passada: Multi-source BFS per trobar la distància REALS ────────
    # Això garanteix que path_len sigui el camí mínim a QUALSEVOL goal.
    
    goal_keys = []
    # Busquem el grup de peces iguals a goal_idx
    target_group = None
    for start, end in groups:
        if start <= goal_idx < end:
            target_group = (start, end)
            break
    
    for k in visited:
        if target_group and goal_pos in k[target_group[0]:target_group[1]]:
            goal_keys.append(k)
    
    # BFS multi-source
    # Per anar ràpid sense guardar tot el graf, podem usar el 'visited' de la 
    # primera passada per saber quins estats existeixen, però necessitem
    # les arestes. Per sort, Klotski és reversible.
    # Re-explorem des dels goals:
    
    true_dists: dict[tuple, int] = {k: 0 for k in goal_keys}
    q_multi = deque(goal_keys)
    max_dist  = 0
    best_key  = goal_keys[0] if goal_keys else start_key
    
    while q_multi:
        curr_key = q_multi.popleft()
        d = true_dists[curr_key]
        if d > max_dist:
            max_dist = d
            best_key  = curr_key
            
        # Per trobar veïns, hem de fer get_moves. 
        # Com que ja coneixem els estats vàlids (estan a visited), 
        # només explorem veïns que estiguin a visited.
        curr_positions = list(visited[curr_key][2]) # Guardarem la posició al visited
        moves = get_moves(W, H, pieces, curr_positions, walls)
        for p_idx, nxt_pos in moves:
            nxt_positions_list = list(curr_positions)
            nxt_positions_list[p_idx] = nxt_pos
            nxt_state = State(tuple(nxt_positions_list))
            nxt_key   = state_key(nxt_state, groups)
            
            if nxt_key in visited and nxt_key not in true_dists:
                true_dists[nxt_key] = d + 1
                q_multi.append(nxt_key)

    # Reconstruïm el millor estat i el seu camí
    best_state_positions = visited[best_key][2]
    
    # Reconstruïm path_degrees (una passda per al millor camí)
    path_degrees = []
    curr = best_key
    while true_dists[curr] > 0:
        path_degrees.append(out_degrees.get(curr, 0))
        # Busquem quin veí té distància d-1
        d = true_dists[curr]
        found_parent = False
        curr_positions = list(visited[curr][2])
        moves = get_moves(W, H, pieces, curr_positions, walls)
        for p_idx, nxt_pos in moves:
            nxt_positions_list = list(curr_positions)
            nxt_positions_list[p_idx] = nxt_pos
            nxt_state = State(tuple(nxt_positions_list))
            nk = state_key(nxt_state, groups)
            if nk in true_dists and true_dists[nk] == d - 1:
                curr = nk
                found_parent = True
                break
        if not found_parent: break
    path_degrees.append(out_degrees.get(curr, 0)) # afegim el goal

    # Comptem dead-ends (grau 1)
    n_dead = sum(1 for d in out_degrees.values() if d == 1)
    # Bottlenecks: nodes al camí amb grau 2
    n_bottles = sum(1 for d in path_degrees if d == 2)
    # El BFS actual ja troba tots els estats. Simplement re-analitzarem les distàncies.
    
    return {
        "start_state" : best_state_positions,
        "path_len"    : max_dist,
        "n_nodes"     : len(visited),
        "n_edges"     : n_edges // 2,
        "n_goals"     : len(goal_keys),
        "path_degrees": path_degrees,
        "n_dead"      : n_dead,
        "n_bottles"   : n_bottles,
    }


# ── Avaluació (mateixes fórmules que eval.py) ─────────────────────────────────


def evaluate_stats(stats: dict) -> float:
    """Retorna la puntuació decimal [0, 5] amb les fórmules actualitzades de evaloptimitzatbo.py."""
    path_len = stats["path_len"]
    n_nodes  = stats["n_nodes"]
    n_edges  = stats["n_edges"]
    n_goals  = stats["n_goals"]
    degs     = stats["path_degrees"]
    n_dead   = stats["n_dead"]
    n_bottles = stats["n_bottles"]

    # M1: sigmoide
    m1 = 1.0 / (1.0 + math.exp(-0.10 * (path_len - 15.0)))

    # M2: complexitat
    if n_nodes > 1:
        density = n_edges / n_nodes
        m2 = min(math.log2(n_nodes) * density / 75.0, 1.0)
    else:
        m2 = 0.0

    # M3: varietat
    if len(degs) >= 2:
        mean = sum(degs) / len(degs)
        if mean > 0:
            std = math.sqrt(sum((x - mean) ** 2 for x in degs) / len(degs))
            m3  = min(std / mean, 1.0)
        else:
            m3 = 0.0
    else:
        m3 = 0.0

    # M4: escassetat goals
    ratio = n_goals / n_nodes if n_nodes > 0 else 1.0
    m4    = math.exp(-5.0 * ratio)

    # M5: dead-ends
    m5 = min((n_dead / n_nodes) / 0.20, 1.0) if n_nodes > 0 else 0.0

    # M6: bottlenecks
    bottle_ratio = n_bottles / len(degs) if degs else 0.0
    m6 = math.exp(-15.0 * (bottle_ratio - 0.2) ** 2)

    score = 0.35*m1 + 0.20*m2 + 0.15*m3 + 0.10*m4 + 0.10*m5 + 0.10*m6

    # Penalitzacions
    if path_len < 10:
        score -= 0.25 * (1.0 - path_len / 10.0)
    if n_nodes < 100:
        score -= 0.20 * (1.0 - n_nodes / 100.0)
    if ratio > 0.30:
        score -= 0.15 * min((ratio - 0.30) / 0.70, 1.0)

    return max(0.0, score) * 5.0


# ── Col·locació de peces ──────────────────────────────────────────────────────


def place_pieces(
    W: int, H: int, n: int,
) -> tuple[list[list[list[int]]], list[tuple[int, int]], set[tuple[int, int]]] | None:
    occupied: set[tuple[int, int]] = set()
    walls:     set[tuple[int, int]] = set()
    pieces:    list[list[list[int]]] = []
    positions: list[tuple[int, int]] = []

    # Generem unes quantes parets aleatòries (fins a un 5-10% del taulell)
    n_walls = random.randint(0, (W * H) // 10)
    for _ in range(100):
        if len(walls) >= n_walls: break
        w = (random.randint(0, W - 1), random.randint(0, H - 1))
        walls.add(w)
    occupied |= walls

    for i in range(n):
        placed = False
        # Clustering: per a cada peça nova, busquem posicions prop de peces ja col·locades
        # però amb certa aleatorietat per no bloquejar-ho tot.
        potential_starts = []
        if positions:
            ref = random.choice(positions)
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    potential_starts.append((ref[0] + dx, ref[1] + dy))
        
        random.shuffle(potential_starts)
        
        for _ in range(150):
            coords = random.choice(POLYOMINOES)
            if potential_starts and random.random() < 0.7:
                pos = potential_starts.pop()
            else:
                pos = (random.randint(0, W - 1), random.randint(0, H - 1))
            
            cells  = {(pos[0]+c[0], pos[1]+c[1]) for c in coords}
            if all(0 <= x < W and 0 <= y < H for x, y in cells) and not cells & occupied:
                pieces.append(coords)
                positions.append(pos)
                occupied |= cells
                placed = True
                break
        if not placed:
            return None

    return pieces, positions, walls


# ── Desat canònic ─────────────────────────────────────────────────────────────


def build_puzzle_json(
    W: int, H: int,
    pieces: list[list[list[int]]],
    start_state: tuple,
    goal_shape: list[list[int]],
    goal_pos: tuple[int, int],
    walls: set[tuple[int, int]],
) -> dict | None:
    """
    Construeix el diccionari JSON canònic del puzzle i el valida amb
    Puzzle.from_json. Retorna None si el puzzle no és vàlid.

    Ordenar les coordenades i les peces és obligatori per a que
    Puzzle.from_json no llanci ValueError.
    """
    from puzzle import Puzzle as _Puzzle

    # Ordenem coordenades de cada peça (Puzzle.from_json ho exigeix)
    pieces_normalized = [sorted(coords) for coords in pieces]

    # Ordenem peces per (forma, posició) — ordre canònic
    items = sorted(
        zip(pieces_normalized, [list(p) for p in start_state]),
        key=lambda x: (x[0], x[1]),
    )
    pieces_sorted = [x[0] for x in items]
    start_sorted  = [x[1] for x in items]

    goal_shape_norm = sorted(goal_shape)
    goal_idx = next(
        (i for i, p in enumerate(pieces_sorted) if p == goal_shape_norm), 0
    )

    puzzle_dict = {
        "W": W, "H": H, "walls": sorted(list(walls)),
        "pieces": pieces_sorted,
        "start":  start_sorted,
        "goals":  [{"i": goal_idx, "pos": list(goal_pos)}],
    }

    # Validem que Puzzle.from_json l'accepta (detecta errors de canonicalització)
    try:
        p = _Puzzle.from_json(json.dumps(puzzle_dict))
    except Exception:
        return None

    # Validem que l'estat inicial NO és ja un estat final
    # (si ho fos, el camí mínim seria 0 i eval donaria 0★)
    from logic import is_goal as _is_goal
    if _is_goal(p, p.start):
        return None

    return puzzle_dict


def save_puzzle(
    puzzle_dict: dict,
    stars: float,
    path_len: int,
    output_dir: Path,
    suffix: str = "",
) -> Path | None:
    """
    Desa el puzzle JSON al disc. Usa el hash del contingut com a nom
    per garantir unicitat (evita col·lisions amb random.randint).
    Retorna None si el fitxer ja existia (puzzle duplicat).
    """
    import hashlib
    content   = json.dumps(puzzle_dict)
    file_hash = hashlib.sha256(content.encode()).hexdigest()[:8]
    name      = f"puzzle_{stars:.2f}stars_{path_len}mov_{file_hash}{suffix}.json"
    path      = output_dir / name

    if path.exists():
        return None  # puzzle duplicat, no sobreescribim

    path.write_text(content)
    return path


# ── Pipeline principal ────────────────────────────────────────────────────────


def run(min_stars: float, max_stars: float, n: int, output_dir: Path) -> None:
    output_dir.mkdir(exist_ok=True)

    saved     = 0
    attempts  = 0
    best_stars: dict | None = None
    best_path:  dict | None = None

    print(f"Cercant {n} puzzle(s) de {min_stars:.1f}★ – {max_stars:.1f}★")
    print("Ctrl+C → desa els millors trobats fins ara.\n")

    try:
        while saved < n:
            attempts += 1

            W, H     = random.choices(BOARD_SIZES, weights=BOARD_WEIGHTS, k=1)[0]
            n_pieces = random.choices(PIECE_COUNTS, weights=PIECE_WEIGHTS, k=1)[0]

            result = place_pieces(W, H, n_pieces)
            if result is None:
                continue

            pieces, goal_positions, walls = result
            # Pre-calculem grups per a la canonicalització (state_key)
            from puzzle import Piece as _Piece
            pieces_obj = [_Piece(*sorted([tuple(c) for c in p])) for p in pieces]
            groups = []
            gi = 0
            while gi < len(pieces_obj):
                gj = gi + 1
                while gj < len(pieces_obj) and pieces_obj[gj] == pieces_obj[gi]:
                    gj += 1
                groups.append((gi, gj))
                gi = gj

            goal_idx   = 0
            goal_shape = pieces[goal_idx]
            goal_pos   = goal_positions[goal_idx]

            min_path = _MIN_PATH_FOR_STARS.get(int(min_stars), 0)
            stats = inverse_bfs(W, H, pieces, goal_positions, goal_idx, walls, groups,
                                min_path=min_path)
            if stats is None:
                continue

            stars = evaluate_stats(stats)

            # Puzzle dades
            puzzle_info = dict(
                W=W, H=H, pieces=pieces, walls=walls,
                start_state=stats["start_state"],
                goal_shape=goal_shape, goal_pos=goal_pos,
                stars=stars, path_len=stats["path_len"],
                n_nodes=stats["n_nodes"],
            )

            # Seguiment del millor per estrelles
            if best_stars is None or stars > best_stars["stars"]:
                best_stars = puzzle_info

            # Seguiment del millor per passos (longest path)
            if best_path is None or stats["path_len"] > best_path["path_len"]:
                best_path = puzzle_info

            sys.stdout.write(
                f"\r[{attempts:5d}] "
                f"{stats['path_len']:3d}mov / {stats['n_nodes']:7d}n  "
                f"{stars:.2f}★   millor: {best_stars['stars']:.2f}★ ({best_stars['path_len']}m)"
            )
            sys.stdout.flush()

            if min_stars <= stars <= max_stars:
                puzzle_dict = build_puzzle_json(
                    W, H, pieces, stats["start_state"],
                    goal_shape, goal_pos, walls,
                )
                if puzzle_dict is None:
                    continue  # JSON invàlid, descartem
                path = save_puzzle(
                    puzzle_dict, stars,
                    stats["path_len"], output_dir,
                )
                if path is None:
                    continue  # duplicat, descartem
                saved += 1
                print(f"\n  [✓] {stars:.2f}★  {stats['path_len']}mov  "
                      f"{stats['n_nodes']}n  →  {path}")

    except KeyboardInterrupt:
        print("\n\nAturat per l'usuari.")
        if best_stars:
            print(f"\n[rescat] Millor valoració: {best_stars['stars']:.2f}★ ({best_stars['path_len']}m)")
            p_json = build_puzzle_json(
                best_stars["W"], best_stars["H"], best_stars["pieces"],
                best_stars["start_state"], best_stars["goal_shape"],
                best_stars["goal_pos"], best_stars["walls"]
            )
            if p_json:
                path = save_puzzle(p_json, best_stars["stars"], best_stars["path_len"], output_dir)
                if path: print(f"  Puzle desat a: {path}")
            else:
                print("  Error en formatar el puzle.")

        if best_path and (not best_stars or best_path["path_len"] != best_stars["path_len"]):
            print(f"\n[rescat] Camí més llarg: {best_path['path_len']} passos ({best_path['stars']:.2f}★)")
            p_json = build_puzzle_json(
                best_path["W"], best_path["H"], best_path["pieces"],
                best_path["start_state"], best_path["goal_shape"],
                best_path["goal_pos"], best_path["walls"]
            )
            if p_json:
                path = save_puzzle(p_json, best_path["stars"], best_path["path_len"], output_dir)
                if path: print(f"  Puzle desat a: {path}")
            else:
                print("  Error en formatar el puzle.")
        
        if not best_stars and not best_path:
            print("No s'havia trobat cap puzle vàlid encara.")
        sys.exit(0)

    print(f"\nFet! {saved} puzzle(s) en {attempts} intents.")


# ── CLI ───────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Genera puzzles amb BFS invers intel·ligent"
    )
    parser.add_argument("-n", type=int, default=1)
    parser.add_argument("--min-stars", type=float, default=DEFAULT_MIN_STARS)
    parser.add_argument("--max-stars", type=float, default=DEFAULT_MAX_STARS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    run(args.min_stars, args.max_stars, args.n, args.output)