# bot author: Gemini 3.1 Pro
import os
import sys
import socket
import time
import random

# The 35 free hexominoes defined as lists of (row, col) coordinates.
# Coordinates are given relative to the top-left of their bounding box.
SHAPES_DATA = [
    [(0,0), (0,1), (0,2), (0,3), (0,4), (0,5)], # 0
    [(0,0), (0,1), (0,2), (0,3), (0,4), (1,0)], # 1
    [(0,0), (0,1), (0,2), (0,3), (0,4), (1,1)], # 2
    [(0,0), (0,1), (0,2), (0,3), (0,4), (1,2)], # 3
    [(0,0), (0,1), (0,2), (0,3), (1,0), (1,1)], # 4
    [(0,0), (0,1), (0,2), (0,3), (1,0), (1,2)], # 5
    [(0,0), (0,1), (0,2), (0,3), (1,0), (1,3)], # 6
    [(0,0), (0,1), (0,2), (0,3), (1,0), (2,0)], # 7
    [(0,0), (0,1), (0,2), (0,3), (1,1), (1,2)], # 8
    [(0,0), (0,1), (0,2), (0,3), (1,1), (2,1)], # 9
    [(0,0), (0,1), (0,2), (0,3), (1,3), (1,4)], # 10
    [(0,0), (0,1), (0,2), (1,0), (1,1), (1,2)], # 11
    [(0,0), (0,1), (0,2), (1,0), (1,1), (2,0)], # 12
    [(0,0), (0,1), (0,2), (1,0), (1,1), (2,1)], # 13
    [(0,0), (0,1), (0,2), (1,0), (1,2), (1,3)], # 14
    [(0,0), (0,1), (0,2), (1,0), (1,2), (2,0)], # 15
    [(0,0), (0,1), (0,2), (1,1), (1,2), (1,3)], # 16
    [(0,0), (0,1), (0,2), (1,1), (2,0), (2,1)], # 17
    [(0,0), (0,1), (0,2), (1,1), (2,1), (3,1)], # 18
    [(0,0), (0,1), (0,2), (1,2), (1,3), (1,4)], # 19
    [(0,0), (0,1), (0,2), (1,2), (1,3), (2,2)], # 20
    [(0,0), (0,1), (0,2), (1,2), (1,3), (2,3)], # 21
    [(0,0), (0,1), (0,2), (1,2), (2,2), (2,3)], # 22
    [(0,0), (0,1), (1,0), (1,1), (1,2), (2,1)], # 23
    [(0,0), (0,1), (1,0), (1,1), (1,2), (2,2)], # 24
    [(0,0), (0,1), (1,1), (1,2), (1,3), (2,1)], # 25
    [(0,0), (0,1), (1,1), (1,2), (1,3), (2,2)], # 26
    [(0,0), (0,1), (1,1), (1,2), (1,3), (2,3)], # 27
    [(0,0), (0,1), (1,1), (1,2), (2,0), (2,1)], # 28
    [(0,0), (0,1), (1,1), (1,2), (2,1), (3,1)], # 29
    [(0,0), (0,1), (1,1), (1,2), (2,2), (2,3)], # 30
    [(0,0), (0,1), (1,1), (2,1), (2,2), (3,1)], # 31
    [(0,0), (0,1), (1,1), (2,1), (3,1), (3,2)], # 32
    [(0,1), (1,0), (1,1), (1,2), (1,3), (2,1)], # 33
    [(0,1), (1,0), (1,1), (1,2), (1,3), (2,2)]  # 34
]

class Placement:
    __slots__ = ['shape_idx', 'cells']
    def __init__(self, shape_idx, cells):
        self.shape_idx = shape_idx
        self.cells = cells

def get_variants(shape):
    """Generate all unique rotations and reflections of a given shape."""
    variants = set()
    for rot in range(4):
        for flip in (False, True):
            new_shape = []
            for r, c in shape:
                if flip:
                    c = -c
                # Rotate 90 degrees clockwise
                for _ in range(rot):
                    r, c = c, -r
                new_shape.append((r, c))
            
            # Normalize to top-left (0, 0)
            min_r = min(r for r, c in new_shape)
            min_c = min(c for r, c in new_shape)
            norm = tuple(sorted((r - min_r, c - min_c) for r, c in new_shape))
            variants.add(norm)
    return list(variants)

def generate_all_placements(w, h):
    """Generate all valid placements of all shapes on a w x h grid."""
    placements = []
    for shape_idx, shape in enumerate(SHAPES_DATA):
        variants = get_variants(shape)
        for var in variants:
            max_r = max(r for r, c in var)
            max_c = max(c for r, c in var)
            
            for r_off in range(h - max_r):
                for c_off in range(w - max_c):
                    cells = [(r_off + r) * w + (c_off + c) for r, c in var]
                    placements.append(Placement(shape_idx, cells))
    return placements

def solve_dlx(w, h, all_placements, start_time, time_limit=28.0):
    """
    Solve the Exact Cover problem using Knuth's Algorithm X with dicts.
    We use iterative deepening/restarts to avoid getting stuck in deep dead ends,
    randomizing the row order on each restart to increase shape diversity (inventory).
    """
    base_limit = 1000
    restart_limit = base_limit
    
    while time.time() - start_time < time_limit:
        random.shuffle(all_placements)
        
        X = {i: set() for i in range(w * h)}
        Y = {}
        for i, p in enumerate(all_placements):
            Y[i] = p.cells
            for cell in p.cells:
                X[cell].add(i)
                
        solution = []
        steps = 0
        
        def select(r):
            cols = []
            for j in Y[r]:
                for i in X[j]:
                    for k in Y[i]:
                        if k != j:
                            X[k].remove(i)
                cols.append(X.pop(j))
            return cols

        def deselect(r, cols):
            for j in reversed(Y[r]):
                X[j] = cols.pop()
                for i in X[j]:
                    for k in Y[i]:
                        if k != j:
                            X[k].add(i)

        def search():
            nonlocal steps
            if not X:
                return True
            steps += 1
            if steps > restart_limit:
                return False
            
            # Choose column with the fewest available rows to minimize branching
            c = min(X, key=lambda col: len(X[col]))
            if not X[c]:
                return False
            
            for r in list(X[c]):
                solution.append(r)
                cols = select(r)
                if search():
                    return True
                deselect(r, cols)
                solution.pop()
            return False

        if search():
            return solution, Y
        
        # Increase limit exponentially for the next random restart
        restart_limit = int(restart_limit * 1.5)
        
    return None, None

def main():
    bot_name = os.environ.get('BOTNAME')
    if not bot_name:
        sys.exit(1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(('localhost', 7474))
    except ConnectionRefusedError:
        sys.exit(1)

    # Send the bot name as the handshake
    sock.sendall(f"{bot_name}\n".encode())

    f = sock.makefile('r')

    while True:
        line = f.readline()
        if not line:
            break
        
        line = line.strip()
        if not line:
            continue
            
        parts = line.split()
        if parts[0] == 'ROUND':
            round_n = int(parts[1])
            w = int(parts[2])
            h = int(parts[3])
            
            start_time = time.time()
            all_placements = generate_all_placements(w, h)
            
            solution, Y = solve_dlx(w, h, all_placements, start_time)
            
            if solution is not None:
                grid = [[-1] * w for _ in range(h)]
                for piece_id, row_id in enumerate(solution):
                    for cell in Y[row_id]:
                        r, c = divmod(cell, w)
                        grid[r][c] = piece_id
                
                # Format output
                out_lines = []
                for r in range(h):
                    row_str = "".join(f"[{grid[r][c]}]" for c in range(w))
                    out_lines.append(row_str + "\n")
                out_lines.append("END\n")
                
                # Send the complete response
                sock.sendall("".join(out_lines).encode())
            else:
                # Failsafe if we timed out without finding a solution (should be rare)
                sock.sendall("END\n".encode())
                
        elif parts[0] == 'TOURNAMENT_END':
            break

    sock.close()

if __name__ == '__main__':
    main()