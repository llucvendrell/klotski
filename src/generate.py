"""
Genera puzzles de peces lliscants a l'atzar.

L'estratègia de generació és la següent:
  1. Escollim les dimensions del taulell (entre 4x4 i 6x6)
  2. Escollim el nombre de peces (distribució esbiaixada, veure PIECE_PROBS)
  3. Generem formes de peces aleatòries (poliominós de mida 1 a 4)
  4. Col·loquem les peces en una posició final vàlida (sense solapaments)
  5. Fem moviments aleatoris des de la posició final per obtenir la posició inicial
     (així garantim que el puzzle és sempre resoluble)
  6. Avaluem el puzzle i el desem si supera el llindar mínim de qualitat

Ús:
    python src/generate.py                      # genera 1 puzzle
    python src/generate.py -n k                # genera k puzzles
    python src/generate.py -n k --min-stars i  # només guarda els que superen i★
    python src/generate.py -n k --output puzzles/  # directori de sortida
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

from solve import solve
from graph import build_graph
from eval import evaluate
from graph import build_graph
from logic import possible_moves, apply_move
from puzzle import Piece, Puzzle, State

# ── Paràmetres de generació ───────────────────────────────────────────────────

# Dimensions possibles del taulell (W, H)
BOARD_SIZES = [
    (4, 4), (4, 5), (5, 4),
    (5, 5), (5, 6), (6, 5),
    (6, 6),
]

MIN_SOLUTION_STEPS = 10

# Distribució esbiaixada del nombre de peces:
# Pocs puzzles amb moltes peces (més difícils d'avaluar) i
# una probabilitat molt baixa de generar puzzles de 12 peces.
PIECE_COUNTS = [4,  5,  6,  7,  8,  12]
PIECE_PROBS  = [0.15, 0.25, 0.30, 0.20, 0.08, 0.02]

# Nombre màxim d'intents per col·locar totes les peces
MAX_PLACEMENT_ATTEMPTS = 1000

# Nombre de moviments aleatoris per "barrejar" el puzzle des de la posició final
MIN_SHUFFLE_MOVES = 50
MAX_SHUFFLE_MOVES = 100

# Llindar mínim de qualitat per defecte (0 = guarda tots)
DEFAULT_MIN_STARS = 0.0

# Directori de sortida per defecte
DEFAULT_OUTPUT = Path("puzzles")

# mínim 75% del taulell ocupat
MIN_DENSITY = 0.75

# ── Formes de poliominós ──────────────────────────────────────────────────────

# Tots els poliominós de mida 1 a 4 en forma normalitzada.
# Cada peça és una llista de coordenades relatives (x, y) amb (0,0) a dalt-esquerra.
ALL_POLYOMINOES: list[tuple[tuple[int, int], ...]] = [
    # Mida 1
    ((0, 0),),
    # Mida 2
    ((0, 0), (1, 0)),   # horitzontal
    ((0, 0), (0, 1)),   # vertical
    # Mida 3
    ((0, 0), (1, 0), (2, 0)),          # L horitzontal
    ((0, 0), (0, 1), (0, 2)),          # L vertical
    ((0, 0), (1, 0), (1, 1)),          # L
    ((0, 0), (0, 1), (1, 1)),          # L girada
    ((0, 1), (1, 0), (1, 1)),          # L altre
    ((0, 0), (1, 0), (0, 1)),          # L altre girada
    # Mida 4
    ((0, 0), (1, 0), (2, 0), (3, 0)),  # I horitzontal
    ((0, 0), (0, 1), (0, 2), (0, 3)),  # I vertical
    ((0, 0), (1, 0), (0, 1), (1, 1)),  # quadrat 2x2
    ((0, 0), (1, 0), (2, 0), (0, 1)),  # L
    ((0, 0), (1, 0), (2, 0), (2, 1)),  # L girada
    ((0, 1), (1, 1), (2, 1), (2, 0)),  # J
    ((0, 0), (0, 1), (0, 2), (1, 2)),  # J vertical
    ((0, 0), (1, 0), (1, 1), (1, 2)),  # L vertical
    ((0, 0), (0, 1), (1, 0), (2, 0)),  # T
    ((0, 0), (1, 0), (2, 0), (1, 1)),  # T
    ((0, 1), (1, 0), (1, 1), (2, 1)),  # S
    ((0, 0), (1, 0), (1, 1), (2, 1)),  # Z
]


# ── Generació de peces ────────────────────────────────────────────────────────


def random_piece() -> Piece:
    """Retorna una peça aleatòria dels poliominós disponibles."""
    coords = random.choice(ALL_POLYOMINOES)
    return Piece.normalized(list(coords))


def piece_cells(piece: Piece, pos: tuple[int, int]) -> set[tuple[int, int]]:
    """Retorna les caselles absolutes que ocupa una peça a la posició donada."""
    px, py = pos
    return {(px + dx, py + dy) for dx, dy in piece.coords}


def fits_in_board(
    piece: Piece,
    pos: tuple[int, int],
    W: int,
    H: int,
    occupied: set[tuple[int, int]],
) -> bool:
    """Comprova si una peça cap al taulell sense solapar res."""
    for x, y in piece_cells(piece, pos):
        if x < 0 or x >= W or y < 0 or y >= H:
            return False
        if (x, y) in occupied:
            return False
    return True


# ── Col·locació de peces ──────────────────────────────────────────────────────


def place_pieces(
    W: int,
    H: int,
    n_pieces: int,
) -> tuple[list[Piece], list[tuple[int, int]]] | None:
    """
    Intenta col·locar n_pieces peces aleatòries al taulell sense solapaments.
    Retorna (llista de peces, llista de posicions) o None si no és possible.
    """
    for _ in range(MAX_PLACEMENT_ATTEMPTS):
        pieces: list[Piece] = []
        positions: list[tuple[int, int]] = []
        occupied: set[tuple[int, int]] = set()
        success = True

        for _ in range(n_pieces):
            placed = False
            for _ in range(MAX_PLACEMENT_ATTEMPTS):
                piece = random_piece()
                x = random.randint(0, W - 1)
                y = random.randint(0, H - 1)
                pos = (x, y)
                if fits_in_board(piece, pos, W, H, occupied):
                    pieces.append(piece)
                    positions.append(pos)
                    occupied |= piece_cells(piece, pos)
                    placed = True
                    break
            if not placed:
                success = False
                break

        if success:
            return pieces, positions

    return None


# ── Canonicalització ──────────────────────────────────────────────────────────


def canonicalize(
    pieces: list[Piece],
    positions: list[tuple[int, int]],
) -> tuple[list[Piece], list[tuple[int, int]]]:
    """
    Ordena les peces en ordre canònic: per (forma, posició).
    Necessari per crear un Puzzle vàlid.
    """
    pairs = sorted(zip(pieces, positions))
    sorted_pieces = [p for p, _ in pairs]
    sorted_positions = [pos for _, pos in pairs]
    return sorted_pieces, sorted_positions


# ── Barreja (shuffle) ─────────────────────────────────────────────────────────


def shuffle_state(puzzle: Puzzle, n_moves: int) -> State:
    """
    Fa n_moves moviments aleatoris des de l'estat inicial del puzzle,
    evitant moure la mateixa peça dues vegades seguides per allunyar-se
    més de la posició inicial.
    """
    state = puzzle.start
    last_piece = None
    for _ in range(n_moves):
        moves = possible_moves(puzzle, state)
        # Evitem moure la mateixa peça que acabem de moure
        if last_piece is not None:
            filtered = [m for m in moves if m[0] != last_piece]
            moves = filtered if filtered else moves
        if not moves:
            break
        move = random.choice(moves)
        last_piece = move[0]
        state = apply_move(puzzle, state, move)
    return state


# ── Generació del puzzle ──────────────────────────────────────────────────────


def generate_puzzle() -> Puzzle | None:
    """
    Genera un puzzle aleatori seguint l'estratègia descrita al mòdul.
    Retorna un Puzzle vàlid o None si no s'ha pogut generar.
    """
    # 1. Dimensions aleatòries
    W, H = random.choice(BOARD_SIZES)

    # 2. Nombre de peces (distribució esbiaixada)
    n_pieces = random.choices(PIECE_COUNTS, weights=PIECE_PROBS, k=1)[0]

    # 3 i 4. Col·locar peces en posició final
    result = place_pieces(W, H, n_pieces)
    if result is None:
        return None
    pieces, goal_positions = result

    # Comprovem la densitat mínima
    total_cells = W * H
    occupied_cells = sum(len(p.coords) for p in pieces)
    if occupied_cells / total_cells < MIN_DENSITY:
        return None

    # Canonicalitzem per crear el puzzle
    pieces, goal_positions = canonicalize(pieces, goal_positions)

    # La peça objectiu és la primera (índex 0)
    goal_piece_idx = 0
    goal_pos = goal_positions[goal_piece_idx]

    try:
        # Creem el puzzle amb la posició final com a estat inicial
        puzzle_at_goal = Puzzle(
            W=W,
            H=H,
            walls=(),
            pieces=tuple(pieces),
            start=State(tuple(goal_positions)),
            goals=((goal_piece_idx, goal_pos),),
        )
    except ValueError:
        return None

    # 5. Barregem per obtenir l'estat inicial
    n_moves = random.randint(MIN_SHUFFLE_MOVES, MAX_SHUFFLE_MOVES)
    shuffled_state = shuffle_state(puzzle_at_goal, n_moves)

    # Si l'estat barrejat ja és el goal, el puzzle és trivial
    if shuffled_state == puzzle_at_goal.start:
        return None
    
    # La peça objectiu no pot estar ja a la posició goal
    if shuffled_state.positions[goal_piece_idx] == goal_pos:
        return None
    
    # La peça objectiu ha d'estar prou lluny del goal
    goal_x, goal_y = goal_pos
    start_x, start_y = shuffled_state.positions[goal_piece_idx]
    manhattan_dist = abs(goal_x - start_x) + abs(goal_y - start_y)
    if manhattan_dist < 3:
        return None

    try:
        puzzle = Puzzle(
            W=W, H=H, walls=(),
            pieces=tuple(pieces),
            start=shuffled_state,
            goals=((goal_piece_idx, goal_pos),),
        )
    except ValueError:
        return None

    # El camí mínim ha de tenir almenys MIN_SOLUTION_STEPS passos
    g = build_graph(puzzle)
    moves = solve(g, puzzle)
    if moves is None or len(moves) < MIN_SOLUTION_STEPS:
        return None

    return puzzle


# ── CLI ───────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Genera puzzles de peces lliscants a l'atzar"
    )
    parser.add_argument("-n", type=int, default=1, help="Nombre de puzzles a generar (per defecte 1)")
    parser.add_argument("--min-stars", type=float, default=DEFAULT_MIN_STARS, help="Puntuació mínima per guardar el puzzle (per defecte 0)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Directori de sortida (per defecte puzzles/)")
    args = parser.parse_args()

    args.output.mkdir(exist_ok=True)

    saved = 0
    attempts = 0

    while saved < args.n:
        attempts += 1
        sys.stdout.write(f"\rIntents: {attempts}  Guardats: {saved}/{args.n}")
        sys.stdout.flush()

        puzzle = generate_puzzle()
        if puzzle is None:
            continue

        # Avaluem el puzzle
        try:
            g = build_graph(puzzle)
            stars = evaluate(puzzle, g)
        except Exception:
            continue

        if stars < args.min_stars:
            continue

        # Desem el puzzle
        path = args.output / f"{puzzle.hash()[:8]}.json"
        path.write_text(puzzle.to_json())
        saved += 1
        print(f"\n  [★ {stars:.2f}] Desat: {path}")

    print(f"\nFet! {saved} puzzle(s) generats en {attempts} intents.")