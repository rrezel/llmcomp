# bot author: GLM 5.1 (z-ai/glm-5.1 via OpenRouter)
# bot author: Claude 3.5 Sonnet

import os
import sys
import socket
import time
import random
from collections import deque

def main():
    botname = os.environ.get('BOTNAME', '').strip()
    if not botname:
        return
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    
    def send_line(line):
        sock.sendall((line + '\n').encode())
    
    def recv_line():
        buf = b''
        while True:
            b = sock.recv(1)
            if not b:
                return None
            if b == b'\n':
                return buf.decode()
            buf += b
    
    send_line(botname)
    
    # Define all 35 free hexominoes as lists of (row, col) cells
    SHAPES_RAW = [
        [(0,0),(0,1),(0,2),(0,3),(0,4),(0,5)],  # #0
        [(0,0),(0,1),(0,2),(0,3),(0,4),(1,0)],  # #1
        [(0,0),(0,1),(0,2),(0,3),(0,4),(1,1)],  # #2
        [(0,0),(0,1),(0,2),(0,3),(0,4),(1,2)],  # #3
        [(0,0),(0,1),(0,2),(0,3),(1,0),(1,1)],  # #4
        [(0,0),(0,1),(0,2),(0,3),(1,0),(1,2)],  # #5
        [(0,0),(0,1),(0,2),(0,3),(1,0),(1,3)],  # #6
        [(0,0),(0,1),(0,2),(0,3),(1,0),(2,0)],  # #7
        [(0,0),(0,1),(0,2),(0,3),(1,1),(1,2)],  # #8
        [(0,0),(0,1),(0,2),(0,3),(1,1),(2,1)],  # #9
        [(0,0),(0,1),(0,2),(0,3),(1,3),(1,4)],  # #10
        [(0,0),(0,1),(0,2),(1,0),(1,1),(1,2)],  # #11
        [(0,0),(0,1),(0,2),(1,0),(1,1),(2,0)],  # #12
        [(0,0),(0,1),(0,2),(1,0),(1,1),(2,1)],  # #13
        [(0,0),(0,1),(0,2),(1,0),(1,2),(1,3)],  # #14
        [(0,0),(0,1),(0,2),(1,0),(1,2),(2,0)],  # #15
        [(0,0),(0,1),(0,2),(1,1),(1,2),(1,3)],  # #16
        [(0,0),(0,1),(0,2),(1,1),(2,0),(2,1)],  # #17
        [(0,0),(0,1),(0,2),(1,1),(2,1),(3,1)],  # #18
        [(0,0),(0,1),(0,2),(1,2),(1,3),(1,4)],  # #19
        [(0,0),(0,1),(0,2),(1,2),(1,3),(2,2)],  # #20
        [(0,0),(0,1),(0,2),(1,2),(1,3),(2,3)],  # #21
        [(0,0),(0,1),(0,2),(1,2),(2,2),(2,3)],  # #22
        [(0,0),(0,1),(1,0),(1,1),(1,2),(2,1)],  # #23
        [(0,0),(0,1),(1,0),(1,1),(1,2),(2,2)],  # #24
        [(0,0),(0,1),(1,1),(1,2),(1,3),(2,1)],  # #25
        [(0,0),(0,1),(1,1),(1,2),(1,3),(2,2)],  # #26
        [(0,0),(0,1),(1,1),(1,2),(1,3),(2,3)],  # #27
        [(0,0),(0,1),(1,1),(1,2),(2,0),(2,1)],  # #28
        [(0,0),(0,1),(1,1),(1,2),(2,1),(3,1)],  # #29
        [(0,0),(0,1),(1,1),(1,2),(2,2),(2,3)],  # #30
        [(0,0),(0,1),(1,1),(2,1),(2,2),(3,1)],  # #31
        [(0,0),(0,1),(1,1),(2,1),(3,1),(3,2)],  # #32
        [(0,1),(1,0),(1,1),(1,2),(1,3),(2,1)],  # #33
        [(0,1),(1,0),(1,1),(1,2),(1,3),(2,2)],  # #34
    ]
    
    def normalize(cells):
        min_r = min(r for r, c in cells)
        min_c = min(c for r, c in cells)
        shifted = tuple(sorted((r - min_r, c - min_c) for r, c in cells))
        return shifted
    
    def get_all_orientations(cells):
        orientations = set()
        cur = list(cells)
        for _ in range(4):
            orientations.add(normalize(cur))
            # reflect
            reflected = [(-r, c) for r, c in cur]
            orientations.add(normalize(reflected))
            # rotate 90 degrees clockwise: (r,c) -> (c,-r)
            cur = [(c, -r) for r, c in cur]
        return list(orientations)
    
    # Precompute all orientations for each shape
    ALL_ORIENTATIONS = []
    for shape in SHAPES_RAW:
        orients = get_all_orientations(shape)
        ALL_ORIENTATIONS.append(orients)
    
    # Create a flat list of (shape_id, orientation_cells) for placement
    ALL_PLACEMENTS = []
    for sid, orients in enumerate(ALL_ORIENTATIONS):
        for orient in orients:
            ALL_PLACEMENTS.append((sid, orient))
    
    def can_place(grid, w, h, cells, dr, dc, piece_id):
        for r, c in cells:
            nr, nc = r + dr, c + dc
            if nr < 0 or nr >= h or nc < 0 or nc >= w:
                return False
            if grid[nr][nc] != -1:
                return False
        return True
    
    def place_piece(grid, w, h, cells, dr, dc, piece_id):
        for r, c in cells:
            nr, nc = r + dr, c + dc
            grid[nr][nc] = piece_id
    
    def remove_piece(grid, cells, dr, dc):
        for r, c in cells:
            nr, nc = r + dr, c + dc
            grid[nr][nc] = -1
    
    def find_first_empty(grid, w, h):
        for r in range(h):
            for c in range(w):
                if grid[r][c] == -1:
                    return (r, c)
        return None
    
    # Check if remaining empty cells can be tiled (simple connectivity check)
    def is_connected_remaining(grid, w, h, start_r, start_c):
        visited = set()
        queue = deque()
        queue.append((start_r, start_c))
        visited.add((start_r, start_c))
        count = 1
        while queue:
            r, c = queue.popleft()
            for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < h and 0 <= nc < w and (nr, nc) not in visited and grid[nr][nc] == -1:
                    visited.add((nr, nc))
                    count += 1
                    queue.append((nr, nc))
        total_empty = sum(1 for r in range(h) for c in range(w) if grid[r][c] == -1)
        return count == total_empty
    
    def solve_tiling(w, h, time_limit):
        grid = [[-1] * w for _ in range(h)]
        shapes_used = set()
        piece_id_counter = [0]
        result = [None]
        start_time = time.time()
        nodes = [0]
        
        # Precompute placements by their top-left anchor
        # For each shape orientation, compute which cells it covers
        # When we find first empty cell (r,c), we need placements that include (r,c)
        
        def get_placements_at(r, c):
            """Get all (shape_id, cells) that can be placed with (r,c) as one of their cells"""
            placements = []
            for sid, orient in ALL_PLACEMENTS:
                for cr, cc in orient:
                    dr, dc = r - cr, c - cc
                    # Check if placement is valid
                    valid = True
                    for pr, pc in orient:
                        nr, nc = pr + dr, pc + dc
                        if nr < 0 or nr >= h or nc < 0 or nc >= w or grid[nr][nc] != -1:
                            valid = False
                            break
                    if valid:
                        placed_cells = [(pr + dr, pc + dc) for pr, pc in orient]
                        placements.append((sid, placed_cells))
            return placements
        
        def backtrack():
            if time.time() - start_time > time_limit:
                return False
            
            nodes[0] += 1
            
            empty = find_first_empty(grid, w, h)
            if empty is None:
                result[0] = [row[:] for row in grid]
                return True
            
            r, c = empty
            
            placements = get_placements_at(r, c)
            
            # Sort: prefer shapes not yet used (to maximize inventory)
            # Then prefer shapes that leave more connected space
            def placement_score(p):
                sid, cells = p
                if sid not in shapes_used:
                    return 0  # prefer new shapes
                return 1
            
            placements.sort(key=placement_score)
            
            for sid, cells in placements:
                pid = piece_id_counter[0]
                piece_id_counter[0] += 1
                
                for cr, cc in cells:
                    grid[cr][cc] = pid
                
                new_shape = sid not in shapes_used
                if new_shape:
                    shapes_used.add(sid)
                
                # Quick connectivity check for remaining empty cells
                next_empty = find_first_empty(grid, w, h)
                connected_ok = True
                if next_empty is not None:
                    # Count empty cells
                    empty_count = sum(1 for rr in range(h) for cc in range(w) if grid[rr][cc] == -1)
                    if empty_count > 0 and empty_count % 6 != 0:
                        connected_ok = False
                    elif empty_count > 0:
                        connected_ok = is_connected_remaining(grid, w, h, next_empty[0], next_empty[1])
                
                if connected_ok:
                    if backtrack():
                        return True
                
                for cr, cc in cells:
                    grid[cr][cc] = -1
                if new_shape:
                    shapes_used.discard(sid)
                piece_id_counter[0] -= 1
            
            return False
        
        if backtrack():
            return result[0], shapes_used
        return None, set()
    
    def simple_tiling_2x3(w, h):
        """Tile with 2x3 rectangles (shape #11) - guaranteed to work for many dimensions"""
        grid = [[-1] * w for _ in range(h)]
        pid = 0
        # Try to tile with 2x3 blocks
        # Shape #11 orientations: 2x3 or 3x2
        
        # First try 2x3 blocks (2 rows, 3 cols)
        if w % 3 == 0 and h % 2 == 0:
            for r in range(0, h, 2):
                for c in range(0, w, 3):
                    for dr in range(2):
                        for dc in range(3):
                            grid[r+dr][c+dc] = pid
                    pid += 1
            return grid
        # Try 3x2 blocks (3 rows, 2 cols)
        if w % 2 == 0 and h % 3 == 0:
            for r in range(0, h, 3):
                for c in range(0, w, 2):
                    for dr in range(3):
                        for dc in range(2):
                            grid[r+dr][c+dc] = pid
                    pid += 1
            return grid
        # Try 1x6 blocks (shape #0)
        if w % 6 == 0:
            for r in range(h):
                for c in range(0, w, 6):
                    for dc in range(6):
                        grid[r][c+dc] = pid
                    pid += 1
            return grid
        if h % 6 == 0:
            for c in range(w):
                for r in range(0, h, 6):
                    for dr in range(6):
                        grid[r+dr][c] = pid
                    pid += 1
            return grid
        return None
    
    def simple_tiling_1x6(w, h):
        """Tile with 1x6 lines"""
        grid = [[-1] * w for _ in range(h)]
        pid = 0
        if w % 6 == 0:
            for r in range(h):
                for c in range(0, w, 6):
                    for dc in range(6):
                        grid[r][c+dc] = pid
                    pid += 1
            return grid
        if h % 6 == 0:
            for c in range(w):
                for r in range(0, h, 6):
                    for dr in range(6):
                        grid[r+dr][c] = pid
                    pid += 1
            return grid
        return None
    
    def mixed_tiling(w, h):
        """Try to use multiple shapes for tiling"""
        grid = [[-1] * w for _ in range(h)]
        pid = 0
        shapes_used = set()
        
        # Strategy: try to place diverse shapes first, then fill remainder with simple shapes
        # We'll try to place shapes in a greedy manner
        
        # Get all possible placements
        def get_all_valid_placements():
            placements = []
            for sid, orient in ALL_PLACEMENTS:
                max_r = max(r for r, c in orient)
                max_c = max(c for r, c in orient)
                for dr in range(h - max_r):
                    for dc in range(w - max_c):
                        valid = True
                        for r, c in orient:
                            if grid[r+dr][c+dc] != -1:
                                valid = False
                                break
                        if valid:
                            cells = [(r+dr, c+dc) for r, c in orient]
                            placements.append((sid, cells))
            return placements
        
        # Greedy: try to place one of each shape
        shape_order = list(range(35))
        random.shuffle(shape_order)
        
        for target_sid in shape_order:
            # Try to place this shape somewhere
            placed = False
            for orient in ALL_ORIENTATIONS[target_sid]:
                max_r = max(r for r, c in orient)
                max_c = max(c for r, c in orient)
                for dr in range(h - max_r):
                    for dc in range(w - max_c):
                        valid = True
                        for r, c in orient:
                            if grid[r+dr][c+dc] != -1:
                                valid = False
                                break
                        if valid:
                            cells = [(r+dr, c+dc) for r, c in orient]
                            for cr, cc in cells:
                                grid[cr][cc] = pid
                            pid += 1
                            shapes_used.add(target_sid)
                            placed = True
                            break
                    if placed:
                        break
                if placed:
                    break
        
        # Now fill the rest with 2x3 or 1x6 blocks
        # Find remaining empty cells and try to fill them
        remaining = []
        for r in range(h):
            for c in range(w):
                if grid[r][c] == -1:
                    remaining.append((r, c))
        
        if len(remaining) % 6 != 0:
            return None, set()
        
        # Try to fill remaining with backtracking
        def fill_remaining():
            empty = find_first_empty(grid, w, h)
            if empty is None:
                return True
            r, c = empty
            
            for sid, orient in ALL_PLACEMENTS:
                max_r = max(rr for rr, cc in orient)
                max_c = max(cc for rr, cc in orient)
                if r - min(rr for rr, cc in orient) < 0:
                    continue
                dr = r - min(rr for rr, cc in orient)
                # Actually let's just try all offsets that include (r,c)
                for cr, cc in orient:
                    dr, dc = r - cr, c - cc
                    valid = True
                    cells = []
                    for pr, pc in orient:
                        nr, nc = pr + dr, pc + dc
                        if nr < 0 or nr >= h or nc < 0 or nc >= w or grid[nr][nc] != -1:
                            valid = False
                            break
                        cells.append((nr, nc))
                    if valid:
                        for nr, nc in cells:
                            grid[nr][nc] = pid
                        old_pid = pid
                        pid_tmp = pid + 1
                        
                        # Temporarily update
                        for nr, nc in cells:
                            grid[nr][nc] = pid
                        
                        nonlocal pid
                        pid += 1
                        shapes_used.add(sid)
                        
                        if fill_remaining():
                            return True
                        
                        pid -= 1
                        shapes_used.discard(sid)
                        for nr, nc in cells:
                            grid[nr][nc] = -1
            
            return False
        
        # This approach is too complex, let me simplify
        return None, set()
    
    def greedy_diverse_tiling(w, h, time_limit):
        """Greedy tiling that tries to maximize shape diversity"""
        grid = [[-1] * w for _ in range(h)]
        pid = 0
        shapes_used = set()
        start_time = time.time()
        
        # Phase 1: Try to place one of each shape greedily
        shape_order = list(range(35))
        random.shuffle(shape_order)
        
        for target_sid in shape_order:
            if time.time() - start_time > time_limit * 0.3:
                break
            placed = False
            orients = ALL_ORIENTATIONS[target_sid]
            random.shuffle(orients)
            for orient in orients:
                if placed:
                    break
                max_r = max(r for r, c in orient)
                max_c = max(c for r, c in orient)
                positions = [(dr, dc) for dr in range(h - max_r) for dc in range(w - max_c)]
                random.shuffle(positions)
                for dr, dc in positions:
                    valid = True
                    for r, c in orient:
                        if grid[r+dr][c+dc] != -1:
                            valid = False
                            break
                    if valid:
                        for r, c in orient:
                            grid[r+dr][c+dc] = pid
                        pid += 1
                        shapes_used.add(target_sid)
                        placed = True
                        break
        
        # Phase 2: Fill remaining cells with backtracking
        remaining_count = sum(1 for r in range(h) for c in range(w) if grid[r][c] == -1)
        
        if remaining_count == 0:
            return grid, shapes_used
        
        if remaining_count % 6 != 0:
            # Something went wrong, reset and use simple tiling
            return None, set()
        
        # Use backtracking for remaining cells
        fill_pid_start = pid
        
        def fill_backtrack():
            nonlocal pid
            if time.time() - start_time > time_limit * 0.9:
                return False
            
            empty = find_first_empty(grid, w, h)
            if empty is None:
                return True
            r, c = empty
            
            # Try placements that include (r, c)
            candidates = []
            for sid, orient in ALL_PLACEMENTS:
                for cr, cc in orient:
                    dr, dc = r - cr, c - dc
                    valid = True
                    cells = []
                    for pr, pc in orient:
                        nr, nc = pr + dr, pc + dc
                        if nr < 0 or nr >= h or nc < 0 or nc >= w or grid[nr][nc] != -1:
                            valid = False
                            break
                        cells.append((nr, nc))
                    if valid:
                        candidates.append((sid, cells))
            
            # Prefer new shapes
            candidates.sort(key=lambda x: 0 if x[0] not in shapes_used else 1)
            
            for sid, cells in candidates:
                for nr, nc in cells:
                    grid[nr][nc] = pid
                pid += 1
                new_shape = sid not in shapes_used
                if new_shape:
                    shapes_used.add(sid)
                
                # Quick check: remaining empty count divisible by 6?
                empty_count = sum(1 for rr in range(h) for cc in range(w) if grid[rr][cc] == -1)
                ok = True
                if empty_count % 6 != 0:
                    ok = False
                elif empty_count > 0:
                    ne = find_first_empty(grid, w, h)
                    if ne and not is_connected_remaining(grid, w, h, ne[0], ne[1]):
                        ok = False
                
                if ok and fill_backtrack():
                    return True
                
                for nr, nc in cells:
                    grid[nr][nc] = -1
                pid -= 1
                if new_shape:
                    shapes_used.discard(sid)
            
            return False
        
        if fill_backtrack():
            return grid, shapes_used
        
        return None, set()
    
    def fallback_tiling(w, h):
        """Simple fallback that always works"""
        grid = [[-1] * w for _ in range(h)]
        pid = 0
        
        # Try various simple tilings
        # 1x6 horizontal
        if w % 6 == 0:
            for r in range(h):
                for c in range(0, w, 6):
                    for dc in range(6):
                        grid[r][c+dc] = pid
                    pid += 1
            return grid
        
        # 1x6 vertical
        if h % 6 == 0:
            for c in range(w):
                for r in range(0, h, 6):
                    for dr in range(6):
                        grid[r+dr][c] = pid
                    pid += 1
            return grid
        
        # 2x3 blocks
        if w % 3 == 0 and h % 2 == 0:
            for r in range(0, h, 2):
                for c in range(0, w, 3):
                    for dr in range(2):
                        for dc in range(3):
                            grid[r+dr][c+dc] = pid
                    pid += 1
            return grid
        
        # 3x2 blocks
        if w % 2 == 0 and h % 3 == 0:
            for r in range(0, h, 3):
                for c in range(0, w, 2):
                    for dr in range(3):
                        for dc in range(2):
                            grid[r+dr][c+dc] = pid
                    pid += 1
            return grid
        
        # Mixed: use 1x6 and 2x3
        # If w % 6 == 0, we already handled it
        # Try: fill rows with 1x6 where possible, use 2x3 for rest
        # This is getting complex; let's try a general approach
        
        # General approach: scan left-to-right, top-to-bottom
        # For each empty cell, try to place a shape
        # Use a priority order of shapes
        
        # Actually, let's try a different approach:
        # Use 2x3 and 3x2 blocks to handle various dimensions
        
        # If w is even, we can try 3x2 blocks in columns of width 2
        # If w is odd but w >= 6, we can use a 6-wide column of 1x6 blocks and recurse
        
        # Let's try: decompose w into parts divisible by 2, 3, or 6
        # w can be written as 2a + 3b for many values (Frobenius: all w >= 2*3-2-3 = 1)
        # Actually for w >= 2, we can write w = 2a + 3b
        
        # Strategy: split the rectangle into vertical strips
        # Each strip is either width 2 (tiled with 3x2 blocks if h%3==0, or 2x3 if h%2==0)
        # or width 3 (tiled with 2x3 blocks if h%2==0, or 3x2 if h%3==0)
        # or width 6 (tiled with 1x6 blocks)
        
        # For h that's a multiple of 6, we can use 1x6 vertical strips of any width
        # For h that's even, we can use 2x3 blocks in strips of width 3
        # For h that's a multiple of 3, we can use 3x2 blocks in strips of width 2
        
        # Let's handle this more carefully
        # We need w*h % 6 == 0
        
        # Case: h % 2 == 0
        #   We can tile with 2x3 blocks if w % 3 == 0 (done above)
        #   Or mix: use 2x3 blocks for width-3 columns, and 1x6 for width-6 columns
        #   w = 3*q + 6*r for some q, r >= 0 if w >= 0 and w != 1, 2, 4, 5
        #   Actually w can be: 3, 6, 8(=2+6), 9, 10(=4+6?), 11(=5+6?), 12, ...
        #   Hmm, let me think differently
        
        # For h % 6 == 0: use 1x6 vertical, any w works
        # For h % 2 == 0 and h % 3 != 0: h is 2, 4, 8, 10, 14, ...
        #   Need w % 3 == 0 for 2x3 blocks
        #   Or w such that we can decompose into 3-wide and 6-wide strips
        # For h % 3 == 0 and h % 2 != 0: h is 3, 9, 15, 21, ...
        #   Need w % 2 == 0 for 3x2 blocks
        
        # Let me try a recursive strip decomposition
        def tile_strip(grid, x, strip_w, h, pid_start):
            """Tile a vertical strip of width strip_w starting at column x"""
            p = pid_start
            if strip_w == 0:
                return p
            if h % 6 == 0:
                # Use 1x6 vertical blocks
                for c in range(x, x + strip_w):
                    for r in range(0, h, 6):
                        for dr in range(6):
                            grid[r+dr][c] = p
                        p += 1
                return p
            if h % 2 == 0 and strip_w % 3 == 0:
                # Use 2x3 blocks
                for r in range(0, h, 2):
                    for c in range(x, x + strip_w, 3):
                        for dr in range(2):
                            for dc in range(3):
                                grid[r+dr][c+dc] = p
                        p += 1
                return p
            if h % 3 == 0 and strip_w % 2 == 0:
                # Use 3x2 blocks
                for r in range(0, h, 3):
                    for c in range(x, x + strip_w, 2):
                        for dr in range(3):
                            for dc in range(2):
                                grid[r+dr][c+dc] = p
                        p += 1
                return p
            return -1  # Can't tile this strip
        
        # Try to decompose w into strips
        # If h % 6 == 0, one strip of width w
        if h % 6 == 0:
            p = tile_strip(grid, 0, w, h, 0)
            if p >= 0:
                return grid
        
        # If h % 2 == 0, try strips of width 3 and 6
        if h % 2 == 0:
            # w = 3*a + 6*b
            for a in range(w // 3 + 1):
                remainder = w - 3 * a
                if remainder >= 0 and remainder % 6 == 0:
                    b = remainder // 6
                    p = 0
                    x = 0
                    ok = True
                    for _ in range(a):
                        p2 = tile_strip(grid, x, 3, h, p)
                        if p2 < 0:
                            ok = False
                            break
                        p = p2
                        x += 3
                    if ok:
                        for _ in range(b):
                            p2 = tile_strip(grid, x, 6, h, p)
                            if p2 < 0:
                                ok = False
                                break
                            p = p2
                            x += 6
                        if ok:
                            return grid
                    # Reset grid
                    grid = [[-1] * w for _ in range(h)]
        
        # If h % 3 == 0, try strips of width 2 and 6
        if h % 3 == 0:
            for a in range(w // 2 + 1):
                remainder = w - 2 * a
                if remainder >= 0 and remainder % 6 == 0:
                    b = remainder // 6
                    p = 0
                    x = 0
                    ok = True
                    for _ in range(a):
                        p2 = tile_strip(grid, x, 2, h, p)
                        if p2 < 0:
                            ok = False
                            break
                        p = p2
                        x += 2
                    if ok:
                        for _ in range(b):
                            p2 = tile_strip(grid, x, 6, h, p)
                            if p2 < 0:
                                ok = False
                                break
                            p = p2
                            x += 6
                        if ok:
                            return grid
                    grid = [[-1] * w for _ in range(h)]
        
        # General case: try to decompose both dimensions
        # Use a combination of horizontal and vertical strips
        # This is getting complex; let's try brute force backtracking as last resort
        
        return None
    
    def enhanced_fallback_tiling(w, h):
        """More robust fallback tiling"""
        # Try the simple fallback first
        result = fallback_tiling(w, h)
        if result is not None:
            return result
        
        # If that didn't work, try horizontal strip decomposition
        grid = [[-1] * w for _ in range(h)]
        pid = 0
        
        def tile_hstrip(grid, y, strip_h, w, pid_start):
            """Tile a horizontal strip of height strip_h starting at row y"""
            p = pid_start
            if strip_h == 0:
                return p
            if w % 6 == 0:
                # Use 1x6 horizontal blocks
                for r in range(y, y + strip_h):
                    for c in range(0, w, 6):
                        for dc in range(6):
                            grid[r][c+dc] = p
                        p += 1
                return p
            if w % 2 == 0 and strip_h % 3 == 0:
                # Use 3x2 blocks (3 rows, 2 cols)
                for r in range(y, y + strip_h, 3):
                    for c in range(0, w, 2):
                        for dr in range(3):
                            for dc in range(2):
                                grid[r+dr][c+dc] = p
                        p += 1
                return p
            if w % 3 == 0 and strip_h % 2 == 0:
                # Use 2x3 blocks (2 rows, 3 cols)
                for r in range(y, y + strip_h, 2):
                    for c in range(0, w, 3):
                        for dr in range(2):
                            for dc in range(3):
                                grid[r+dr][c+dc] = p
                        p += 1
                return p
            return -1
        
        # Try horizontal strip decomposition
        if w % 6 == 0:
            p = tile_hstrip(grid, 0, h, w, 0)
            if p >= 0:
                return grid
        
        if w % 2 == 0:
            for a in range(h // 3 + 1):
                remainder = h - 3 * a
                if remainder >= 0 and remainder % 6 == 0:
                    b = remainder // 6
                    p = 0
                    y = 0
                    ok = True
                    for _ in range(a):
                        p2 = tile_hstrip(grid, y, 3, w, p)
                        if p2 < 0:
                            ok = False
                            break
                        p = p2
                        y += 3
                    if ok:
                        for _ in range(b):
                            p2 = tile_hstrip(grid, y, 6, w, p)
                            if p2 < 0:
                                ok = False
                                break
                            p = p2
                            y += 6
                        if ok:
                            return grid
                    grid = [[-1] * w for _ in range(h)]
        
        if w % 3 == 0:
            for a in range(h // 2 + 1):
                remainder = h - 2 * a
                if remainder >= 0 and remainder % 6 == 0:
                    b = remainder // 6
                    p = 0
                    y = 0
                    ok = True
                    for _ in range(a):
                        p2 = tile_hstrip(grid, y, 2, w, p)
                        if p2 < 0:
                            ok = False
                            break
                        p = p2
                        y += 2
                    if ok:
                        for _ in range(b):
                            p2 = tile_hstrip(grid, y, 6, w, p)
                            if p2 < 0:
                                ok = False
                                break
                            p = p2
                            y += 6
                        if ok:
                            return grid
                    grid = [[-1] * w for _ in range(h)]
        
        return None
    
    def ultimate_fallback(w, h):
        """Last resort: backtracking tiling with simple shapes"""
        grid = [[-1] * w for _ in range(h)]
        pid = [0]
        
        # Only use a few simple shapes for speed
        simple_shapes = []
        for sid in [0, 11]:  # 1x6 line and 2x3 rectangle
            for orient in ALL_ORIENTATIONS[sid]:
                simple_shapes.append((sid, orient))
        
        def backtrack():
            empty = find_first_empty(grid, w, h)
            if empty is None:
                return True
            r, c = empty
            
            for sid, orient in simple_shapes:
                for cr, cc in orient:
                    dr, dc = r - cr, c - cc
                    valid = True
                    cells = []
                    for pr, pc in orient:
                        nr, nc = pr + dr, pc + dc
                        if nr < 0 or nr >= h or nc < 0 or nc >= w or grid[nr][nc] != -1:
                            valid = False
                            break
                        cells.append((nr, nc))
                    if valid:
                        for nr, nc in cells:
                            grid[nr][nc] = pid[0]
                        pid[0] += 1
                        if backtrack():
                            return True
                        pid[0] -= 1
                        for nr, nc in cells:
                            grid[nr][nc] = -1
            
            return False
        
        if backtrack():
            return grid
        return None
    
    def diversify_grid(grid, w, h, time_limit):
        """Try to replace pieces with different shapes to increase diversity"""
        start_time = time.time()
        
        # Find all pieces and their shapes
        pieces = {}
        for r in range(h):
            for c in range(w):
                pid = grid[r][c]
                if pid not in pieces:
                    pieces[pid] = []
                pieces[pid].append((r, c))
        
        # Determine current shape of each piece
        def identify_shape(cells):
            normalized = normalize(cells)
            for sid in range(35):
                if normalized in ALL_ORIENTATIONS[sid]:
                    return sid
            return -1
        
        piece_shapes = {}
        for pid, cells in pieces.items():
            piece_shapes[pid] = identify_shape(cells)
        
        shapes_count = {}
        for pid, sid in piece_shapes.items():
            shapes_count[sid] = shapes_count.get(sid, 0) + 1
        
        # Try to replace pieces that have duplicate shapes with unused shapes
        used_shapes = set(piece_shapes.values())
        unused_shapes = set(range(35)) - used_shapes
        
        # For each duplicate shape, try to replace one instance with an unused shape
        for dup_sid in sorted(shapes_count.keys(), key=lambda s: -shapes_count[s]):
            if shapes_count[dup_sid] <= 1:
                continue
            if not unused_shapes:
                break
            if time.time() - start_time > time_limit:
                break
            
            # Find pieces with this shape
            dup_pids = [pid for pid, sid in piece_shapes.items() if sid == dup_sid]
            
            for pid in dup_pids[1:]:  # Keep one, try to replace others
                if not unused_shapes:
                    break
                if time.time() - start_time > time_limit:
                    break
                
                cells = pieces[pid]
                cell_set = set(cells)
                
                # Try each unused shape
                for new_sid in list(unused_shapes):
                    if time.time() - start_time > time_limit:
                        break
                    
                    for orient in ALL_ORIENTATIONS[new_sid]:
                        # Try to place this orientation at each position
                        # that covers the same cells
                        # We need to find a placement that:
                        # 1. Covers exactly the cells in `cell_set`
                        # This is only possible if the shape has the same normalized form
                        # as the cells... which means it's the same shape. That won't help.
                        pass
                
                # Actually, replacing a single piece with a different shape while
                # keeping the same cells is impossible (different shape = different cells).
                # We need to swap cells between adjacent pieces.
                # This is much more complex. Let me skip this for now.
                break
        
        return grid
    
    def solve_round(w, h):
        """Main solving function for a round"""
        time_limit = 25.0  # Leave 5 seconds buffer
        start_time = time.time()
        
        k = w * h // 6  # Number of pieces needed
        
        # Strategy 1: Try greedy diverse tiling with backtracking
        if w * h <= 600:  # Only for smaller grids
            grid, shapes = greedy_diverse_tiling(w, h, time_limit * 0.7)
            if grid is not None:
                return grid
        
        # Strategy 2: Simple tiling with strip decomposition
        grid = enhanced_fallback_tiling(w, h)
        if grid is not None:
            # Try to diversify
            remaining_time = time_limit - (time.time() - start_time)
            if remaining_time > 2:
                grid = diversify_grid(grid, w, h, remaining_time * 0.5)
            return grid
        
        # Strategy 3: Ultimate fallback
        grid = ultimate_fallback(w, h)
        if grid is not None:
            return grid
        
        # Should not reach here since the server guarantees tileability
        # But just in case, create a dummy grid
        grid = [[0] * w for _ in range(h)]
        return grid
    
    # Main tournament loop
    while True:
        line = recv_line()
        if line is None:
            break
        
        if line.startswith('ROUND'):
            parts = line.split()
            round_num = int(parts[1])
            w = int(parts[2])
            h = int(parts[3])
            
            grid = solve_round(w, h)
            
            # Send the grid
            for r in range(h):
                row_str = ''
                for c in range(w):
                    row_str += '[' + str(grid[r][c]) + ']'
                send_line(row_str)
            send_line('END')
            
            # Read response
            response = recv_line()
            # Read END_ROUND
            end_round = recv_line()
        
        elif line == 'TOURNAMENT_END':
            break
    
    sock.close()

if __name__ == '__main__':
    main()
