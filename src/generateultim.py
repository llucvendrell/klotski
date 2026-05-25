"""
Genera puzzles de peces lliscants amb BFS invers intel·ligent.

Basat en el codi del company (que funcionava) amb millores mínimes:
  - M3 real (coeficient de variació) en comptes d'aproximació
  - Comptatge de goals dins del BFS (sense passada extra)
  - Sortida més clara

Ús:
    python src/generate.py                        # busca puzzles de 4.3★+
    python src/generate.py --min-stars 3.0        # busca puzzles de 3.0★+
    python src/generate.py --min-stars 4.0 -n 3  # busca 3 puzzles de 4.0★+
    python src/generate.py --output my_puzzles/
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import deque
from pathlib import Path

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

BFS_NODE_LIMIT = 5_000_000

DEFAULT_MIN_STARS = 4.3
DEFAULT_MAX_STARS = 5.0
DEFAULT_OUTPUT    = Path("puzzles")


# ── Lògica de moviments ───────────────────────────────────────────────────────


def get_moves(
    W: int, H: int,
    pieces: list[list[list[int]]],
    state: tuple,
) -> list[tuple[int, tuple[int, int]]]:
    occupied: dict[tuple[int, int], int] = {}
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
    min_path: int = 0,
) -> dict | None:
    """
    BFS invers des del goal: explora tots els estats accessibles.
    Retorna estadístiques per avaluar el puzzle, o None si és massa gran.

    min_path: si es defineix, atura el BFS ANTICIPADAMENT quan el graf
    ja és prou gran per saber que no hi ha cap camí de longitud min_path.
    Concretament: si hem visitat més nodes que BFS_NODE_LIMIT/10 i la
    distància màxima és < min_path/2, descartem ràpidament.
    """
    start     = tuple(goal_positions)
    goal_pos  = goal_positions[goal_idx]

    visited: dict[tuple, tuple[int, tuple | None]] = {start: (0, None)}
    queue: deque[tuple] = deque([start])

    out_degrees: dict[tuple, int] = {}
    n_edges   = 0
    max_dist  = 0
    best_state = start
    n_goals   = 1  # el goal en si és un estat final
    early_check = max(500, BFS_NODE_LIMIT // 200)  # comprovem amb pocs nodes

    while queue:
        curr      = queue.popleft()
        curr_dist = visited[curr][0]
        moves     = get_moves(W, H, pieces, curr)
        out_degrees[curr] = len(moves)

        if curr_dist > max_dist:
            max_dist   = curr_dist
            best_state = curr

        # Descart primerenc: si amb pocs nodes el camí és molt curt,
        # aquest taulell mai donarà el llindar d'estrelles demanat
        if min_path > 0 and len(visited) == early_check:
            if max_dist < min_path // 2:
                return None

        for p_idx, nxt_pos in moves:
            n_edges += 1
            nxt_list = list(curr)
            nxt_list[p_idx] = nxt_pos
            nxt = tuple(nxt_list)

            if nxt not in visited:
                if len(visited) >= BFS_NODE_LIMIT:
                    return None
                visited[nxt] = (curr_dist + 1, curr)
                queue.append(nxt)
                if nxt[goal_idx] == goal_pos:
                    n_goals += 1

    # Reconstruïm els graus al llarg del camí òptim (per M3)
    path_degrees: list[int] = []
    curr = best_state
    while curr is not None:
        path_degrees.append(out_degrees.get(curr, 0))
        curr = visited[curr][1]

    return {
        "start_state" : best_state,
        "path_len"    : max_dist,
        "n_nodes"     : len(visited),
        "n_edges"     : n_edges // 2,
        "n_goals"     : n_goals,
        "path_degrees": path_degrees,
    }


# ── Avaluació (mateixes fórmules que eval.py) ─────────────────────────────────


def evaluate_stats(stats: dict) -> float:
    """Retorna la puntuació decimal [0, 5] amb les fórmules d'eval.py."""
    path_len = stats["path_len"]
    n_nodes  = stats["n_nodes"]
    n_edges  = stats["n_edges"]
    n_goals  = stats["n_goals"]
    degs     = stats["path_degrees"]

    # M1: sigmoide
    m1 = 1.0 / (1.0 + math.exp(-0.10 * (path_len - 15.0)))

    # M2: complexitat
    if n_nodes > 1:
        density = n_edges / n_nodes
        m2 = min(math.log2(n_nodes) * density / 75.0, 1.0)
    else:
        m2 = 0.0

    # M3: coeficient de variació dels graus al camí (igual que eval.py)
    if len(degs) >= 2:
        mean = sum(degs) / len(degs)
        if mean > 0:
            std = math.sqrt(sum((x - mean) ** 2 for x in degs) / len(degs))
            m3  = min(std / mean, 1.0)
        else:
            m3 = 0.0
    else:
        m3 = 0.0

    # M4: escassetat dels goals
    ratio = n_goals / n_nodes if n_nodes > 0 else 1.0
    m4    = math.exp(-5.0 * ratio)

    score = 0.45*m1 + 0.25*m2 + 0.20*m3 + 0.10*m4

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
) -> tuple[list[list[list[int]]], list[tuple[int, int]]] | None:
    occupied: set[tuple[int, int]] = set()
    pieces:    list[list[list[int]]] = []
    positions: list[tuple[int, int]] = []

    for _ in range(n):
        placed = False
        for _ in range(100):
            coords = random.choice(POLYOMINOES)
            pos    = (random.randint(0, W - 1), random.randint(0, H - 1))
            cells  = {(pos[0]+c[0], pos[1]+c[1]) for c in coords}
            if all(0 <= x < W and 0 <= y < H for x, y in cells) and not cells & occupied:
                pieces.append(coords)
                positions.append(pos)
                occupied |= cells
                placed = True
                break
        if not placed:
            return None

    return pieces, positions


# ── Desat canònic ─────────────────────────────────────────────────────────────


def build_puzzle_json(
    W: int, H: int,
    pieces: list[list[list[int]]],
    start_state: tuple,
    goal_shape: list[list[int]],
    goal_pos: tuple[int, int],
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
        "W": W, "H": H, "walls": [],
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

    saved    = 0
    attempts = 0
    best: dict | None = None

    print(f"Cercant {n} puzzle(s) de {min_stars:.1f}★ – {max_stars:.1f}★")
    print("Ctrl+C → desa el millor trobat fins ara.\n")

    try:
        while saved < n:
            attempts += 1

            W, H     = random.choices(BOARD_SIZES, weights=BOARD_WEIGHTS, k=1)[0]
            n_pieces = random.choices(PIECE_COUNTS, weights=PIECE_WEIGHTS, k=1)[0]

            result = place_pieces(W, H, n_pieces)
            if result is None:
                continue

            pieces, goal_positions = result
            goal_idx   = 0
            goal_shape = pieces[goal_idx]
            goal_pos   = goal_positions[goal_idx]

            min_path = _MIN_PATH_FOR_STARS.get(int(min_stars), 0)
            stats = inverse_bfs(W, H, pieces, goal_positions, goal_idx,
                                min_path=min_path)
            if stats is None:
                continue

            stars = evaluate_stats(stats)

            if best is None or stars > best["stars"]:
                best = dict(
                    W=W, H=H, pieces=pieces,
                    start_state=stats["start_state"],
                    goal_shape=goal_shape, goal_pos=goal_pos,
                    stars=stars, path_len=stats["path_len"],
                    n_nodes=stats["n_nodes"],
                )

            sys.stdout.write(
                f"\r[{attempts:5d}] "
                f"{stats['path_len']:3d}mov / {stats['n_nodes']:7d}n  "
                f"{stars:.2f}★   millor: {best['stars']:.2f}★"
            )
            sys.stdout.flush()

            if min_stars <= stars <= max_stars:
                puzzle_dict = build_puzzle_json(
                    W, H, pieces, stats["start_state"],
                    goal_shape, goal_pos,
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
        print("\n\nAturada.")
        if best is not None:
            puzzle_dict = build_puzzle_json(
                best["W"], best["H"], best["pieces"],
                best["start_state"], best["goal_shape"], best["goal_pos"],
            )
            if puzzle_dict is not None:
                path = save_puzzle(
                    puzzle_dict, best["stars"],
                    best["path_len"], output_dir, suffix="_rescat",
                )
                if path:
                    print(f"  [rescat] {best['stars']:.2f}★  "
                          f"{best['path_len']}mov  →  {path}")
                else:
                    print(f"  [rescat] ja existia al disc (duplicat)")
            else:
                print("  [rescat] error en canonicalitzar el puzzle")
        else:
            print("  No s'havia trobat cap puzzle vàlid encara.")
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