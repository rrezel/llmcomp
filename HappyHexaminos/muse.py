# bot author: Muse Spark
import os
import socket
import sys

# ---------- hexomino templates (6x6) ----------
# each number is a free-hexomino id from the spec (#0.. #34)
T_A = [
    [0,0,0,0],
    [1,1,1,2],
    [1,11,11,16,2,2],
    [7,11,11,16,16,2],
    [7,11,11,16,16,2],
    [7,7,7,7,16,2],
]
T_B = [
    [3,4,4,15,15,15],
    [3,4,4,4,4,15],
    [3,3,23,23,15,15],
    [3,13,23,23,23,12],
    [3,13,13,23,12,12],
    [13,13,13,12,12,12],
]
T_C = [
    [5,5,21,21],
    [5,20,5,21,21,8],
    [20,20,20,21,8,8],
    [20,9,27,21,8,8],
    [20,9,27,27,27,8],
    [9,9,9,9,27,27],
]
TEMPLATES = [T_A, T_B, T_C]

def place_template(board, ox, oy, tmpl, next_id):
    """copy 6x6 template into board, assigning new piece ids"""
    mp = {}
    for dy in range(6):
        for dx in range(6):
            sid = tmpl[dy][dx]
            if sid not in mp:
                mp[sid] = next_id
                next_id += 1
            board[oy+dy][ox+dx] = mp[sid]
    return next_id

def tile_base(board, ox, oy, w, h, next_id):
    """deterministic tiling of w×h rectangle with #0 (1×6) and #11 (2×3)"""
    # case 1: width multiple of 3, height even -> 2×3 blocks
    if w % 3 == 0 and h % 2 == 0:
        for y in range(0, h, 2):
            for x in range(0, w, 3):
                pid = next_id; next_id += 1
                for dy in range(2):
                    for dx in range(3):
                        board[oy+y+dy][ox+x+dx] = pid
    # case 2: height multiple of 3, width even -> 3×2 blocks
    elif h % 3 == 0 and w % 2 == 0:
        for y in range(0, h, 3):
            for x in range(0, w, 2):
                pid = next_id; next_id += 1
                for dy in range(3):
                    for dx in range(2):
                        board[oy+y+dy][ox+x+dx] = pid
    # case 3: width multiple of 6 -> horizontal bars
    elif w % 6 == 0:
        for y in range(h):
            for x in range(0, w, 6):
                pid = next_id; next_id += 1
                for dx in range(6):
                    board[oy+y][ox+x+dx] = pid
    # case 4: height multiple of 6 -> vertical bars
    else: # h % 6 == 0 guaranteed
        for x in range(w):
            for y in range(0, h, 6):
                pid = next_id; next_id += 1
                for dy in range(6):
                    board[oy+y+dy][ox+x] = pid
    return next_id

def solve(w, h):
    board = [[-1]*w for _ in range(h)]
    nid = 0

    # try horizontal strip of 6-high blocks
    if h >= 6:
        blocks = min(len(TEMPLATES), w // 6)
        for i in range(blocks):
            nid = place_template(board, i*6, 0, TEMPLATES[i], nid)
        # right strip
        rw = w - blocks*6
        if rw > 0:
            nid = tile_base(board, blocks*6, 0, rw, 6, nid)
        # bottom strip
        if h > 6:
            nid = tile_base(board, 0, 6, w, h-6, nid)
    elif w >= 6: # very thin board, use vertical arrangement
        blocks = min(len(TEMPLATES), h // 6)
        for i in range(blocks):
            nid = place_template(board, 0, i*6, TEMPLATES[i], nid)
        if blocks*6 < h:
            nid = tile_base(board, 0, blocks*6, 6, h-blocks*6, nid)
        if w > 6:
            nid = tile_base(board, 6, 0, w-6, h, nid)
    else: # w<6 and h<6 cannot happen because area>=36
        nid = tile_base(board, 0, 0, w, h, nid)

    return board

def board_to_lines(board):
    h = len(board); w = len(board[0])
    lines = []
    for y in range(h):
        line = ''.join(f'[{board[y][x]}]' for x in range(w))
        lines.append(line)
    return lines

def main():
    name = os.environ.get('BOTNAME', '').strip()
    if not name or not all(c.isalnum() or c in '_-' for c in name):
        sys.exit(1)
    s = socket.create_connection(('localhost', 7474))
    f = s.makefile('rwb', buffering=0)
    f.write((name + '\n').encode())

    while True:
        line = f.readline().decode().strip()
        if not line:
            break
        if line.startswith('ROUND'):
            _, n, w, h = line.split()
            w = int(w); h = int(h)
            board = solve(w, h)
            for row in board_to_lines(board):
                f.write((row + '\n').encode())
            f.write(b'END\n')
        elif line.startswith('OK') or line.startswith('INVALID'):
            continue
        elif line.startswith('END_ROUND'):
            continue
        elif line == 'TOURNAMENT_END':
            break
    s.close()

if __name__ == '__main__':
    main()