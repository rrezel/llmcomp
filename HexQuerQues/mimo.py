# bot author: MiMo-V2.5-Pro (xiaomi/mimo-v2.5-pro via OpenRouter)
import os
import socket
import time

def get_neighbors(r, i):
    n = [(r, (i+1)%6), (r, (i-1)%6)]
    if r >= 1: n.append((r-1, i))
    if r <= 2: n.append((r+1, i))
    return n

def get_captures_from(board, r, i, color):
    opp = 'B' if color == 'A' else 'A'
    caps = []
    if board[r][(i+1)%6] == opp and board[r][(i+2)%6] == '.':
        caps.append((r, (i+2)%6, [(r, (i+1)%6)]))
    if board[r][(i-1)%6] == opp and board[r][(i-2)%6] == '.':
        caps.append((r, (i-2)%6, [(r, (i-1)%6)]))
    if r+2 <= 3 and board[r+1][i] == opp and board[r+2][i] == '.':
        caps.append((r+2, i, [(r+1, i)]))
    if r-2 >= 0 and board[r-1][i] == opp and board[r-2][i] == '.':
        caps.append((r-2, i, [(r-1, i)]))
    return caps

def get_chain_moves(board, r, i, color):
    caps = get_captures_from(board, r, i, color)
    if not caps:
        return []
    chains = []
    for lr, li, jumped in caps:
        nb = [row[:] for row in board]
        for jr, ji in jumped:
            nb[jr][ji] = '.'
        nb[r][i] = '.'
        nb[lr][li] = color
        subs = get_chain_moves(nb, lr, li, color)
        if subs:
            for s in subs:
                chains.append([(r, i, lr, li)] + s)
        else:
            chains.append([(r, i, lr, li)])
    return chains

def get_all_moves(board, color):
    moves = []
    for r in range(4):
        for i in range(6):
            if board[r][i] == color:
                moves.extend(get_chain_moves(board, r, i, color))
    if moves:
        return moves
    for r in range(4):
        for i in range(6):
            if board[r][i] == color:
                for nr, ni in get_neighbors(r, i):
                    if board[nr][ni] == '.':
                        moves.append([(r, i, nr, ni)])
    return moves

def apply_move(board, move, color):
    nb = [row[:] for row in board]
    for r1, i1, r2, i2 in move:
        if r1 == r2:
            cw = (i2 - i1) % 6
            if cw == 2:
                nb[r1][(i1+1)%6] = '.'
            elif cw == 4:
                nb[r1][(i1-1)%6] = '.'
        elif i1 == i2 and abs(r2-r1) == 2:
            nb[(r1+r2)//2][i1] = '.'
        nb[r1][i1] = '.'
        nb[r2][i2] = color
    return nb

def evaluate(board, color):
    opp = 'B' if color == 'A' else 'A'
    mp, op = [], []
    for r in range(4):
        for i in range(6):
            if board[r][i] == color: mp.append((r,i))
            elif board[r][i] == opp: op.append((r,i))
    if not op: return 100000
    if not mp: return -100000
    s = (len(mp) - len(op)) * 10000
    rv = [40, 25, 10, 0]
    for r, i in mp: s += rv[r]
    for r, i in op: s -= rv[r]
    for r, i in mp: s += len(get_captures_from(board, r, i, color)) * 150
    for r, i in op: s -= len(get_captures_from(board, r, i, opp)) * 150
    mm = sum(1 for r,i in mp for nr,ni in get_neighbors(r,i) if board[nr][ni]=='.')
    om = sum(1 for r,i in op for nr,ni in get_neighbors(r,i) if board[nr][ni]=='.')
    s += (mm - om) * 5
    return s

def minimax(board, color, depth, alpha, beta, maximizing, st, tl):
    opp = 'B' if color == 'A' else 'A'
    if time.time() - st > tl:
        return evaluate(board, color)
    mc = sum(1 for r in range(4) for i in range(6) if board[r][i] == color)
    oc = sum(1 for r in range(4) for i in range(6) if board[r][i] == opp)
    if oc == 0: return 100000
    if mc == 0: return -100000
    if depth <= 0: return evaluate(board, color)
    cc = color if maximizing else opp
    moves = get_all_moves(board, cc)
    if not moves:
        return -100000 if maximizing else 100000
    moves.sort(key=lambda m: -len(m))
    if maximizing:
        v = float('-inf')
        for m in moves:
            v = max(v, minimax(apply_move(board, m, cc), color, depth-1, alpha, beta, False, st, tl))
            alpha = max(alpha, v)
            if beta <= alpha: break
        return v
    else:
        v = float('inf')
        for m in moves:
            v = min(v, minimax(apply_move(board, m, cc), color, depth-1, alpha, beta, True, st, tl))
            beta = min(beta, v)
            if beta <= alpha: break
        return v

def choose_move(board, color, time_left):
    moves = get_all_moves(board, color)
    if not moves: return None
    if len(moves) == 1: return moves[0]
    opp = 'B' if color == 'A' else 'A'
    for m in moves:
        nb = apply_move(board, m, color)
        if not any(nb[r][i] == opp for r in range(4) for i in range(6)):
            return m
    tl = min(time_left / 8, 3.0)
    tl = max(tl, 0.3)
    st = time.time()
    best = moves[0]
    pc = sum(1 for r in range(4) for i in range(6) if board[r][i] != '.')
    max_d = 7 if pc <= 6 else 5 if pc <= 10 else 4 if pc <= 16 else 3
    for d in range(1, max_d + 1):
        if time.time() - st > tl * 0.7: break
        cb, cs = None, float('-inf')
        for m in moves:
            s = minimax(apply_move(board, m, color), color, d-1, float('-inf'), float('inf'), False, st, tl)
            if s > cs: cs, cb = s, m
            if time.time() - st > tl * 0.85: break
        if cb:
            best = cb
            moves.sort(key=lambda m: 0 if m == best else 1)
    return best

def format_move(move):
    parts = [f"{move[0][0]},{move[0][1]}"]
    for seg in move:
        parts.append(f"{seg[2]},{seg[3]}")
    return "MOVE " + " -> ".join(parts)

def parse_board(s):
    t = s.split()
    return [[t[r*6+i] for i in range(6)] for r in range(4)]

def parse_move_line(line):
    parts = line.split(" -> ")
    coords = []
    for p in parts:
        p = p.strip()
        if p.startswith("MOVE "): p = p[5:]
        r, i = p.split(",")
        coords.append((int(r), int(i)))
    return [(coords[j][0], coords[j][1], coords[j+1][0], coords[j+1][1]) for j in range(len(coords)-1)]

def main():
    botname = os.environ['BOTNAME'].strip()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.sendall((botname + '\n').encode())
    f = sock.makefile('r')
    board = None
    color = None
    tr = 30.0
    while True:
        line = f.readline()
        if not line: break
        line = line.rstrip('\n')
        if line.startswith("GAME "):
            color = line.split()[2]
            tr = 30.0
        elif line.startswith("BOARD "):
            board = parse_board(line[6:])
        elif line == "TURN":
            st = time.time()
            move = choose_move(board, color, tr)
            tr -= time.time() - st
            if move:
                sock.sendall((format_move(move) + '\n').encode())
                board = apply_move(board, move, color)
        elif line.startswith("OPP "):
            move = parse_move_line(line[4:])
            opp = 'B' if color == 'A' else 'A'
            board = apply_move(board, move, opp)
        elif line == "TOURNAMENT_END":
            break
    sock.close()

if __name__ == "__main__":
    main()