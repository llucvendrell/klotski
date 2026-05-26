
import sys
from pathlib import Path
sys.path.append("src")
from generateultim import inverse_bfs, State
from puzzle import Puzzle

# Case 1: Simple 3x3 board
W, H = 3, 3
pieces = [[[0,0]]] # One 1x1 piece
goal_positions = [(2, 2)]
goal_idx = 0
walls = set()
groups = [(0, 1)]

stats = inverse_bfs(W, H, pieces, goal_positions, goal_idx, walls, groups)
print(f"Stats: {stats}")
