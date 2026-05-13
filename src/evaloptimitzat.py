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
    pixi run python src/eval.py puzzles/sample1.json           # construeix el graf
    pixi run python3 src/eval.py puzzles/sample1.graphml        # carrega el graf ja construït
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

W_PATH         = 0.40
W_ENTROPY      = 0.15
W_MODULARITY   = 0.15
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
    n = g.num_vertices()
    if n <= 1: return 0.0
    # Obtenim l'histograma de graus directament des de C++
    _, counts = gt.vertex_hist(g, "out")
    counts_data = counts.a if hasattr(counts, 'a') else counts
    counts_nonzero = counts_data[counts_data > 0]
    
    entropy = sum(-(c / n) * math.log2(c / n) for c in counts_nonzero)
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
    try:
        # Louvain o Label Propagation són ordres de magnitud més ràpids per grafs grans
        prop = gt.label_propagation(g)
        Q = gt.modularity(g, prop)
        return float(max(0.0, min(Q, 1.0)))
    except:
        return 0.2

    
def measure_eccentricity(g: gt.Graph, dist_map_arr: gt.PropertyMap) -> float:
    """
    M4 · Excentricitat relativa de l'estat inicial [0, 1].

    Mesura si l'inici és al centre (fàcil) o a la perifèria (difícil)
    del graf. En comptes d'aproximar el diàmetre amb l'excentricitat
    de l'inici (que sempre dona 1.0), estimem el diàmetre real
    mostrejant DIAM_SAMPLE_SIZE nodes aleatoris i fent BFS des de
    cadascun. Això dona una estimació robusta a cost controlat.
    """
    # Usem el mapa de distàncies ja calculat per estalviar un BFS
    finite = dist_map_arr.a[dist_map_arr.a < 2**30]
    if len(finite) == 0: return 0.0
    ecc_start = finite.max()
    # El pseudo-diàmetre és gairebé instantani
    diam, _ = gt.pseudo_diameter(g)
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

    a) Distància mitjana: normalitzem per REF_PATH_LEN (referència
       absoluta) en comptes de path_len. Això evita que puzzles amb
       1 sol goal obtinguin automàticament M5 = 1.0 pel fet que
       dist(inici → goal) == path_len per definició.

       Exemple del problema anterior:
         path_len = 4, dist_goal = 4 → fracció = 4/4 = 1.0  (incorrecte)
       Amb la correcció:
         path_len = 4, dist_goal = 4 → fracció = 4/50 = 0.08 (correcte)

    b) Abundància: molts goals indiquen que quasi qualsevol
       configuració és vàlida. Apliquem un factor d'escassetat
       que val 1.0 quan hi ha 1 goal i decau logarítmicament.

    M5 = mitjana(fraccions) × factor_escassetat
    """
    if not goal_vertices:
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
            # Normalitzem per REF_PATH_LEN, no per path_len
            fractions.append(min((len(vlist) - 1) / REF_PATH_LEN, 1.0))

    if not fractions:
        return 0.0

    avg_fraction = sum(fractions) / len(fractions)

    # Factor d'escassetat: decau com 1 / log2(n_goals + 1)
    # 1 goal    → factor 1.00
    # 10 goals  → factor 0.29
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


def evaluate(puzzle: Puzzle, g: gt.Graph, verbose: bool = False) -> float:
    """
    Avalua el puzzle segons l'enfocament d'Expert: 
    Densitat, Estructura de Fases i Complexitat de Decisió.
    """
    # 1. Extracció de dades clau del graf
    try:
        is_start_arr = g.vp["is_start"].a
        is_goal_arr = g.vp["is_goal"].a
        start_idx = int(is_start_arr.argmax())
        goal_indices = list(is_goal_arr.nonzero()[0])
        
        if not goal_indices:
            return 0.0

        # Un sol BFS per a tot el càlcul
        dist_map = gt.shortest_distance(g, source=g.vertex(start_idx))
        
        # Trobar el camí més curt al goal més proper
        target_goal_idx = min(goal_indices, key=lambda idx: dist_map.a[idx])
        v_list, _ = gt.shortest_path(g, g.vertex(start_idx), g.vertex(target_goal_idx))
        path_vertices = [int(v) for v in v_list]
        path_len = len(path_vertices) - 1
    except Exception as e:
        if verbose: print(f"Error en processar el graf: {e}")
        return 0.0

    # --- MÈTRIQUES D'EXPERIÈNCIA (Lògica Expert) ---

    # A. DENSITAT COGNITIVA
    # Premia camins llargs en grafs que no són "massa" gegants.
    log_size = math.log10(g.num_vertices() + 1)
    m_density = float(min((path_len / log_size) / 8.0, 1.0))

    # B. ESTRUCTURA DE FASES (Modularitat + Excentricitat)
    # Detecta si el puzzle es divideix en "etapes".
    try:
        prop = gt.label_propagation(g)
        m_modul = float(gt.modularity(g, prop))
    except:
        m_modul = 0.2
    
    # Excentricitat: l'inici està realment lluny de la perifèria?
    finite_dists = dist_map.a[dist_map.a < 2**30]
    ecc_start = float(finite_dists.max()) if len(finite_dists) > 0 else 1.0
    diam, _ = gt.pseudo_diameter(g)
    m_ecc = float(ecc_start / diam) if diam > 0 else 0.5
    
    m_structure = (m_modul * 0.6) + (m_ecc * 0.4)

    # C. LLIBERTAT DE MOVIMENT
    # Mirem el grau mitjà (quantes opcions té el jugador per node).
    # Un puzzle on només pots fer 1 moviment sempre és avorrit.
    avg_degree = float(g.get_out_degrees(g.get_vertices()).mean())
    m_freedom = float(min(avg_degree / 3.5, 1.0)) 

    # D. MAGNITUD (Bonus per complexitat absoluta)
    m_magnitude = float(min(log_size / 6.5, 1.0))

    # --- PESOS FINALS ---
    score_raw = (0.40 * m_density + 
                 0.30 * m_structure + 
                 0.15 * m_freedom + 
                 0.15 * m_magnitude)

    # Penalització per Linealitat (Si és un "tub", resta)
    path_avg_degree = float(g.get_out_degrees(path_vertices).mean()) if path_vertices else 0
    p_linearity = 0.0
    if avg_degree > 0:
        p_linearity = 0.15 * max(0.0, 1.0 - (path_avg_degree / avg_degree))

    score_final = float(max(0.0, score_raw - p_linearity))

    # Arrodoniment final a 5 estrelles
    stars = round(score_final * 5.0, 2)
    stars = max(0.0, min(5.0, stars))

    if verbose:
        print(f"\n--- INFORME EXPERT ---")
        print(f"Mida Graf: {g.num_vertices()} nodes")
        print(f"Solució: {path_len} moviments")
        print(f"Densitat (Dificultat): {m_density:.2f}")
        print(f"Estructura (Fases): {m_structure:.2f}")
        print(f"Llibertat (Opcions): {m_freedom:.2f}")
        print(f"Magnitud (Volum): {m_magnitude:.2f}")
        print(f"Linealitat (Penalització): -{p_linearity:.2f}")
        print(f"★ NOTA FINAL: {stars} / 5.00")
        print(f"----------------------\n")

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
    parser.add_argument("puzzle", type=Path, help="Fitxer .json o .graphml del puzzle")
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Mostra el detall de totes les mesures",
    )
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
        g = None  # es construirà dins evaluate

    print(f"Avaluant '{args.puzzle.stem}'...")
    stars = evaluate(puzzle, g, verbose=args.verbose)

    if not args.verbose:
        print(f"★ Puntuació: {stars:.2f} / 5.00")