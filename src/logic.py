"""
Lògica del joc de trencaclosques de peces lliscants.

Permet calcular els moviments possibles i aplicar-los.
"""

from __future__ import annotations

from puzzle import Puzzle, State, Coord

Direction = str  # "N", "E", "S", "W"
Move = tuple[int, Direction, int]

DELTAS: dict[Direction, Coord] = {
    "N": (0, -1),
    "S": (0, 1),
    "E": (1, 0),
    "W": (-1, 0),
}


def _piece_cells(puzzle: Puzzle, state: State, piece_idx: int) -> set[Coord]:
    """Retorna les caselles absolutes que ocupa una peça."""
    px, py = state.positions[piece_idx]
    return {(px + dx, py + dy) for dx, dy in puzzle.pieces[piece_idx].coords}


def _occupied_by_others(
    puzzle: Puzzle, state: State, piece_idx: int
) -> set[Coord]:
    """Retorna les caselles ocupades per parets i totes les peces excepte piece_idx."""
    cells: set[Coord] = set(puzzle.walls)
    for i, piece in enumerate(puzzle.pieces):
        if i == piece_idx:
            continue
        px, py = state.positions[i]
        for dx, dy in piece.coords:
            cells.add((px + dx, py + dy))
    return cells


def can_move(
    puzzle: Puzzle, state: State, piece_idx: int, direction: Direction
) -> bool:
    """Comprova si una peça pot moure's un pas en la direcció donada."""
    ddx, ddy = DELTAS[direction]
    my_cells = _piece_cells(puzzle, state, piece_idx)
    blocked = _occupied_by_others(puzzle, state, piece_idx)

    for cx, cy in my_cells:
        nx, ny = cx + ddx, cy + ddy
        if nx < 0 or nx >= puzzle.W or ny < 0 or ny >= puzzle.H:
            return False
        if (nx, ny) in blocked:
            return False
    return True


def apply_move(puzzle: Puzzle, state: State, move: Move) -> State:
    """Aplica un moviment i retorna el nou estat. Llença ValueError si és invàlid."""
    piece_idx, direction, dist = move
    ddx, ddy = DELTAS[direction]
    px, py = state.positions[piece_idx]
    positions = list(state.positions)
    for _ in range(dist):
        s = State(tuple(positions))
        if not can_move(puzzle, s, piece_idx, direction):
            raise ValueError(f"Moviment invàlid: peça {piece_idx} direcció {direction}")
        px += ddx
        py += ddy
        positions[piece_idx] = (px, py)
    return State(tuple(positions))


def max_slide(
    puzzle: Puzzle, state: State, piece_idx: int, direction: Direction
) -> int:
    """Quantes caselles pot lliscar una peça en una direcció?"""
    count = 0
    s = state
    while can_move(puzzle, s, piece_idx, direction):
        s = apply_move(puzzle, s, (piece_idx, direction, 1))
        count += 1
    return count


def possible_moves(puzzle: Puzzle, state: State) -> list[Move]:
    """Retorna tots els moviments vàlids d'un pas."""
    moves: list[Move] = []
    for i in range(len(puzzle.pieces)):
        for d in ("N", "E", "S", "W"):
            if can_move(puzzle, state, i, d):
                moves.append((i, d, 1))
    return moves


def valid_placement(puzzle: Puzzle, state: State) -> bool:
    """
    Comprova que cap peça se solapa amb una altra, amb les parets,
    ni surt fora del taulell.
    """
    occupied: set[Coord] = set(puzzle.walls)
    for i, piece in enumerate(puzzle.pieces):
        px, py = state.positions[i]
        for dx, dy in piece.coords:
            x, y = px + dx, py + dy
            if x < 0 or x >= puzzle.W or y < 0 or y >= puzzle.H:
                return False
            if (x, y) in occupied:
                return False
            occupied.add((x, y))
    return True


def replay_moves(puzzle: Puzzle, moves: list[Move]) -> list[State]:
    """
    Reprodueix una seqüència de moviments des de l'estat inicial
    i retorna tots els estats visitats (inclòs l'inicial).
    """
    states: list[State] = [puzzle.start]
    current = puzzle.start
    for move in moves:
        current = apply_move(puzzle, current, move)
        states.append(current)
    return states


def is_goal(puzzle: Puzzle, state: State) -> bool:
    """
    Comprova si l'estat actual satisfà tots els objectius.
    Considera que peces del mateix tipus són intercanviables si l'índex
    indicat al goal correspon a un grup de peces idèntiques.
    """
    # Agrupem posicions per tipus de peça per a una comprovació ràpida
    # (Això s'hauria de pre-calcular si es crida moltes vegades, però 
    # per is_goal és suficientment ràpid aquí)
    
    # Identificarem els grups de peces iguals tal com fem a state_key
    i = 0
    groups = []
    while i < len(puzzle.pieces):
        j = i + 1
        while j < len(puzzle.pieces) and puzzle.pieces[j] == puzzle.pieces[i]:
            j += 1
        groups.append((i, j))
        i = j

    # Per cada objectiu, comprovem si algun membre del seu grup és a la posició
    for p_idx, target_pos in puzzle.goals.items():
        # Busquem a quin grup pertany p_idx
        found = False
        for start, end in groups:
            if start <= p_idx < end:
                # Comprovem si alguna de les peces [start:end] és a target_pos
                if target_pos in state.positions[start:end]:
                    found = True
                break
        if not found:
            return False
    return True
