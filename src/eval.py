"""
Avalua un puzzle de peces lliscants i li assigna una puntuació d'interès (0–5 estrelles).

L'avaluació combina cinc mesures estructurals del graf d'estats i dues penalitzacions:

  Mesures (contribucions positives):
    M1 · Longitud del camí mínim       — dificultat directa
    M2 · Entropia del grau dels nodes  — riquesa estructural del graf
    M3 · Modularitat de comunitats     — presència de zones i fases
    M4 · Excentricitat mostrejada      — posició real de l'inici al graf
    M5 · Dificultat ponderada dels goals — penalitza goals abundants i propers

  Penalitzacions (contribucions negatives):
    P2 · Linealitat del camí           — penalitza si la solució és quasi única
    P3 · Goal massa proper             — penalitza si es pot acabar per accident

  Escala final:
    La puntuació base es passa per una corba quadràtica que comprimeix els
    valors mitjans i fa que només els puzzles genuïnament bons assoleixin
    puntuacions altes.

Ús:
    pixi run python src/eval.py puzzles/sample1.json
    pixi run python src/eval.py puzzles/sample1.json --verbose
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

import graph_tool.all as gt  # type: ignore[import-untyped]

from graph import build_graph
from logic import apply_move
from puzzle import Puzzle
from solve import solve


# ── Pesos de les cinc mesures (han de sumar 1.0) ──────────────────────────────

W_PATH         = 0.30
W_ENTROPY      = 0.20
W_MODULARITY   = 0.20
W_ECCENTRICITY = 0.15
W_GOAL_DIFF    = 0.15

# ── Paràmetres de les penalitzacions ─────────────────────────────────────────

MAX_PENALTY_LINEARITY = 0.25
MAX_PENALTY_NEAR_GOAL = 0.30
NEAR_GOAL_THRESHOLD   = 5

# ── Valors de referència ──────────────────────────────────────────────────────

REF_PATH_LEN      = 50     # moviments de referència per M1
MIN_PATH_LEN      = 15     # per sota d'aquí el puzzle és trivial
DIAM_SAMPLE_SIZE  = 200    # nodes a mostrejar per estimar el diàmetre (M4)
GOAL_SAMPLE_SIZE  = 100    # goals a mostrejar per M5 (evita O(n) shortest_paths)


# ── Mesures individuals ───────────────────────────────────────────────────────


def measure_path_length(path_len: int) -> float:
    """
    M1 · Longitud del camí mínim normalitzada a [0, 1].

    Escala logarítmica per reflectir la percepció humana de dificultat.
    Aplica un factor de penalització addicional si el camí és molt curt
    (< MIN_PATH_LEN): un puzzle de 5 moviments no és interessant.
    """
    if path_len == 0:
        return 0.0
    base = min(math.log(path_len + 1) / math.log(REF_PATH_LEN + 1), 1.0)
    if path_len < MIN_PATH_LEN:
        base *= path_len / MIN_PATH_LEN
    return base


def measure_entropy(g: gt.Graph) -> float:
    """
    M2 · Entropia de Shannon de la distribució de graus [0, 1].

    Mesura la variació estructural: un graf amb nodes molt connectats
    barrejats amb callejons sense sortida és més ric i enganyós.
    """
    n = g.num_vertices()
    if n <= 1:
        return 0.0

    freq: dict[int, int] = {}
    for v in g.vertices():
        d = v.out_degree()
        freq[d] = freq.get(d, 0) + 1

    entropy = sum(
        -(c / n) * math.log2(c / n)
        for c in freq.values()
    )
    max_entropy = math.log2(n)
    return entropy / max_entropy if max_entropy > 0 else 0.0


def measure_modularity(g: gt.Graph) -> float:
    """
    M3 · Modularitat de comunitats [0, 1].

    Detecta zones densament connectades internament (fases del puzzle).
    Usa l'algorisme de Louvain de graph-tool.

    A diferència del clustering (sempre 0 en grafs de puzzles per
    absència de triangles), la modularitat discrimina bé en qualsevol
    tipus de graf.
    """
    state = gt.minimize_blockmodel_dl(g, state_args={"deg_corr": False})
    b = state.get_blocks()
    Q = gt.modularity(g, b)
    return float(max(0.0, min(Q, 1.0)))


def measure_eccentricity(g: gt.Graph, start_v: gt.Vertex) -> float:
    """
    M4 · Excentricitat relativa de l'estat inicial [0, 1].

    Mesura si l'inici és al centre (fàcil) o a la perifèria (difícil)
    del graf. En comptes d'aproximar el diàmetre amb l'excentricitat
    de l'inici (que sempre dona 1.0), estimem el diàmetre real
    mostrejant DIAM_SAMPLE_SIZE nodes aleatoris i fent BFS des de
    cadascun. Això dona una estimació robusta a cost controlat.
    """
    dist_from_start = gt.shortest_distance(g, source=start_v)
    finite = [d for d in dist_from_start.a if d < 2**30]
    if not finite:
        return 0.0
    ecc_start = max(finite)

    # Estimació del diàmetre per mostreig
    all_vertices = list(g.vertices())
    sample = random.sample(
        all_vertices,
        min(DIAM_SAMPLE_SIZE, len(all_vertices))
    )
    diam = ecc_start
    for v in sample:
        d = gt.shortest_distance(g, source=v)
        fd = [x for x in d.a if x < 2**30]
        if fd:
            diam = max(diam, max(fd))

    return ecc_start / diam if diam > 0 else 0.0


def measure_goal_difficulty(
    g: gt.Graph,
    start_v: gt.Vertex,
    goal_vertices: list[gt.Vertex],
    path_len: int,
) -> float:
    """
    M5 · Dificultat ponderada dels goals [0, 1].

    Dos factors penalitzen simultàniament:

    a) Distància mitjana: goals propers contribueixen poc
       (fracció = dist / path_len)

    b) Abundància: molts goals indiquen que quasi qualsevol
       configuració és vàlida. Apliquem un factor d'escassetat
       que val 1.0 quan hi ha 1 goal i decau logarítmicament.

    M5 = mitjana(fraccions) × factor_escassetat
    """
    if not goal_vertices or path_len == 0:
        return 0.0

    # Mostregem per eficiència si hi ha molts goals
    sample = (
        random.sample(goal_vertices, GOAL_SAMPLE_SIZE)
        if len(goal_vertices) > GOAL_SAMPLE_SIZE
        else goal_vertices
    )

    fractions = []
    for goal_v in sample:
        vlist, _ = gt.shortest_path(g, start_v, goal_v)
        if vlist:
            fractions.append(min((len(vlist) - 1) / path_len, 1.0))

    if not fractions:
        return 0.0

    avg_fraction = sum(fractions) / len(fractions)

    # Factor d'escassetat: decau com 1 / log2(n_goals + 1)
    # 1 goal  → factor 1.00
    # 10 goals → factor 0.29
    # 100 goals → factor 0.15
    # 2412 goals → factor 0.09
    scarcity = 1.0 / math.log2(len(goal_vertices) + 1)

    return avg_fraction * scarcity


# ── Penalitzacions ────────────────────────────────────────────────────────────


def penalty_linearity(g: gt.Graph, path_indices: list[int]) -> float:
    """
    P2 · Penalitza si el camí òptim passa per zones poc connectades.

    Compara el grau mitjà dels nodes del camí amb el grau mitjà global.
    Un camí que passa per nodes amb molts menys veïns que la mitjana
    indica que la solució és quasi única i el puzzle és massa lineal.
    """
    if not path_indices:
        return 0.0
    global_avg = sum(v.out_degree() for v in g.vertices()) / g.num_vertices()
    if global_avg == 0:
        return 0.0
    path_avg = sum(g.vertex(i).out_degree() for i in path_indices) / len(path_indices)
    return MAX_PENALTY_LINEARITY * max(0.0, 1.0 - path_avg / global_avg)


def penalty_near_goal(
    g: gt.Graph,
    start_v: gt.Vertex,
    goal_vertices: list[gt.Vertex],
) -> float:
    """
    P3 · Penalitza si el goal més proper és massa accessible.

    Un goal a molt poca distància de l'inici pot ser resolt per
    accident, fent el puzzle trivial sense que el jugador ho sàpiga.
    La penalització és proporcional a quant per sota del llindar
    cau la distància mínima.
    """
    if not goal_vertices:
        return 0.0
    min_dist = min(
        len(gt.shortest_path(g, start_v, gv)[0]) - 1
        for gv in goal_vertices
    )
    if min_dist >= NEAR_GOAL_THRESHOLD:
        return 0.0
    return MAX_PENALTY_NEAR_GOAL * (1.0 - min_dist / NEAR_GOAL_THRESHOLD)


# ── Escala final ──────────────────────────────────────────────────────────────


def strict_scale(score: float) -> float:
    """
    Aplica una corba quadràtica a la puntuació base per fer l'escala
    més estricta: els valors mitjans es comprimeixen cap avall i només
    els puzzles genuïnament excel·lents assoleixen puntuacions altes.

    La corba és score² (sempre a [0,1]), que penalitza valors intermedis:
      0.5 → 0.25   (un puzzle mediocre treu 1.25★ en comptes de 2.5★)
      0.7 → 0.49   (un puzzle bo treu 2.45★)
      0.9 → 0.81   (un puzzle molt bo treu 4.05★)
      1.0 → 1.00   (un puzzle perfecte treu 5.00★)
    """
    return score ** 2


# ── Avaluació global ──────────────────────────────────────────────────────────


def evaluate(puzzle: Puzzle, verbose: bool = False) -> float:
    """
    Construeix el graf, calcula les cinc mesures i les dues penalitzacions,
    aplica l'escala estricta i retorna una puntuació de 0 a 5 estrelles.
    """
    g = build_graph(puzzle)
    moves = solve(g, puzzle)

    n_nodes  = g.num_vertices()
    n_edges  = g.num_edges()
    path_len = len(moves) if moves else 0

    is_start_prop = g.vp["is_start"]
    is_goal_prop  = g.vp["is_goal"]
    state_prop    = g.vp["state"]

    start_v: gt.Vertex | None = None
    goal_vertices: list[gt.Vertex] = []
    for v in g.vertices():
        if is_start_prop[v]:
            start_v = v
        if is_goal_prop[v]:
            goal_vertices.append(v)

    if start_v is None:
        raise ValueError("No s'ha trobat l'estat inicial al graf")

    n_goals = len(goal_vertices)

    # ── Cinc mesures ──────────────────────────────────────────────────
    m_path  = measure_path_length(path_len)
    m_ent   = measure_entropy(g)
    m_modul = measure_modularity(g)
    m_ecc   = measure_eccentricity(g, start_v)
    m_gdiff = measure_goal_difficulty(g, start_v, goal_vertices, path_len)

    score_raw = (
        W_PATH         * m_path  +
        W_ENTROPY      * m_ent   +
        W_MODULARITY   * m_modul +
        W_ECCENTRICITY * m_ecc   +
        W_GOAL_DIFF    * m_gdiff
    )

    # ── Penalitzacions ────────────────────────────────────────────────
    key_to_idx = {
        tuple(tuple(p) for p in json.loads(state_prop[v])): int(v)
        for v in g.vertices()
    }
    path_indices: list[int] = []
    if moves:
        current = puzzle.start
        path_indices.append(key_to_idx[current.positions])
        for move in moves:
            current = apply_move(puzzle, current, move)
            path_indices.append(key_to_idx[current.positions])

    pen_linear    = penalty_linearity(g, path_indices)
    pen_near_goal = penalty_near_goal(g, start_v, goal_vertices)

    score_penalized = max(0.0, score_raw - pen_linear - pen_near_goal)

    # ── Escala estricta i conversió a estrelles ───────────────────────
    stars = round(strict_scale(score_penalized) * 5.0, 2)

    if verbose:
        _print_report(
            n_nodes, n_edges, n_goals, path_len,
            m_path, m_ent, m_modul, m_ecc, m_gdiff,
            pen_linear, pen_near_goal,
            score_raw, score_penalized, stars,
        )

    return stars


def _print_report(
    n_nodes, n_edges, n_goals, path_len,
    m_path, m_ent, m_modul, m_ecc, m_gdiff,
    pen_linear, pen_near_goal,
    score_raw, score_penalized, stars,
) -> None:
    """Mostra un informe detallat de l'avaluació."""
    print("─" * 52)
    print(f"  Nodes del graf        : {n_nodes}")
    print(f"  Arestes               : {n_edges}")
    print(f"  Estats finals (goals) : {n_goals}")
    print(f"  Longitud camí mínim   : {path_len} moviments")
    print("─" * 52)
    print(f"  M1 longitud camí      : {m_path:.3f}  (pes {W_PATH:.0%})")
    print(f"  M2 entropia graus     : {m_ent:.3f}  (pes {W_ENTROPY:.0%})")
    print(f"  M3 modularitat        : {m_modul:.3f}  (pes {W_MODULARITY:.0%})")
    print(f"  M4 excentricitat inici: {m_ecc:.3f}  (pes {W_ECCENTRICITY:.0%})")
    print(f"  M5 dificultat goals   : {m_gdiff:.3f}  (pes {W_GOAL_DIFF:.0%})")
    print("─" * 52)
    print(f"  Puntuació bruta       : {score_raw:.3f}")
    if pen_linear > 0:
        print(f"  P2 linealitat camí    : -{pen_linear:.3f}  (solució massa única)")
    if pen_near_goal > 0:
        print(f"  P3 goal massa proper  : -{pen_near_goal:.3f}  (goal assolible per accident)")
    print(f"  Puntuació penalitzada : {score_penalized:.3f}")
    print(f"  Escala estricta (²)   : {score_penalized**2:.3f}")
    print("─" * 52)
    print(f"  ★ Puntuació final     : {stars:.2f} / 5.00")
    print("─" * 52)


# ── CLI ───────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Avalua l'interès d'un puzzle de peces lliscants (0–5 estrelles)"
    )
    parser.add_argument("puzzle", type=Path, help="Fitxer .json del puzzle")
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Mostra el detall de totes les mesures",
    )
    args = parser.parse_args()

    if not args.puzzle.exists():
        print(f"Error: no s'ha trobat {args.puzzle}", file=sys.stderr)
        sys.exit(1)

    puzzle = Puzzle.from_json(args.puzzle.read_text())
    print(f"Avaluant '{args.puzzle.stem}'...")

    stars = evaluate(puzzle, verbose=args.verbose)

    if not args.verbose:
        print(f"★ Puntuació: {stars:.2f} / 5.00")