"""
Envia la valoració d'un o tots els puzzles al repositori compartit calculant-la directament.
Usa eval.py propi (evaloptimitzatbo.py) i el teu token fix correcte.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import graph_tool.all as gt  # type: ignore[import-untyped]

from evaloptimitzatbo import evaluate
from puzzle import Puzzle

BASE_URL    = "https://klotski.pauek.dev"
PUZZLES_DIR = Path("puzzles")
TOKEN       = "019d90b1-6aaf-7000-9d26-6103afa10285"  # El teu token correcte


def load_puzzle_and_graph(puzzle_id: str) -> tuple[str, Puzzle, gt.Graph | None] | None:
    """Troba el fitxer i extreu l'ID exactament com ho fa el codi d'ells."""
    candidates: list[tuple[Path, str]] = []
    for p in PUZZLES_DIR.glob(f"*{puzzle_id}*"):
        if p.suffix == ".graphml":
            candidates.append((p, "graphml"))
        elif p.suffix == ".json":
            candidates.append((p, "json"))

    candidates.sort(key=lambda x: (x[1] != "graphml",))

    for path, fmt in candidates:
        full_id = path.stem.split("_")[-1]

        if fmt == "graphml":
            print(f"\n[+] Carregant graf precalculat '{path.name}'...")
            g = gt.load_graph(str(path))
            puzzle = Puzzle.from_json(g.gp["puzzle"])
            return full_id, puzzle, g
        else:
            print(f"\n[+] Carregant puzzle JSON '{path.name}'...")
            puzzle = Puzzle.from_json(path.read_text())
            return full_id, puzzle, None

    print(f"  [✗] Error: No s'ha trobat cap fitxer per a '{puzzle_id}'.", file=sys.stderr)
    return None


def send_rating(puzzle_id: str, stars: float, token: str) -> None:
    """Envia el vot recreant el comportament d'èxit del curl amb l'ID de 64 caràcters."""
    full_id = str(puzzle_id).strip()
    url = f"{BASE_URL}/api/puzzles/{full_id}/votes"
    
    stars_int = int(round(stars))
    payload = f'{{"stars": {stars_int}}}'
    body = payload.encode("utf-8")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token.strip()}"
    }
    
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST"
    )
    
    with urllib.request.urlopen(request) as response:
        response.read()


def rate_one(puzzle_id: str, token: str, *, dry_run: bool = False, verbose: bool = False) -> bool:
    """Executa l'avaluació en temps real i envia el resultat."""
    result = load_puzzle_and_graph(puzzle_id)
    if result is None:
        return False

    full_id, puzzle, g = result

    try:
        stars, raw_score = evaluate(puzzle, g, verbose)
    except Exception as e:
        print(f"  [✗] Error en avaluar el puzzle ({e})", file=sys.stderr)
        return False

    if dry_run:
        print(f"  [★] {full_id[:8]}: {stars} / 5 (Bruta: {raw_score:.2f}) -> Mode dry-run.")
        return True

    try:
        send_rating(full_id, stars, token)
        print(f"  [✓] Enviada correctament la valoració de {stars} estrelles per al puzzle '{full_id[:8]}'.")
        return True
    except urllib.error.HTTPError as e:
        print(f"  [! ] Error HTTP {e.code} enviant la valoració al servidor.", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  [! ] Error en la connexió: {e}", file=sys.stderr)
        return False


# ── Modificació del CLI per admetre --all o ID individual ─────────────────────


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Avalua en viu i envia la valoració d'un o tots els puzzles")
    parser.add_argument("id", metavar="ID", nargs="?", default=None, help="Identificador del puzzle individual")
    parser.add_argument("--all", action="store_true", help="Avalua i envia TOTS els puzzles de la carpeta")
    parser.add_argument("--dry-run", action="store_true", help="Avalua localment sense enviar")
    parser.add_argument("--verbose", "-v", action="store_true", help="Mostra l'informe complet de mètriques")
    args = parser.parse_args()

    if not args.all and args.id is None:
        parser.error("Has d'especificar l'ID d'un puzzle o fer servir l'argument --all")

    if args.all:
        vistos = set()
        extensions_valides = {".json", ".graphml"}
        
        puzzles_a_processar = []
        for p in PUZZLES_DIR.glob("*"):
            if p.suffix in extensions_valides:
                full_id = p.stem.split("_")[-1]
                if full_id not in vistos:
                    vistos.add(full_id)
                    puzzles_a_processar.append(full_id)

        if not puzzles_a_processar:
            print(f"No s'ha trobat cap puzzle vàlid a la carpeta '{PUZZLES_DIR}/'.")
            sys.exit(0)

        total_puzzles = len(puzzles_a_processar)
        print(f"S'han trobat {total_puzzles} puzzles únics a processar.")
        
        exits = 0
        ultim_id_enviat = "Cap de moment"

        # Protegim el bucle amb un try-except general per si s'atura el programa a la meitat
        try:
            for i, p_id in enumerate(puzzles_a_processar, 1):
                print(f"\n--- [Puzzle {i}/{total_puzzles}] ---")
                
                # Executem la valoració
                if rate_one(p_id, TOKEN, dry_run=args.dry_run, verbose=args.verbose):
                    exits += 1
                    ultim_id_enviat = p_id  # 🟢 El xivato guarda l'ID de l'últim que ha funcionat
                
                # XIVATO EN TEMPS REAL: Mostra el progrés actualitzat després de cada puzzle
                print(f"  [📢 XIVATO] Estat actual: {exits} enviats correctament. Últim amb èxit: {ultim_id_enviat[:8]}")

        except KeyboardInterrupt:
            # Si prems Ctrl + C a la terminal, l'script es para ordenadament i et avisa
            print(f"\n\n🛑 PROGRES INTERROMPUT PER L'USUARI (Ctrl + C)")
            print(f"────────────────────────────────────────────────────")
            print(f"  Total enviats abans d'aturar: {exits} / {total_puzzles}")
            print(f"  👉 L'ÚLTIM PUZZLE ENVIAT AMB ÈXIT HA ESTAT: {ultim_id_enviat}")
            print(f"────────────────────────────────────────────────────")
            sys.exit(0)
            
        print(f"\n====================================================")
        print(f" 🏁 Procés completat al 100%!")
        print(f" Total global: {exits}/{total_puzzles} vots enviats correctament.")
        print(f"====================================================")

    else:
        print(f"Avaluant '{args.id[:8]}'...")
        success = rate_one(args.id, TOKEN, dry_run=args.dry_run, verbose=args.verbose)
        if not success:
            sys.exit(1)