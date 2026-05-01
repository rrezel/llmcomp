# bot author: GLM 5.1 (z-ai/glm-5.1 via OpenRouter)
# bot author: Claude 3.5 Sonnet

import os
import socket
import time

# --- Precomputed tables ---
NEIGHBORS = {}
JUMP_TARGETS = {}
ATTACKERS = {}

def _precompute():
    for r in range(4):
        for i in range(6):
            idx = r * 6 + i
            nbrs = []
            nbrs.append(r * 6 + (i + 1) % 6)
            nbrs.append(r * 6 + (i - 1) % 6)
            if r > 0:
                nbrs.append((r - 1) * 6 + i)
            if r < 3:
                nbrs.append((r + 1) * 6 + i)
            NEIGHBORS[idx] = nbrs

            jumps = []
            for d in (1, -1):
                jumped_i = (i + d) % 6
                land_i = (i + 2 * d) % 6
                jumps.append((r * 6 + land_i, r * 6 + jumped_i))
            if r + 2 <= 3:
                jumps.append(((r + 2) * 6 + i, (r + 1) * 6 + i))
            if r - 2 >= 0:
                jumps.append(((r - 2) * 6 + i, (r - 1) * 6 + i))
            JUMP_TARGETS[idx] = jumps

            atks = []
            for d in (1, -1):
                atk_i = (i + d) % 6
                land_i2 = (i - d) % 6
                atks.append((r * 6 + atk_i, r * 6 + land_i2))
            if r == 1:
                atks.append((2 * 6 + i, 0 * 6 + i))
                atks.append((0 * 6 + i, 2 * 6 + i))
            elif r == 2:
                atks.append((3 * 6 + i, 1 * 6 + i))
                atks.append((1 * 6 + i, 3 * 6 + i))
            ATTACKERS[idx] = atks

_precompute()

def _idx(r, i):
    return r * 6 + i

def _ri(index):
    return index // 6, index % 6

def _init_board():
    board = ['.'] * 24
    for i in (0, 2, 4):
        board[_idx(3, i)] = 'A'
        board[_idx(2, i)] = 'A'
    for i in (1, 3, 5):
        board[_idx(3, i)] = 'B'
        board[_idx(2, i)] = 'B'
    return board

# --- Move generation ---

def _find_chains(board, start, color, enemy):
    results = []
    stack = [(start, [start], frozenset())]
    while stack:
        curr, path, captured = stack.pop()
        valid = []
        for land, jumped in JUMP_TARGETS[curr]:
            if jumped in captured:
                continue
            if board[jumped] != enemy:
                continue
            can_land = False
            if land in captured:
                can_land = True
            elif land in path[:-1]:
                can_land = True
            elif board[land] == '.':
                can_land = True
            if can_land:
                valid.append((land, jumped))
        if not valid:
            if len(path) > 1:
                results.append(path[:])
        else:
            for land, jumped in valid:
                stack.append((land, path + [land], captured | {jumped}))
    return results

def _get_captures(board, color):
    enemy = 'B' if color == 'A' else 'A'
    captures = []
    for pos in range(24):
        if board[pos] == color:
            chains = _find_chains(board, pos, color, enemy)
            captures.extend(chains)
    return captures

def _get_slides(board, color):
    slides = []
    for pos in range(24):
        if board[pos] == color:
            for nbr in NEIGHBORS[pos]:
                if board[nbr] == '.':
                    slides.append([pos, nbr])
    return slides

def _get_all_moves(board, color):
    captures = _get_captures(board, color)
    if captures:
        return captures
    return _get_slides(board, color)

# --- Board manipulation ---

def _is_jump_segment(from_idx, to_idx):
    r1, i1 = _ri(from_idx)
    r2, i2 = _ri(to_idx)
    if r1 == r2 and (i2 == (i1 + 2) % 6 or i2 == (i1 - 2) % 6):
        return True
    if i1 == i2 and abs(r2 - r1) == 2:
        return True
    return False

def _get_jumped_idx(from_idx, to_idx):
    r1, i1 = _ri(from_idx)
    r2, i2 = _ri(to_idx)
    if r1 == r2:
        if i2 == (i1 + 2) % 6:
            return _idx(r1, (i1 + 1) % 6)
        if i2 == (i1 - 2) % 6:
            return _idx(r1, (i1 - 1) % 6)
    if i1 == i2:
        if r2 == r1 + 2:
            return _idx(r1 + 1, i1)
        if r2 == r1 - 2:
            return _idx(r1 - 1, i1)
    return None

def _apply_move(board, move, color):
    nb = board[:]
    nb[move[0]] = '.'
    is_cap = len(move) > 2
    if not is_cap and len(move) == 2:
        is_cap = _is_jump_segment(move[0], move[1])
    if is_cap:
        for seg in range(1, len(move)):
            jumped = _get_jumped_idx(move[seg - 1], move[seg])
            if jumped is not None:
                nb[jumped] = '.'
    nb[move[-1]] = color
    return nb

# --- Formatting and parsing ---

def _format_move(move):
    parts = []
    for pos in move:
        r, i = _ri(pos)
        parts.append(f"{r},{i}")
    return "MOVE " + " -> ".join(parts)

def _parse_move(s):
    if s.startswith('MOVE '):
        s = s[5:]
    parts = s.split(' -> ')
    positions = []
    for part in parts:
        r, i = part.split(',')
        positions.append(_idx(int(r), int(i)))
    return positions

def _parse_board(line):
    tokens = line.split()
    board = []
    for k in range(24):
        board.append(tokens[k + 1])
    return board

# --- Evaluation ---

_RING_VAL = [15, 12, 10, 5]

def _evaluate(board, my_color):
    enemy = 'B' if my_color == 'A' else 'A'
    mc = 0
    ec = 0
    mv = 0
    ev = 0
    mt = 0
    et = 0
    for pos in range(24):
        c = board[pos]
        if c == my_color:
            mc += 1
            mv += _RING_VAL[pos // 6]
            for atk, land in ATTACKERS[pos]:
                if board[atk] == enemy and board[land] == '.':
                    mt += 1
                    break
        elif c == enemy:
            ec += 1
            ev += _RING_VAL[pos // 6]
            for atk, land in ATTACKERS[pos]:
                if board[atk] == my_color and board[land] == '.':
                    et += 1
                    break
    if ec == 0:
        return 100000
    if mc == 0:
        return -100000
    score = (mc - ec) * 1000
    score += (mv - ev)
    score -= mt * 80
    score += et * 80
    return score

# --- Search ---

def _minimax(board, color, depth, alpha, beta, my_color, deadline):
    if time.time() > deadline:
        return _evaluate(board, my_color)
    enemy_c = 'B' if color == 'A' else 'A'
    mc = 0
    ec = 0
    for pos in range(24):
        if board[pos] == my_color:
            mc += 1
        elif board[pos] == enemy_c:
            ec += 1
    if ec == 0:
        return 100000
    if mc == 0:
        return -100000
    moves = _get_all_moves(board, color)
    if not moves:
        return -100000 if color == my_color else 100000
    if depth <= 0:
        return _evaluate(board, my_color)
    moves.sort(key=lambda m: -len(m))
    if color == my_color:
        val = -200000
        for move in moves:
            nb = _apply_move(board, move, color)
            s = _minimax(nb, enemy_c, depth - 1, alpha, beta, my_color, deadline)
            if s > val:
                val = s
            if val > alpha:
                alpha = val
            if beta <= alpha:
                break
            if time.time() > deadline:
                break
        return val
    else:
        val = 200000
        for move in moves:
            nb = _apply_move(board, move, color)
            s = _minimax(nb, enemy_c, depth - 1, alpha, beta, my_color, deadline)
            if s < val:
                val = s
            if val < beta:
                beta = val
            if beta <= alpha:
                break
            if time.time() > deadline:
                break
        return val

def _find_best_move(board, color, time_limit):
    moves = _get_all_moves(board, color)
    if not moves:
        return None
    if len(moves) == 1:
        return moves[0]
    enemy = 'B' if color == 'A' else 'A'
    for move in moves:
        nb = _apply_move(board, move, color)
        if not any(c == enemy for c in nb):
            return move
    best_move = moves[0]
    start_time = time.time()
    deadline = start_time + time_limit
    for depth in range(1, 30):
        if time.time() > deadline - 0.005:
            break
        best_score = -200000
        current_best = None
        alpha = -200000
        beta = 200000
        for move in moves:
            if time.time() > deadline - 0.005:
                break
            nb = _apply_move(board, move, color)
            s = _minimax(nb, enemy, depth - 1, alpha, beta, color, deadline)
            if s > best_score:
                best_score = s
                current_best = move
            if s > alpha:
                alpha = s
        if current_best is not None:
            best_move = current_best
        if best_score >= 100000:
            break
        if current_best is not None and current_best in moves:
            moves.remove(current_best)
            moves.insert(0, current_best)
    return best_move

# --- Main loop ---

def main():
    botname = os.environ['BOTNAME']
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.sendall((botname + '\n').encode())
    f = sock.makefile('r')
    board = None
    my_color = None
    game_time_used = 0.0
    move_count = 0
    pending_move = None

    while True:
        line = f.readline()
        if not line:
            break
        line = line.rstrip('\n')
        if not line:
            continue

        if line.startswith('MATCH '):
            pass
        elif line.startswith('GAME '):
            parts = line.split()
            my_color = parts[2]
            game_time_used = 0.0
            move_count = 0
            pending_move = None
        elif line.startswith('BOARD '):
            board = _parse_board(line)
        elif line == 'TURN':
            move_count += 1
            time_remaining = 28.0 - game_time_used
            est_left = max(25 - move_count, 3)
            time_for_move = time_remaining / est_left
            time_for_move = max(time_for_move, 0.05)
            time_for_move = min(time_for_move, 8.0)
            t0 = time.time()
            move = _find_best_move(board, my_color, time_for_move)
            elapsed = time.time() - t0
            game_time_used += elapsed
            if move is None:
                moves = _get_all_moves(board, my_color)
                move = moves[0] if moves else None
            if move is not None:
                pending_move = move
                msg = _format_move(move) + '\n'
                sock.sendall(msg.encode())
        elif line.startswith('OK '):
            if pending_move is not None:
                board = _apply_move(board, pending_move, my_color)
                pending_move = None
        elif line.startswith('OPP '):
            opp_str = line[4:]
            opp_move = _parse_move(opp_str)
            opp_color = 'B' if my_color == 'A' else 'A'
            board = _apply_move(board, opp_move, opp_color)
        elif line.startswith('DQ '):
            pending_move = None
        elif line.startswith('GAME_END'):
            pending_move = None
        elif line.startswith('MATCH_END'):
            pass
        elif line == 'TOURNAMENT_END':
            break

    try:
        f.close()
    except Exception:
        pass
    try:
        sock.close()
    except Exception:
        pass

if __name__ == '__main__':
    main()
