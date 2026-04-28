"""
Descarrega puzzles del repositori compartit.
 
Ús:
    python src/download.py                  # descarrega tots els puzzles disponibles
    python src/download.py <id>             # descarrega un puzzle concret
"""
 
from __future__ import annotations
 
import json
import sys
import urllib.request
from pathlib import Path
 
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
    path = PUZZLES_DIR / f"{puzzle_id[:8]}.json"
    path.write_text(json.dumps(puzzle))
    return path
 
 
def download_one(puzzle_id: str) -> None:
    """Descarrega i desa un puzzle concret."""
    print(f"Descarregant {puzzle_id[:8]}...")
    puzzle = get_puzzle(puzzle_id)
    path = save_puzzle(puzzle_id, puzzle)
    print(f"Desat: {path}")
 
 
def download_all() -> None:
    """Descarrega tots els puzzles disponibles al repositori."""
    print("Obtenint llista de puzzles...")
    ids = get_ids()
    print(f"Trobats {len(ids)} puzzles")
    for puzzle_id in ids:
        download_one(puzzle_id)
 
 
if __name__ == "__main__":
    if len(sys.argv) == 1:
        download_all()
    elif len(sys.argv) == 2:
        download_one(sys.argv[1])
    else:
        print(f"Ús: python {sys.argv[0]} [id]")
        sys.exit(1)
 