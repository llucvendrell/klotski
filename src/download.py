"""
Descarrega puzzles del repositori compartit.
 
Ús:
    python src/download.py                  # descarrega tots els puzzles disponibles
    python src/download.py <id>             # descarrega un puzzle concret
"""
 
from __future__ import annotations
 
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
 
from puzzle import Puzzle
 
BASE_URL = "https://klotski.pauek.dev/api"
PUZZLES_DIR = Path("puzzles")
 
 
def get_ids() -> list[str]:
    """Obté la llista dels IDs dels 100 puzzles amb millor valoració."""
    with urllib.request.urlopen(f"{BASE_URL}/puzzles") as response:
        return json.loads(response.read())
 
 
def get_puzzle(puzzle_id: str) -> dict:
    """Descarrega un puzzle concret per ID i retorna el JSON del puzzle."""
    url = f"{BASE_URL}/puzzles/{puzzle_id}"
    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read())
    return data["puzzle"]
 
 
def save_puzzle(puzzle_id: str, puzzle: dict) -> Path:
    """Desa un puzzle com a fitxer .json a la carpeta puzzles/."""
    PUZZLES_DIR.mkdir(exist_ok=True)
    path = PUZZLES_DIR / f"{puzzle_id}.json"
    path.write_text(json.dumps(puzzle))
    return path
 
 
def download_one(puzzle_id: str) -> None:
    """Descarrega, valida i desa un puzzle concret."""
    short_id = puzzle_id[:8]
    try:
        puzzle_dict = get_puzzle(puzzle_id)
        Puzzle.from_json(json.dumps(puzzle_dict))  # validem que el JSON és correcte
        path = save_puzzle(puzzle_id, puzzle_dict)
        print(f"  [✓] {short_id}  →  {path}")
    except urllib.error.HTTPError as e:
        print(f"  [✗] {short_id}: error HTTP {e.code}", file=sys.stderr)
    except urllib.error.URLError as e:
        print(f"  [✗] {short_id}: error de connexió ({e.reason})", file=sys.stderr)
    except Exception as e:
        print(f"  [✗] {short_id}: {e}", file=sys.stderr)
 
 
def download_all() -> None:
    """Descarrega tots els puzzles disponibles al repositori."""
    print("Obtenint llista de puzzles...")
    ids = get_ids()
    print(f"Trobats {len(ids)} puzzles\n")
    for i, puzzle_id in enumerate(ids, start=1):
        print(f"[{i:3}/{len(ids)}]", end=" ")
        download_one(puzzle_id)
 
 
if __name__ == "__main__":
    if len(sys.argv) == 1:
        download_all()
    elif len(sys.argv) == 2:
        download_one(sys.argv[1])
    else:
        print(f"Ús: python {sys.argv[0]} [id]")
        sys.exit(1)
 