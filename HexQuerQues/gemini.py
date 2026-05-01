# bot author: Gemini 3.1 Pro
import os
import sys
import socket
import time
import random

# --- Board Representation and Precomputation ---
# The board is represented as a 1D tuple/list of 24 characters ('.', 'A', 'B').
# Index mapping: idx = r * 6 + i

SLIDES = {i: [] for i in range(24)}
JUMPS = {i: [] for i in range(24)}

for r in range(4):
    for i in range(6):
        idx = r * 6 + i
        # Slides
        SLIDES[idx].append(r * 6 + (i + 1) % 6)
        SLIDES[idx].append(r * 6 + (i - 1) % 6)
        if r > 0: SLIDES[idx].append((r - 1) * 6 + i)
        if r < 3: SLIDES[idx].append((r + 1) * 6 + i)

        # Jumps
        # Same ring
        JUMPS[idx].append((r * 6 + (i + 1) % 6, r * 6 + (i + 2) % 6))
        JUMPS[idx].append((r * 6 + (i - 1) % 6, r * 6 + (i - 2) % 6))
        # Radial
        if r <= 1: JUMPS[idx].append(((r + 1) * 6 + i, (r + 2) * 6 + i))
        if r >= 2: JUMPS[idx].append(((r - 1) * 6 + i, (r - 2) * 6 + i))

RING_BONUS = [0, 2, 2, 0]

class TimeoutException(Exception):
    pass

# --- Game Logic ---

def get_moves(state, player):
    opp = 'B' if player == 'A' else 'A'
    jumps = []

    def dfs(curr, cur_state, path):
        possible_jumps = []
        for mid, dst in JUMPS[curr]:
            if cur_state[mid] == opp and cur_state[dst] == '.':
                possible_jumps.append((mid, dst))

        if not possible_jumps:
            if len(path) > 1:
                jumps.append(path)
            return

        for mid, dst in possible_jumps:
            next_state = list(cur_state)
            next_state[curr] = '.'  # Piece leaves
            next_state[mid] = '.'   # Enemy jumped and removed immediately
            next_state[dst] = player # Piece lands
            dfs(dst, next_state, path + [dst])

    my_pieces = [i for i, p in enumerate(state) if p == player]
    
    # 1. Mandatory jumps
    for p_idx in my_pieces:
        dfs(p_idx, list(state), [p_idx])

    if jumps:
        return jumps

    # 2. Slides
    slides = []
    for p_idx in my_pieces:
        for adj in SLIDES[p_idx]:
            if state[adj] == '.':
                slides.append([p_idx, adj])
                
    return slides

def apply_move(state, move_path, player):
    new_state = list(state)
    is_jump = (len(move_path) > 2) or (move_path[1] not in SLIDES[move_path[0]])
    new_state[move_path[0]] = '.'
    
    if is_jump:
        curr = move_path[0]
        for nxt in move_path[1:]:
            for m, d in JUMPS[curr]:
                if d == nxt:
                    new_state[m] = '.'
                    break
            curr = nxt
        new_state[curr] = player
    else:
        new_state[move_path[1]] = player
        
    return tuple(new_state)

def evaluate(state, player):
    score = 0
    for i, p in enumerate(state):
        if p == '.': continue
        r = i // 6
        val = 100 + RING_BONUS[r]
        if p == player:
            score += val
        else:
            score -= val
    return score

# --- AI Engine ---

def alphabeta(state, depth, alpha, beta, maximizing, player, start_time, time_limit):
    if time.time() - start_time > time_limit:
        raise TimeoutException()

    opp = 'B' if player == 'A' else 'A'
    current_player = player if maximizing else opp

    moves = get_moves(state, current_player)
    
    if not moves:
        return -10000 if maximizing else 10000

    if depth == 0:
        return evaluate(state, player)

    if maximizing:
        max_eval = -float('inf')
        for move in moves:
            next_state = apply_move(state, move, current_player)
            ev = alphabeta(next_state, depth - 1, alpha, beta, False, player, start_time, time_limit)
            max_eval = max(max_eval, ev)
            alpha = max(alpha, ev)
            if beta <= alpha: break
        return max_eval
    else:
        min_eval = float('inf')
        for move in moves:
            next_state = apply_move(state, move, current_player)
            ev = alphabeta(next_state, depth - 1, alpha, beta, True, player, start_time, time_limit)
            min_eval = min(min_eval, ev)
            beta = min(beta, ev)
            if beta <= alpha: break
        return min_eval

def get_best_move(state, player, time_limit):
    start_time = time.time()
    moves = get_moves(state, player)

    if not moves:
        return None
    if len(moves) == 1:
        return moves[0]

    random.shuffle(moves)
    # Order jumps first to improve alpha-beta pruning
    moves.sort(key=lambda m: len(m), reverse=True)

    global_best_move = moves[0]
    depth = 1

    try:
        while depth <= 20:
            best_score = -float('inf')
            current_best_move = moves[0]
            alpha = -float('inf')
            beta = float('inf')

            for move in moves:
                next_state = apply_move(state, move, player)
                score = alphabeta(next_state, depth - 1, alpha, beta, False, player, start_time, time_limit)
                
                if score > best_score:
                    best_score = score
                    current_best_move = move
                alpha = max(alpha, score)

            global_best_move = current_best_move
            
            if best_score > 9000:  # Forced win found
                break

            # Heuristic: if we used > 45% of our allotted time for this depth, abort deepening
            if time.time() - start_time > time_limit * 0.45:
                break

            depth += 1
    except TimeoutException:
        pass

    return global_best_move

# --- Network Client Loop ---

def main():
    bot_name = os.environ.get('BOTNAME')
    if not bot_name:
        sys.stderr.write("Error: BOTNAME environment variable not set.\n")
        sys.exit(1)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(('localhost', 7474))
    except Exception as e:
        sys.stderr.write(f"Failed to connect to localhost:7474: {e}\n")
        sys.exit(1)
        
    f = s.makefile('rw', encoding='utf-8')
    f.write(f"{bot_name}\n")
    f.flush()

    time_left = 30.0
    my_color = None
    board = tuple(['.'] * 24)
    pending_move = None

    while True:
        line = f.readline()
        if not line:
            break
            
        line = line.strip()
        if not line:
            continue

        parts = line.split()
        cmd = parts[0]

        if cmd == 'GAME':
            my_color = parts[2]
            time_left = 30.0
        elif cmd == 'BOARD':
            board = tuple(parts[1:])
        elif cmd == 'TURN':
            # Dynamic time management: assume ~15 critical moves remaining
            time_to_use = max(0.1, time_left / 15.0)
            
            start_think = time.time()
            best_move = get_best_move(board, my_color, time_to_use)
            time_spent = time.time() - start_think
            time_left -= time_spent
            
            # Fallback if move generation fails safely
            if not best_move:
                moves = get_moves(board, my_color)
                if moves:
                    best_move = moves[0]

            if best_move:
                move_str = "MOVE " + " -> ".join([f"{idx//6},{idx%6}" for idx in best_move])
                f.write(move_str + "\n")
                f.flush()
                pending_move = best_move
                
        elif cmd == 'OK':
            if pending_move:
                board = apply_move(board, pending_move, my_color)
                pending_move = None
        elif cmd == 'OPP':
            move_str = line[9:] # Strip "OPP MOVE "
            tokens = move_str.split(" -> ")
            opp_move = []
            for t in tokens:
                r, i = map(int, t.split(','))
                opp_move.append(r * 6 + i)
            
            opp_color = 'B' if my_color == 'A' else 'A'
            board = apply_move(board, opp_move, opp_color)
        elif cmd == 'TOURNAMENT_END':
            break

if __name__ == "__main__":
    main()