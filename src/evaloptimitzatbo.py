"""
Avalua un puzzle de peces lliscants i li assigna una puntuació d'interès (0–5 estrelles).

Principis de disseny:
  1. Un camí llarg sempre puntua alt, independentment de la mida del graf.
  2. Un graf gran és un indicador POSITIU (més complexitat).
  3. Pocs goals relatius als nodes és positiu.
  4. Zero BFS globals: totes les mesures usen l'array de graus i el camí de solve().

  Mesures:
    M1 · Longitud absoluta del camí   — escala sigmoidea, referència fixa
    M2 · Complexitat del graf         — log(nodes × arestes/nodes)
    M3 · Varietat de graus al camí    — coeficient de variació
    M4 · Ratio goals/nodes invertit   — pocs goals = difícil encertar
    M5 · Ratio de nodes sense sortida - 20% de dead-ends és un valor molt bo
    M6 · Punts de pas obligat (corredors) - 10% i 30% del camí

  Penalitzacions:
    P1 · Camí massa curt              — <10 moviments
    P2 · Graf massa petit             — <100 nodes
    P3 · Massa goals                  — >20% nodes finals

Ús:
    pixi run python src/evaloptimitzatbo.py puzzles/sample1.json
    pixi run python src/evaloptimitzatbo.py puzzles/sample1.graphml
    pixi run python src/evaloptimitzatbo.py puzzles/sample1.json --verbose
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import graph_tool.all as gt  # type: ignore[import-untyped]

from graph_eficientcopybo import build_graph
from puzzle import Puzzle


# ── Pesos (han de sumar 1.0) ──────────────────────────────────────────────────

W_PATH      = 0.35   # camí llarg és important
W_COMPLEX   = 0.20   # complexitat del graf
W_VARIETY   = 0.15   # varietat al camí
W_GOALS     = 0.10   # escassetat dels goals
W_DEADENDS  = 0.10   # ratio de callejons sense sortida
W_BOTTLENEK = 0.10   # punts de pas obligat (corredors)

# ── Penalitzacions ────────────────────────────────────────────────────────────

MAX_PENALTY_SHORT  = 0.25
MAX_PENALTY_SMALL  = 0.20
MAX_PENALTY_GOALS  = 0.15

SHORT_PATH_THRESHOLD  = 10     # moviments mínims per no penalitzar
SMALL_GRAPH_THRESHOLD = 100    # nodes mínims per no penalitzar
GOAL_RATIO_MAX        = 0.30   # >30% de nodes finals → penalitza

# ── Referència per M1 ────────────────────────────────────────────────────────

# Valors de referència per a la sigmoide de M1:
# path_len = 10  → ~0.27
# path_len = 20  → ~0.50
# path_len = 40  → ~0.73
# path_len = 60  → ~0.83
# path_len = 100 → ~0.92
SIGMOID_CENTER = 15.0   # camí de 15 moviments → puntuació 0.5
SIGMOID_SLOPE  = 0.10   # pendent de la sigmoide


# ── Mesures individuals ───────────────────────────────────────────────────────


def measure_path_length(path_len: int) -> float:
    """
    M1 · Longitud absoluta del camí [0, 1].  O(1).

    Usem una funció sigmoidea amb referència fixa (independent de la mida
    del graf). Això garanteix que un camí de 52 moviments sempre puntui
    alt (~0.87), independentment de si el graf té 100 o 1M nodes.

    sigmoid(x) = 1 / (1 + exp(-k*(x - x0)))
      x0 = SIGMOID_CENTER = 20  (camí de 20 moviments → 0.5)
      k  = SIGMOID_SLOPE  = 0.08

    Escala orientativa:
       5 mov → 0.23    10 mov → 0.31    20 mov → 0.50
      30 mov → 0.67    40 mov → 0.77    52 mov → 0.85
      70 mov → 0.92   100 mov → 0.97
    """
    if path_len == 0:
        return 0.0
    return 1.0 / (1.0 + math.exp(-SIGMOID_SLOPE * (path_len - SIGMOID_CENTER)))


def measure_complexity(n_nodes: int, n_edges: int) -> float:
    """
    M2 · Complexitat del graf [0, 1].  O(1).

    Combina la mida del graf i la seva densitat relativa en una sola mesura:
        complexity = log2(n_nodes) × (n_edges / n_nodes) / REF

    Un graf gran amb bona densitat d'arestes indica un espai d'estats
    ric i complex. Normalitzem per un valor de referència raonable.

    Valors típics:
      16 nodes, 24 arestes  → log2(16) × 1.5 = 6.0   → ~0.08
      35k nodes, 78k arestes → log2(35k) × 2.2 = 33   → ~0.44
      1.1M nodes, 3.3M arestes → log2(1.1M) × 2.9 = 58 → ~0.77
    """
    if n_nodes <= 1:
        return 0.0
    density = n_edges / n_nodes
    raw = math.log2(n_nodes) * density
    # Normalitzem: log2(1M) × 3 ≈ 60 és un valor excel·lent
    return min(raw / 75.0, 1.0)


def measure_path_variety(
    degree_array: np.ndarray,
    path_indices: list[int],
) -> float:
    """
    M3 · Varietat de graus al llarg del camí [0, 1].  O(path_len).

    Mesura si el camí passa per estats de connectivitat molt diferent:
    alguns amb moltes opcions (interseccions), altres amb poques (callejons).
    Un camí monòton és avorrit; un camí variat és interessant.

    Usem el coeficient de variació (std/mean) normalitzat a [0,1].
    """
    if len(path_indices) < 2:
        return 0.0
    path_deg = degree_array[np.array(path_indices, dtype=np.int64)]
    mean = float(path_deg.mean())
    if mean == 0:
        return 0.0
    cv = float(path_deg.std()) / mean
    return min(cv, 1.0)


def measure_goal_scarcity(n_goals: int, n_nodes: int) -> float:
    """
    M4 · Escassetat dels goals [0, 1].  O(1).

    Pocs goals = difícil encertar la solució per casualitat = puzzle més bo.
    """
    if n_nodes == 0:
        return 0.0
    ratio = n_goals / n_nodes
    return math.exp(-5.0 * ratio)


def measure_dead_ends(degree_array: np.ndarray, n_nodes: int) -> float:
    """
    M5 · Ratio de callejons sense sortida [0, 1].  O(V).

    Comptem els nodes amb grau 1 (excloent el node inicial si té grau 1).
    Un ratio alt de dead-ends indica que el puzzle té moltes rutes falses.
    Normalitzem: un 20% de dead-ends és un valor molt bo.
    """
    if n_nodes <= 2:
        return 0.0
    n_dead = int(np.sum(degree_array == 1))
    ratio = n_dead / n_nodes
    return min(ratio / 0.20, 1.0)


def measure_bottlenecks(degree_array: np.ndarray, path_indices: list[int]) -> float:
    """
    M6 · Punts de pas obligat (corredors) [0, 1].  O(path_len).

    Nodes al camí amb grau 2: són "cols" o corredors on només pots
    anar endavant o enrere. Tenir-ne alguns fa que el puzzle se senti
    estructurat, però massa fa que sigui trivial.
    Format ideal: entre el 10% i el 30% del camí.
    """
    if not path_indices:
        return 0.0
    path_deg = degree_array[np.array(path_indices, dtype=np.int64)]
    n_bottles = int(np.sum(path_deg == 2))
    ratio = n_bottles / len(path_indices)
    # Funció campana: màxim a 0.2, decau cap a 0 i 1.
    return math.exp(-15.0 * (ratio - 0.2) ** 2)


# ── Penalitzacions


def penalty_short_path(path_len: int) -> float:
    """P1 · Camí massa curt.  O(1)."""
    if path_len >= SHORT_PATH_THRESHOLD:
        return 0.0
    return MAX_PENALTY_SHORT * (1.0 - path_len / SHORT_PATH_THRESHOLD)


def penalty_small_graph(n_nodes: int) -> float:
    """P2 · Graf massa petit.  O(1)."""
    if n_nodes >= SMALL_GRAPH_THRESHOLD:
        return 0.0
    return MAX_PENALTY_SMALL * (1.0 - n_nodes / SMALL_GRAPH_THRESHOLD)


def penalty_too_many_goals(n_goals: int, n_nodes: int) -> float:
    """P3 · Massa goals.  O(1)."""
    if n_nodes == 0:
        return 0.0
    ratio = n_goals / n_nodes
    if ratio <= GOAL_RATIO_MAX:
        return 0.0
    excess = (ratio - GOAL_RATIO_MAX) / (1.0 - GOAL_RATIO_MAX)
    return MAX_PENALTY_GOALS * min(excess, 1.0)


# ── Escala final 


def strict_scale(score: float) -> float:
    """
    Escala lineal: la puntuació base es mapeja directament a estrelles.
    La sigmoide de M1 ja garanteix que puzzles bons puntuen alt.
      0.5 → 2.5★   0.7 → 3.5★   0.8 → 4.0★   0.9 → 4.5★
    """
    return score


# ── Avaluació global 


def evaluate(
    puzzle: Puzzle,
    g: gt.Graph | None = None,
    verbose: bool = False,
) -> tuple[int, float]:
    """
    Avaluació completa. Retorna (stars, raw_score).
    """
    if g is None:
        g = build_graph(puzzle)

    # ── Mínim camí usant el graf (Molt ràpid) ────────────────────────
    is_goal_prop = g.vp["is_goal"]
    goal_nodes   = np.where(is_goal_prop.a)[0]
    
    # Busquem el camí mínim a qualsevol goal
    v_start = g.vertex(0)  # El primer node sempre és l'inicial
    path_len = float('inf')
    best_path_indices = []

    # BFS des de v_start a tots els nodes del graf
    dist_map = gt.shortest_distance(g, source=v_start)
    
    # Busquem el node final més proper
    min_dist = float('inf')
    best_v_goal = None
    
    for v_goal_idx in goal_nodes:
        d = dist_map[v_goal_idx]
        if d < min_dist:
            min_dist = d
            best_v_goal = v_goal_idx
    
    if best_v_goal is not None:
        path_len = min_dist
        # Obtenim els índexs dels nodes del camí
        v_list, e_list = gt.shortest_path(g, v_start, best_v_goal)
        path_indices = [int(v) for v in v_list]
    else:
        path_len = 0
        path_indices = []

    n_nodes  = g.num_vertices()
    n_edges  = g.num_edges()
    state_prop    = g.vp["state"]

    # ── Arrays numpy d'una passada
    n_goals      = int(is_goal_prop.a.sum())
    degree_prop  = g.degree_property_map("out")
    degree_array = degree_prop.a.copy()

    # ── Sis mesures
    m_path    = measure_path_length(path_len)
    m_complex = measure_complexity(n_nodes, n_edges)
    m_variety = measure_path_variety(degree_array, path_indices)
    m_goals   = measure_goal_scarcity(n_goals, n_nodes)
    m_dead    = measure_dead_ends(degree_array, n_nodes)
    m_bottle  = measure_bottlenecks(degree_array, path_indices)

    score_raw = (
        W_PATH      * m_path    +
        W_COMPLEX   * m_complex +
        W_VARIETY   * m_variety +
        W_GOALS     * m_goals   +
        W_DEADENDS  * m_dead    +
        W_BOTTLENEK * m_bottle
    )

    # ── Tres penalitzacions ───────────────────────────────────────────
    pen_short = penalty_short_path(path_len)
    pen_small = penalty_small_graph(n_nodes)
    pen_goals = penalty_too_many_goals(n_goals, n_nodes)

    score_penalized = max(0.0, score_raw - pen_short - pen_small - pen_goals)
    raw   = strict_scale(score_penalized) * 5.0
    stars = max(0, min(5, round(raw)))

    if verbose:
        _print_report(
            n_nodes, n_edges, n_goals, path_len,
            m_path, m_complex, m_variety, m_goals, m_dead, m_bottle,
            pen_short, pen_small, pen_goals,
            score_raw, score_penalized, raw, stars,
        )

    return stars, raw


def _print_report(
    n_nodes, n_edges, n_goals, path_len,
    m_path, m_complex, m_variety, m_goals, m_dead, m_bottle,
    pen_short, pen_small, pen_goals,
    score_raw, score_penalized, raw, stars,
) -> None:
    print("─" * 52)
    print(f"  Nodes del graf        : {n_nodes}")
    print(f"  Arestes               : {n_edges}")
    print(f"  Estats finals (goals) : {n_goals}")
    print(f"  Longitud camí mínim   : {path_len} moviments")
    print("─" * 52)
    print(f"  M1 longitud camí      : {m_path:.3f}  (pes {W_PATH:.0%})")
    print(f"  M2 complexitat graf   : {m_complex:.3f}  (pes {W_COMPLEX:.0%})")
    print(f"  M3 varietat al camí   : {m_variety:.3f}  (pes {W_VARIETY:.0%})")
    print(f"  M4 escassetat goals   : {m_goals:.3f}  (pes {W_GOALS:.0%})")
    print(f"  M5 ratio dead-ends    : {m_dead:.3f}  (pes {W_DEADENDS:.0%})")
    print(f"  M6 bottlenecks        : {m_bottle:.3f}  (pes {W_BOTTLENEK:.0%})")
    print("─" * 52)
    print(f"  Puntuació bruta       : {score_raw:.3f}")
    if pen_short > 0:
        print(f"  P1 camí curt          : -{pen_short:.3f}  (menys de {SHORT_PATH_THRESHOLD} moviments)")
    if pen_small > 0:
        print(f"  P2 graf petit         : -{pen_small:.3f}  (menys de {SMALL_GRAPH_THRESHOLD} nodes)")
    if pen_goals > 0:
        print(f"  P3 massa goals        : -{pen_goals:.3f}  (>{GOAL_RATIO_MAX:.0%} de nodes finals)")
    print(f"  Puntuació penalitzada : {score_penalized:.3f}")
    print(f"  Puntuació escalada    : {strict_scale(score_penalized):.3f}")
    print("─" * 52)
    print(f"  ★ Puntuació final     : {stars} / 5  ({raw:.2f} abans d'arrodonir)")
    print("─" * 52)


# ── CLI ───────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Avalua l'interès d'un puzzle de peces lliscants (0–5 estrelles)"
    )
    parser.add_argument("puzzle", type=Path, help="Fitxer .json o .graphml del puzzle")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Mostra el detall de totes les mesures")
    args = parser.parse_args()

    if not args.puzzle.exists():
        print(f"Error: no s'ha trobat {args.puzzle}", file=sys.stderr)
        sys.exit(1)

    if args.puzzle.suffix == ".graphml":
        print(f"Carregant graf '{args.puzzle.stem}'...")
        g = gt.load_graph(str(args.puzzle))
        puzzle = Puzzle.from_json(g.gp["puzzle"])
    else:
        puzzle = Puzzle.from_json(args.puzzle.read_text())
        g = None

    print(f"Avaluant '{args.puzzle.stem}'...")
    stars, raw = evaluate(puzzle, g, verbose=args.verbose)

    if not args.verbose:
        print(f"★ Puntuació: {stars} / 5  ({raw:.2f} abans d'arrodonir)")