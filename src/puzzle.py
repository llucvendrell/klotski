"""
Definició dels elements bàsics del joc: peces, estats i trencaclosques.

Un puzzle d'aquest tipus té una alçada (H) i una amplada (W).
Conté un conjunt de peces, cadascuna amb una forma (poliominó)
i una posició inicial. També pot tenir parets (walls) que són
cel·les que cap peça pot ocupar. L'objectiu és situar certes
peces en posicions concretes (goals).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping


# Tipus de dades per a coordenades: (x, y)
Coord = tuple[int, int]

# Tipus de dades per a la clau de l'estat (canonicalització)
StateKey = tuple[Coord, ...]


@dataclass(frozen=True, order=True)
class Piece:
    """
    Una peça es defineix com un poliominó: un conjunt de coordenades relatives.
    Per convicció, s'ordenen i es normalitzen perquè el mínim de x i y sigui 0.
    Aquest objecte és immutable (frozen), cosa que permet usar-lo com a clau
    de coordenades.
    """

    coords: tuple[Coord, ...]

    def __init__(self, *coords: Coord) -> None:
        object.__setattr__(self, "coords", coords)
        if len(self.coords) == 0:
            raise ValueError("Una peça ha de tenir almenys una coordenada")
        for x, y in self.coords:
            if x < 0 or y < 0:
                raise ValueError(f"Coordenada negativa: ({x}, {y})")
        if len(set(self.coords)) != len(self.coords):
            raise ValueError("Coordenades repetides")
        if self.coords != tuple(sorted(self.coords)):
            raise ValueError("Les coordenades no estan ordenades")
        xs = [x for x, y in self.coords]
        ys = [y for x, y in self.coords]
        if min(xs) != 0 or min(ys) != 0:
            raise ValueError("La peça no està normalitzada (min x o min y != 0)")

    @staticmethod
    def normalized(coords: list[Coord]) -> Piece:
        """Crea una peça normalitzada a partir de coordenades arbitràries."""
        if len(coords) == 0:
            raise ValueError("Una peça ha de tenir almenys una coordenada")
        min_x = min(x for x, y in coords)
        min_y = min(y for x, y in coords)
        norm = sorted(set((x - min_x, y - min_y) for x, y in coords))
        return Piece(*norm)


@dataclass(frozen=True)
class State:
    """
    Representa una disposició de les peces en el taulell.
    Guardem les posicions (x, y) de cada peça en l'ordre en què
    estan definides al puzzle.
    """

    positions: tuple[Coord, ...]


class Puzzle:
    """
    Defineix un trencaclosques complet.
    """

    def __init__(
        self,
        W: int,
        H: int,
        pieces: tuple[Piece, ...],
        start: State,
        goals: Mapping[int, Coord],
        walls: tuple[Coord, ...] = (),
    ) -> None:
        self.W = W
        self.H = H
        self.pieces = pieces
        self.start = start
        self.goals = goals
        self.walls = walls

        # Validacions bàsiques
        if len(self.pieces) != len(self.start.positions):
            raise ValueError("El número de peces i posicions inicials no coincideix")

        # Peces en ordre canònic: (forma, posició_inicial)
        pairs = list(zip(self.pieces, self.start.positions))
        if pairs != sorted(pairs):
            raise ValueError("Les peces no estan en ordre canònic")

    def to_json(self, indent: int | None = None) -> str:
        """Serialitza el puzzle a format JSON canònic."""
        obj = {
            "W": self.W,
            "H": self.H,
            "walls": [list(c) for c in self.walls],
            "pieces": [[list(c) for c in p.coords] for p in self.pieces],
            "start": [list(c) for c in self.start.positions],
            "goals": [{"i": i, "pos": list(p)} for i, p in self.goals.items()],
        }
        return json.dumps(obj, indent=indent, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def from_json(data: str) -> Puzzle:
        """Crea un puzzle a partir d'un string JSON."""
        obj = json.loads(data)
        pieces = tuple(Piece(*[tuple(c) for c in coords]) for coords in obj["pieces"])
        start = State(tuple((c[0], c[1]) for c in obj["start"]))
        goals = {g["i"]: (g["pos"][0], g["pos"][1]) for g in obj["goals"]}
        walls = tuple((c[0], c[1]) for c in obj["walls"])
        return Puzzle(obj["W"], obj["H"], pieces, start, goals, walls)

    def hash(self) -> str:
        """Retorna un hash SHA-256 únic per a aquest puzzle."""
        return hashlib.sha256(self.to_json().encode()).hexdigest()
