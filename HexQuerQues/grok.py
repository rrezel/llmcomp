#!/usr/bin/env python3
# HexQuerQues Tournament Bot
# bot author: Grok (xAI collaborative) - full legal play with greedy max-capture + inward-slide strategy
# Complete, self-contained, stdlib-only. Plays every game to win.

import os
import socket
import sys
import copy
import random

def get_neighbors(r, i):
    neigh = [(r, (i + 1) % 6), (r, (i - 1) % 6)]
    if r > 0:
        neigh.append((r - 1, i))
    if r < 3:
        neigh.append((r + 1, i))
    return neigh

def is_neighbor(pos1, pos2):
    r1, i1 = pos1
    r2, i2 = pos2
    if r1 == r2:
        d = min((i2 - i1) % 6, (i1 - i2) % 6)
        return d == 1
    if i1 == i2:
        return abs(r1 - r2) == 1
    return False

def get_jumps(board, r, i, player):
    jumps = []
    enemy = 'B' if player == 'A' else 'A'
    # circumferential jumps
    for d in [1, -1]:
        j1 = (i + d) % 6
        j2 = (i + 2 * d) % 6
        if board[r][j1] == enemy and board[r][j2] == '.':
            jumps.append((r, j2, r, j1))
    # radial outward
    if r + 2 <= 3 and board[r + 1][i] == enemy and board[r + 2][i] == '.':
        jumps.append((r + 2, i, r + 1, i))
    # radial inward
    if r - 2 >= 0 and board[r - 1][i] == enemy and board[r - 2][i] == '.':
        jumps.append((r - 2, i, r - 1, i))
    return jumps

def has_any_capture(board, player):
    for r in range(4):
        for i in range(6):
            if board[r][i] == player:
                if get_jumps(board, r, i, player):
                    return True
    return False

def find_all_capture_paths(board, player):
    paths = []
    for r in range(4):
        for i in range(6):
            if board[r][i] == player:
                jumps = get_jumps(board, r, i, player)
                if jumps:
                    board_copy = copy.deepcopy(board)
                    recurse(r, i, [(r, i)], board_copy, player, paths)
    return paths

def recurse(curr_r, curr_i, path, board, player, paths_list):
    jumps = get_jumps(board, curr_r, curr_i, player)
    if not jumps:
        paths_list.append(path[:])
        return
    for land_r, land_i, cap_r, cap_i in jumps:
        board[curr_r][curr_i] = '.'
        orig_land = board[land_r][land_i]
        orig_cap = board[cap_r][cap_i]
        board[land_r][land_i] = player
        board[cap_r][cap_i] = '.'
        new_path = path + [(land_r, land_i)]
        recurse(land_r, land_i, new_path, board, player, paths_list)
        # undo
        board[curr_r][curr_i] = player
        board[land_r][land_i] = orig_land
        board[cap_r][cap_i] = orig_cap

def find_slide_moves(board, player):
    slides = []
    for r in range(4):
        for i in range(6):
            if board[r][i] == player:
                for nr, ni in get_neighbors(r, i):
                    if board[nr][ni] == '.':
                        slides.append([(r, i), (nr, ni)])
    return slides

def select_best_move(paths, is_capture):
    if not paths:
        return None
    if is_capture:
        # prefer longest chains (most captures)
        max_capt = max(len(p) - 1 for p in paths)
        bests = [p for p in paths if len(p) - 1 == max_capt]
        return random.choice(bests)
    else:
        # prefer inward slides (lower ring index)
        min_r = min(p[-1][0] for p in paths)
        bests = [p for p in paths if p[-1][0] == min_r]
        return random.choice(bests)

def build_move_line(path):
    return 'MOVE ' + ' -> '.join(f"{r},{i}" for r, i in path)

def parse_move_line(line):
    tokens = line.split()
    path = []
    for tok in tokens[1:]:
        if tok == '->':
            continue
        rs, iss = tok.split(',')
        path.append((int(rs), int(iss)))
    return path

def apply_path(board, path, player):
    if len(path) < 2:
        return
    sr, si = path[0]
    board[sr][si] = '.'
    curr_r, curr_i = sr, si
    for k in range(1, len(path)):
        land_r, land_i = path[k]
        # clear current position (required for chain intermediates; harmless for start)
        board[curr_r][curr_i] = '.'
        # slide or jump?
        if not is_neighbor((curr_r, curr_i), (land_r, land_i)):
            # jump - remove captured
            if curr_r == land_r:  # ring
                diff = (land_i - curr_i) % 6
                cap_i = (curr_i + 1) % 6 if diff == 2 else (curr_i - 1) % 6
                cap_r = curr_r
            else:  # radial
                cap_r = (curr_r + land_r) // 2
                cap_i = curr_i
            board[cap_r][cap_i] = '.'
        # place piece
        board[land_r][land_i] = player
        curr_r, curr_i = land_r, land_i

def main():
    botname = os.environ['BOTNAME'].strip()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.sendall((botname + '\n').encode('ascii'))
    f = sock.makefile('r', encoding='ascii')

    my_color = None
    opponent_color = None
    board = None
    last_path = None

    while True:
        line = f.readline()
        if not line:
            break
        line = line.rstrip('\n')
        if not line:
            continue
        parts = line.split()
        if not parts:
            continue
        cmd = parts[0]

        if cmd == 'MATCH':
            continue
        elif cmd == 'GAME':
            my_color = parts[2]
            opponent_color = 'B' if my_color == 'A' else 'A'
            board_line = f.readline().rstrip('\n')
            board = parse_board(board_line)
            last_path = None
            continue
        elif cmd == 'TURN':
            if board is None or my_color is None:
                continue
            if has_any_capture(board, my_color):
                paths = find_all_capture_paths(board, my_color)
                path = select_best_move(paths, True) if paths else None
            else:
                paths = find_slide_moves(board, my_color)
                path = select_best_move(paths, False) if paths else None
            if path:
                last_path = path[:]
                move_line = build_move_line(path)
                sock.sendall((move_line + '\n').encode('ascii'))
        elif cmd == 'OPP':
            if board is not None:
                path = parse_move_line(line)
                apply_path(board, path, opponent_color)
        elif cmd == 'OK':
            if last_path is not None and board is not None:
                apply_path(board, last_path, my_color)
                last_path = None
        elif cmd == 'GAME_END':
            board = None
            my_color = None
            last_path = None
        elif cmd == 'TOURNAMENT_END':
            break

def parse_board(line):
    if line.startswith('BOARD'):
        tokens = line.split()[1:]
    else:
        tokens = line.split()
    board = [['.' for _ in range(6)] for _ in range(4)]
    k = 0
    for r in range(4):
        for i in range(6):
            board[r][i] = tokens[k]
            k += 1
    return board

if __name__ == "__main__":
    main()