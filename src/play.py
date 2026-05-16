"""
Joc interactiu de trencaclosques de peces lliscants amb PyGame.

Ús: python3 play.py <puzzle.json>
"""

from __future__ import annotations

import colorsys
import sys
from pathlib import Path

import pygame

from puzzle import Puzzle, State
from logic import apply_move, can_move, is_goal, max_slide

# -- Paràmetres visuals ------------------------------------------------

CELL = 80
MARGIN_TOP = 20
MARGIN_SIDE = 20
MARGIN_BOTTOM = 50   # espai extra per al text
BORDER_W = 3
PIECE_PAD = 3        # inset des de les línies de la quadrícula

BG_COLOR = (245, 245, 245)
GRID_COLOR = (200, 200, 200)
WALL_COLOR = (60, 60, 60)
BORDER_COLOR = (40, 40, 40)
SOLVED_COLOR = (255, 220, 40)
HINT_COLOR = (160, 160, 160)

# -- Paràmetres dels objectius (dots i vores) ---------------------------

TARGET_DOT_ALPHA = 255          # opacitat dels dots d'objectiu (0–255), 85% ≈ 216
TARGET_DOT_RATIO = 0.45         # mida del dot respecte a CELL
OVERLAY_DOT_RATIO = 0.15        # mida del dot petit (peça secundària a sobre), 2/3 del gran
DOT_CORNER_RADIUS = 0.25        # radi de les cantonades del dot, com a fracció de la mida

PRIMARY_BORDER_W = 4            # gruix de la vora de les peces primàries
PRIMARY_BORDER_SAT = 1.0        # saturació de la vora (0.0–1.0)
PRIMARY_BORDER_VAL = 0.55       # valor/brillantor de la vora (0.0–1.0)

PIECE_PALETTE: list[tuple[int, int, int]] = [
    (76, 175, 80),
    (33, 150, 243),
    (255, 193, 7),
    (156, 39, 176),
    (255, 87, 34),
    (0, 188, 212),
    (233, 30, 99),
    (121, 85, 72),
    (63, 81, 181),
    (139, 195, 74),
    (255, 152, 0),
    (103, 58, 183),
    (0, 150, 136),
    (244, 67, 54),
    (3, 169, 244),
    (205, 220, 57),
    (255, 235, 59),
    (96, 125, 139),
    (38, 166, 154),
    (239, 108, 0),
]


def piece_color(index: int) -> tuple[int, int, int]:
    return PIECE_PALETTE[index % len(PIECE_PALETTE)]


def darker(color: tuple[int, int, int], amount: int = 40) -> tuple[int, int, int]:
    return tuple(max(0, c - amount) for c in color)  # type: ignore[return-value]


def saturated(
    color: tuple[int, int, int],
    sat: float = PRIMARY_BORDER_SAT,
    val: float = PRIMARY_BORDER_VAL,
) -> tuple[int, int, int]:
    """Retorna el color amb saturació i valor ajustats (mantenint el to)."""
    r, g, b = color[0] / 255, color[1] / 255, color[2] / 255
    h, _s, _v = colorsys.rgb_to_hsv(r, g, b)
    nr, ng, nb = colorsys.hsv_to_rgb(h, sat, val)
    return (int(nr * 255), int(ng * 255), int(nb * 255))


# -- Conversions coordenades ↔ píxels ---------------------------------


def cell_to_px(cx: int, cy: int) -> tuple[int, int]:
    return MARGIN_SIDE + cx * CELL, MARGIN_TOP + cy * CELL


def px_to_cell(px: int, py: int) -> tuple[float, float]:
    return (px - MARGIN_SIDE) / CELL, (py - MARGIN_TOP) / CELL


# -- Cerca de peça sota el cursor --------------------------------------


def find_piece_at(puzzle: Puzzle, state: State, mx: int, my: int) -> int | None:
    """Retorna l'índex de la peça sota el píxel (mx, my), o None."""
    cx, cy = px_to_cell(mx, my)
    ix, iy = int(cx), int(cy)
    if ix < 0 or ix >= puzzle.W or iy < 0 or iy >= puzzle.H:
        return None
    if cx < 0 or cy < 0:
        return None
    for i, piece in enumerate(puzzle.pieces):
        px, py = state.positions[i]
        for dx, dy in piece.coords:
            if px + dx == ix and py + dy == iy:
                return i
    return None


# -- Silueta de les peces -----------------------------------------------


def _piece_outline(cells: set[tuple[int, int]]) -> list[tuple[int, int]]:
    """
    Calcula el polígon frontera d'un conjunt de caselles.

    Retorna vèrtexs en ordre horari (coordenades de pantalla).
    Cada vèrtex és un punt de la quadrícula (cantonada de casella).
    """
    # Arestes dirigides en sentit horari per cada casella
    edges: dict[tuple[int, int], tuple[int, int]] = {}
    for cx, cy in cells:
        if (cx, cy - 1) not in cells:  # dalt
            edges[(cx, cy)] = (cx + 1, cy)
        if (cx + 1, cy) not in cells:  # dreta
            edges[(cx + 1, cy)] = (cx + 1, cy + 1)
        if (cx, cy + 1) not in cells:  # baix
            edges[(cx + 1, cy + 1)] = (cx, cy + 1)
        if (cx - 1, cy) not in cells:  # esquerra
            edges[(cx, cy + 1)] = (cx, cy)

    start = min(edges)
    polygon: list[tuple[int, int]] = [start]
    current = start
    while True:
        nxt = edges[current]
        if nxt == start:
            break
        polygon.append(nxt)
        current = nxt
    return polygon


def _simplify(polygon: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Elimina vèrtexs col·lineals (punts intermedis en arestes rectes)."""
    result: list[tuple[int, int]] = []
    n = len(polygon)
    for i in range(n):
        p = polygon[(i - 1) % n]
        c = polygon[i]
        nx = polygon[(i + 1) % n]
        # Producte vectorial ≠ 0 → canvi de direcció
        if (c[0] - p[0]) * (nx[1] - c[1]) - (c[1] - p[1]) * (nx[0] - c[0]) != 0:
            result.append(c)
    return result


def _piece_polygon(
    cells: set[tuple[int, int]],
    offset_px: tuple[float, float] = (0.0, 0.0),
) -> list[tuple[float, float]]:
    """
    Calcula el polígon de silueta d'una peça, amb inset.

    *cells* són les coordenades absolutes de les caselles de la peça.
    *offset_px* és un desplaçament addicional en píxels (per arrossegar).
    """
    outline = _piece_outline(cells)
    simplified = _simplify(outline)
    ox, oy = offset_px

    result: list[tuple[float, float]] = []
    for vx, vy in simplified:
        # Determinar l'inset segons quines caselles adjacents són de la peça
        br = (vx, vy) in cells
        bl = (vx - 1, vy) in cells
        tr = (vx, vy - 1) in cells
        tl = (vx - 1, vy - 1) in cells

        ix = PIECE_PAD if (br + tr) > (bl + tl) else -PIECE_PAD
        iy = PIECE_PAD if (br + bl) > (tr + tl) else -PIECE_PAD

        result.append((MARGIN_SIDE + vx * CELL + ix + ox, MARGIN_TOP + vy * CELL + iy + oy))

    return result


def draw_piece(
    screen: pygame.Surface,
    puzzle: Puzzle,
    piece_idx: int,
    pos_x: int,
    pos_y: int,
    offset_px: tuple[float, float] = (0.0, 0.0),
    *,
    primary: bool = False,
) -> None:
    """Dibuixa una peça com a silueta sòlida amb vora."""
    color = piece_color(piece_idx)
    cells = {
        (pos_x + dx, pos_y + dy) for dx, dy in puzzle.pieces[piece_idx].coords
    }
    polygon = _piece_polygon(cells, offset_px)
    if len(polygon) >= 3:
        pygame.draw.polygon(screen, color, polygon)
        if primary:
            border_color = saturated(color)
            pygame.draw.polygon(screen, border_color, polygon, width=PRIMARY_BORDER_W)
        else:
            pygame.draw.polygon(screen, darker(color), polygon, width=2)


def _draw_dot(
    screen: pygame.Surface,
    cx: int,
    cy: int,
    color: tuple[int, int, int],
    ratio: float,
    alpha: int,
) -> None:
    """Dibuixa un rectangle arrodonit semitransparent al centre de la casella (cx, cy)."""
    size = int(CELL * ratio)
    corner = max(1, int(size * DOT_CORNER_RADIUS))
    px, py = cell_to_px(cx, cy)
    top_left_x = int(px + (CELL - size) / 2)
    top_left_y = int(py + (CELL - size) / 2)
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.rect(
        surf, (*color, alpha),
        (0, 0, size, size),
        border_radius=corner,
    )
    screen.blit(surf, (top_left_x, top_left_y))



def draw_board(
    screen: pygame.Surface,
    puzzle: Puzzle,
    state: State,
    dragging_piece: int | None,
    drag_offset_px: tuple[float, float],
    solved: bool,
) -> None:
    board_w = puzzle.W * CELL
    board_h = puzzle.H * CELL
    screen_w = screen.get_width()
    screen_h = screen.get_height()

    # Índexs de peces primàries (les que apareixen als objectius)
    primary_pieces = {gi for gi, _ in puzzle.goals}

    # Caselles objectiu: (cx, cy) → índex de peça primària
    goal_cells: dict[tuple[int, int], int] = {}
    for gi, gpos in puzzle.goals:
        gx, gy = gpos
        for dx, dy in puzzle.pieces[gi].coords:
            goal_cells[(gx + dx, gy + dy)] = gi

    # -- Capa 1: Fons, parets, quadrícula ------------------------------

    screen.fill(SOLVED_COLOR if solved else BG_COLOR)
    pygame.draw.rect(
        screen, BG_COLOR,
        (MARGIN_SIDE, MARGIN_TOP, board_w, board_h),
    )

    for wx, wy in puzzle.walls:
        rx, ry = cell_to_px(wx, wy)
        pygame.draw.rect(screen, WALL_COLOR, (rx, ry, CELL, CELL))

    for col in range(puzzle.W + 1):
        x = MARGIN_SIDE + col * CELL
        pygame.draw.line(screen, GRID_COLOR, (x, MARGIN_TOP), (x, MARGIN_TOP + board_h))
    for row in range(puzzle.H + 1):
        y = MARGIN_TOP + row * CELL
        pygame.draw.line(screen, GRID_COLOR, (MARGIN_SIDE, y), (MARGIN_SIDE + board_w, y))

    # -- Capa 2: Dots d'objectiu --------------------------------------

    for (cx, cy), gi in goal_cells.items():
        color = piece_color(gi)
        _draw_dot(screen, cx, cy, color, TARGET_DOT_RATIO, TARGET_DOT_ALPHA)

    # -- Capa 3: Peces -------------------------------------------------

    for i in range(len(puzzle.pieces)):
        if i == dragging_piece:
            continue
        px, py = state.positions[i]
        draw_piece(screen, puzzle, i, px, py, primary=i in primary_pieces)

    if dragging_piece is not None:
        px, py = state.positions[dragging_piece]
        draw_piece(
            screen, puzzle, dragging_piece, px, py, drag_offset_px,
            primary=dragging_piece in primary_pieces,
        )

    # -- Capa 4: Dots per sobre de peces que tapen objectius -----------

    for (cx, cy), gi in goal_cells.items():
        color = piece_color(gi)
        _draw_dot(screen, cx, cy, color, OVERLAY_DOT_RATIO, TARGET_DOT_ALPHA)

    # -- Vora del taulell i text d'ajuda -------------------------------

    pygame.draw.rect(
        screen,
        BORDER_COLOR,
        (MARGIN_SIDE - BORDER_W, MARGIN_TOP - BORDER_W,
         board_w + 2 * BORDER_W, board_h + 2 * BORDER_W),
        width=BORDER_W,
    )

    font = pygame.font.SysFont(None, 18)
    line1 = font.render("Drag pieces with mouse", True, HINT_COLOR)
    line2 = font.render("Esc - exit  /  R - reset", True, HINT_COLOR)
    text_x = screen_w // 2
    text_y = MARGIN_TOP + board_h + 8
    screen.blit(line1, line1.get_rect(midtop=(text_x, text_y)))
    screen.blit(line2, line2.get_rect(midtop=(text_x, text_y + 16)))


# -- Bucle principal ----------------------------------------------------

# Llindar en píxels per decidir l'eix de l'arrossegament
AXIS_THRESHOLD = 8


def run_game(puzzle: Puzzle) -> None:
    pygame.init()

    screen_w = puzzle.W * CELL + 2 * MARGIN_SIDE
    screen_h = puzzle.H * CELL + MARGIN_TOP + MARGIN_BOTTOM
    screen = pygame.display.set_mode((screen_w, screen_h))
    pygame.display.set_caption("Klotski!")

    state = puzzle.start
    solved = False

    # Estat de l'arrossegament
    dragging: int | None = None  # índex de la peça
    drag_start_mx = 0  # posició del ratolí a l'inici
    drag_start_my = 0
    drag_axis: str | None = None  # "H", "V" o None (indecís)
    drag_slides: dict[str, int] = {}  # direcció → max caselles
    drag_offset_px = (0.0, 0.0)  # desplaçament actual en píxels

    clock = pygame.time.Clock()
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                    running = False
                elif event.key == pygame.K_r:
                    state = puzzle.start
                    solved = False
                    dragging = None

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if dragging is None:
                    piece_idx = find_piece_at(puzzle, state, *event.pos)
                    if piece_idx is not None:
                        slides = {}
                        for d in ("N", "E", "S", "W"):
                            ms = max_slide(puzzle, state, piece_idx, d)
                            if ms > 0:
                                slides[d] = ms
                        if slides:  # almenys algun moviment possible
                            dragging = piece_idx
                            drag_start_mx, drag_start_my = event.pos
                            drag_axis = None
                            drag_slides = slides
                            drag_offset_px = (0.0, 0.0)

            elif event.type == pygame.MOUSEMOTION and dragging is not None:
                mx, my = event.pos
                dpx = mx - drag_start_mx
                dpy = my - drag_start_my

                # Decidir eix si encara no s'ha decidit
                if drag_axis is None:
                    if abs(dpx) > AXIS_THRESHOLD or abs(dpy) > AXIS_THRESHOLD:
                        drag_axis = "H" if abs(dpx) >= abs(dpy) else "V"

                ox, oy = 0.0, 0.0
                if drag_axis == "H":
                    max_e = drag_slides.get("E", 0)
                    max_w = drag_slides.get("W", 0)
                    ox = max(-max_w * CELL, min(max_e * CELL, float(dpx)))
                elif drag_axis == "V":
                    max_s = drag_slides.get("S", 0)
                    max_n = drag_slides.get("N", 0)
                    oy = max(-max_n * CELL, min(max_s * CELL, float(dpy)))

                drag_offset_px = (ox, oy)

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if dragging is not None:
                    ox, oy = drag_offset_px
                    # Snap al enter de caselles més proper
                    snap_cells_x = round(ox / CELL)
                    snap_cells_y = round(oy / CELL)

                    # Aplicar moviments
                    if snap_cells_x > 0:
                        state = apply_move(puzzle, state, (dragging, "E", snap_cells_x))
                    elif snap_cells_x < 0:
                        state = apply_move(puzzle, state, (dragging, "W", -snap_cells_x))

                    if snap_cells_y > 0:
                        state = apply_move(puzzle, state, (dragging, "S", snap_cells_y))
                    elif snap_cells_y < 0:
                        state = apply_move(puzzle, state, (dragging, "N", -snap_cells_y))

                    solved = is_goal(puzzle, state)
                    dragging = None
                    drag_offset_px = (0.0, 0.0)
                    drag_axis = None

        draw_board(screen, puzzle, state, dragging, drag_offset_px, solved)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Ús: python3 {sys.argv[0]} <puzzle.json>")
        sys.exit(1)

    json_path = Path(sys.argv[1])
    pz = Puzzle.from_json(json_path.read_text())
    run_game(pz)
