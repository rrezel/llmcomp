# bot author: Muse Spark
import os
import socket
import sys
import time
import random
from collections import defaultdict

HOST = "localhost"
PORT = 7474
TIME_BUDGET = 29.0 # leave 1s margin on 30s limit
INF = 10**9

# Board geometry: 4 rings, 6 vertices each. Index = r*6 + i
def neighbors(r, i):
    n = []
    # same ring
    n.append((r, (i+1) % 6))
    n.append((r, (i-1) % 6))
    # radial
    if r > 0:
        n.append((r-1, i))
    if r < 3:
        n.append((r+1, i))
    return n

def between(a, b):
    r1, i1 = a
    r2, i2 = b
    # same ring jump
    if r1 == r2:
        diff = (i2 - i1) % 6
        if diff == 2:
            return (r1, (i1+1) % 6)
        if diff == 4: # i2 = i1-2 mod6
            return (r1, (i1-1) % 6)
    # radial jump
    if i1 == i2 and abs(r2 - r1) == 2:
        return ((r1+r2)//2, i1)
    return None

def idx(r, i):
    return r*6 + i

def rc_from_idx(k):
    return divmod(k, 6)

class Board:
    def __init__(self):
        # 24 cells: '.' empty, 'A', 'B'
        self.cells = ['.']*24
        # starting position
        for i in [0,2,4]:
            self.cells[idx(2,i)] = 'A'
            self.cells[idx(3,i)] = 'A'
            self.cells[idx(2,i+1)] = 'B'
            self.cells[idx(3,i+1)] = 'B'
        self.to_move = 'A'
        self.plies_no_capture = 0
        self.positions = defaultdict(int)
        self._record_pos()

    def copy(self):
        b = Board.__new__(Board)
        b.cells = self.cells[:]
        b.to_move = self.to_move
        b.plies_no_capture = self.plies_no_capture
        b.positions = self.positions.copy()
        return b

    def _record_pos(self):
        key = (tuple(self.cells), self.to_move)
        self.positions[key] += 1

    def piece_count(self, color):
        return self.cells.count(color)

    def has_capture(self, color):
        for k in range(24):
            if self.cells[k]!= color:
                continue
            r, i = rc_from_idx(k)
            for nr, ni in neighbors(r, i):
                jumped = between((r,i), (nr,ni))
                if jumped is None:
                    continue
                jr, ji = jumped
                if self.cells[idx(jr,ji)] == ('B' if color=='A' else 'A') and self.cells[idx(nr,ni)] == '.':
                    return True
        return False

    def generate_captures_from(self, k, color):
        r, i = rc_from_idx(k)
        captures = []
        for nr, ni in neighbors(r, i):
            jumped = between((r,i), (nr,ni))
            if jumped is None:
                continue
            jr, ji = jumped
            jk = idx(jr,ji)
            nk = idx(nr,ni)
            if self.cells[jk] == ('B' if color=='A' else 'A') and self.cells[nk] == '.':
                captures.append((nr,ni,jk))
        return captures

    def generate_all_moves(self, color):
        moves = []
        has_cap = self.has_capture(color)
        if has_cap:
            # all capture chains
            for k in range(24):
                if self.cells[k]!= color:
                    continue
                self._chain_dfs(k, color, [k], moves)
            return moves
        # slides
        for k in range(24):
            if self.cells[k]!= color:
                continue
            r, i = rc_from_idx(k)
            for nr, ni in neighbors(r, i):
                nk = idx(nr,ni)
                if self.cells[nk] == '.':
                    moves.append([(r,i),(nr,ni)])
        return moves

    def _chain_dfs(self, k, color, path, out):
        r, i = rc_from_idx(k)
        extended = False
        for nr, ni in neighbors(r, i):
            jumped = between((r,i), (nr,ni))
            if jumped is None:
                continue
            jr, ji = jumped
            jk = idx(jr,ji)
            nk = idx(nr,ni)
            if self.cells[jk] == ('B' if color=='A' else 'A') and self.cells[nk] == '.':
                extended = True
                # simulate jump
                old_src, old_jumped, old_dst = self.cells[k], self.cells[jk], self.cells[nk]
                self.cells[k] = '.'
                self.cells[jk] = '.'
                self.cells[nk] = color
                self._chain_dfs(nk, color, path + [(nr,ni)], out)
                # undo
                self.cells[k], self.cells[jk], self.cells[nk] = old_src, old_jumped, old_dst
        if not extended and len(path) > 1:
            out.append(path[:])

    def make_move(self, path):
        captured = 0
        if len(path) == 2: # slide
            r1,i1 = path[0]; r2,i2 = path[1]
            k1, k2 = idx(r1,i1), idx(r2,i2)
            self.cells = self.cells
            self.cells = '.'
            self.plies_no_capture += 1
        else: # capture chain
            for j in range(len(path)-1):
                r1,i1 = path[j]; r2,i2 = path[j+1]
                jumped = between(path[j], path[j+1])
                jr, ji = jumped
                jk = idx(jr,ji)
                k1, k2 = idx(r1,i1), idx(r2,i2)
                self.cells = self.cells
                self.cells = '.'
                self.cells[jk] = '.'
                captured += 1
            self.plies_no_capture = 0
        self.to_move = 'B' if self.to_move == 'A' else 'A'
        self._record_pos()
        return captured

    def is_draw_by_40(self):
        return self.plies_no_capture >= 40

    def is_draw_by_rep(self):
        return self.positions[(tuple(self.cells), self.to_move)] >= 3

    def terminal(self):
        a_cnt = self.piece_count('A')
        b_cnt = self.piece_count('B')
        if a_cnt == 0: return 'B_WINS'
        if b_cnt == 0: return 'A_WINS'
        if not self.generate_all_moves(self.to_move): return ('B_STALEMATED' if self.to_move=='A' else 'A_STALEMATED')
        if self.is_draw_by_40() or self.is_draw_by_rep(): return 'DRAW'
        return None

    def eval(self, my_color):
        # material + mobility + center control
        enemy = 'B' if my_color=='A' else 'A'
        my_p = self.piece_count(my_color)
        en_p = self.piece_count(enemy)
        score = (my_p - en_p) * 1000

        # mobility
        my_mob = len(self.generate_all_moves(my_color))
        en_mob = len(self.generate_all_moves(enemy))
        score += (my_mob - en_mob) * 10

        # center control: pieces on inner rings worth more
        center_bonus = 0
        for k in range(24):
            if self.cells[k] == my_color:
                r,_ = rc_from_idx(k)
                center_bonus += (3-r)*5
            elif self.cells[k] == enemy:
                r,_ = rc_from_idx(k)
                center_bonus -= (3-r)*5
        score += center_bonus
        return score

def format_move(path):
    return "MOVE " + " -> ".join(f"{r},{i}" for r,i in path)

def parse_board(tokens):
    b = Board()
    b.cells = tokens[:]
    return b

def main():
    botname = os.environ.get("BOTNAME", "")
    if not botname or not all(c.isalnum() or c in '_-' for c in botname) or len(botname)>32:
        sys.exit(0)

    sock = socket.create_connection((HOST, PORT))
    rfile = sock.makefile('r')
    wfile = sock.makefile('w')

    def send(line):
        wfile.write(line + "\n")
        wfile.flush()

    send(botname)

    board = None
    my_color = None
    game_start_time = 0

    while True:
        line = rfile.readline()
        if not line:
            break
        line = line.rstrip("\n")
        if not line:
            continue

        if line.startswith("MATCH"):
            continue

        if line.startswith("GAME"):
            _, g, color = line.split()
            my_color = color
            board = None
            game_start_time = time.time()
            continue

        if line.startswith("BOARD"):
            _, *cells = line.split()
            board = parse_board(cells)
            board.to_move = my_color
            continue

        if line == "TURN":
            time_left = TIME_BUDGET - (time.time() - game_start_time)
            if time_left <= 0.5:
                # no time, make random legal move
                moves = board.generate_all_moves(my_color)
                move = random.choice(moves) if moves else [(0,0),(0,1)]
            else:
                move = iterative_deepening(board, my_color, time_left)
            send(format_move(move))
            board.make_move(move)
            continue

        if line.startswith("OPP"):
            _, moveline = line.split(" ",1)
            path = parse_move(moveline)
            board.make_move(path)
            continue

        if line.startswith("GAME_END"):
            board = None
            continue

        if line.startswith("TOURNAMENT_END"):
            break

    sock.close()

def parse_move(s):
    parts = s.split(" -> ")
    return [tuple(map(int,p.split(","))) for p in parts]

def iterative_deepening(board, my_color, time_left):
    best_move = None
    depth = 1
    start = time.time()
    while time.time() - start < time_left*0.9 and depth <= 6:
        move, _ = alpha_beta(board, my_color, depth, -INF, INF, start, time_left)
        if move is not None:
            best_move = move
        depth += 1
    return best_move if best_move else board.generate_all_moves(my_color)[0]

def alpha_beta(board, my_color, depth, alpha, beta, start, time_left):
    if time.time() - start > time_left*0.9:
        return None, board.eval(my_color)

    term = board.terminal()
    if term is not None:
        if term == f"{my_color}_WINS": return None, INF
        if term == f"{'B' if my_color=='A' else 'A'}_WINS": return None, -INF
        return None, 0
    if depth == 0:
        return None, board.eval(my_color)

    moves = board.generate_all_moves(board.to_move)
    if not moves:
        return None, board.eval(my_color)

    # move ordering: captures first
    moves.sort(key=lambda m: len(m)>2, reverse=True)

    best_move = None
    if board.to_move == my_color:
        best_val = -INF
        for m in moves:
            nb = board.copy()
            nb.make_move(m)
            _, val = alpha_beta(nb, my_color, depth-1, alpha, beta, start, time_left)
            if val > best_val:
                best_val = val
                best_move = m
            alpha = max(alpha, val)
            if alpha >= beta:
                break
        return best_move, best_val
    else:
        best_val = INF
        for m in moves:
            nb = board.copy()
            nb.make_move(m)
            _, val = alpha_beta(nb, my_color, depth-1, alpha, beta, start, time_left)
            if val < best_val:
                best_val = val
                best_move = m
            beta = min(beta, val)
            if alpha >= beta:
                break
        return best_move, best_val

if __name__ == "__main__":
    main()