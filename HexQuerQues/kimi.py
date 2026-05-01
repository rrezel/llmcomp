# HexQuerQues Bot — Standard Library Only
# Negamax with iterative deepening, alpha-beta pruning

import os
import socket
import time

# ----------------------------------------------------------------------
# Board geometry
# ----------------------------------------------------------------------
RINGS = 4
VERTICES = 6
CELLS = RINGS * VERTICES
EMPTY = '.'

# Precompute neighbors (slides) and jumps (captures) for each cell index
NEIGHBORS = [[] for _ in range(CELLS)]   # list of neighbor indices
JUMPS = [[] for _ in range(CELLS)]       # list of (jumped_idx, land_idx)

for idx in range(CELLS):
    r, i = divmod(idx, VERTICES)
    # Ring neighbors
    NEIGHBORS[idx].append(r * VERTICES + (i + 1) % VERTICES)
    NEIGHBORS[idx].append(r * VERTICES + (i - 1) % VERTICES)
    # Radial neighbors
    if r > 0:
        NEIGHBORS[idx].append((r - 1) * VERTICES + i)
    if r < RINGS - 1:
        NEIGHBORS[idx].append((r + 1) * VERTICES + i)

    # Same-ring jumps
    JUMPS[idx].append((r * VERTICES + (i + 1) % VERTICES,
                       r * VERTICES + (i + 2) % VERTICES))
    JUMPS[idx].append((r * VERTICES + (i - 1) % VERTICES,
                       r * VERTICES + (i - 2) % VERTICES))
    # Radial jumps (three collinear cells on a spoke)
    if r == 0:
        JUMPS[idx].append((1 * VERTICES + i, 2 * VERTICES + i))
    elif r == 1:
        JUMPS[idx].append((2 * VERTICES + i, 3 * VERTICES + i))
    elif r == 2:
        JUMPS[idx].append((1 * VERTICES + i, 0 * VERTICES + i))
    elif r == 3:
        JUMPS[idx].append((2 * VERTICES + i, 1 * VERTICES + i))


# ----------------------------------------------------------------------
# Move formatting / parsing
# ----------------------------------------------------------------------
def format_move(move):
    """Convert internal move (list of indices) to wire format."""
    return "MOVE " + " -> ".join(f"{idx // VERTICES},{idx % VERTICES}" for idx in move)


def parse_move(move_line):
    """Parse a wire-format MOVE line into a list of indices."""
    # skip leading "MOVE "
    coords = move_line[5:].split(' -> ')
    return [int(c.split(',')[0]) * VERTICES + int(c.split(',')[1]) for c in coords]


# ----------------------------------------------------------------------
# Move application
# ----------------------------------------------------------------------
def apply_move(board, move, player):
    """Return a new board tuple after playing *move* for *player*."""
    b = list(board)
    start = move[0]
    end = move[-1]
    b[start] = EMPTY

    # Slide?
    if len(move) == 2 and end in NEIGHBORS[start]:
        b[end] = player
        return tuple(b)

    # Capture chain
    for j in range(len(move) - 1):
        curr = move[j]
        nxt = move[j + 1]
        curr_r, curr_i = divmod(curr, VERTICES)
        nxt_r, nxt_i = divmod(nxt, VERTICES)
        if curr_r == nxt_r:
            diff = (nxt_i - curr_i) % VERTICES
            if diff == 2:
                jumped_i = (curr_i + 1) % VERTICES
            else:  # diff == 4  (i.e. -2 mod 6)
                jumped_i = (curr_i - 1) % VERTICES
            jumped = curr_r * VERTICES + jumped_i
        else:
            jumped_r = (curr_r + nxt_r) // 2
            jumped = jumped_r * VERTICES + curr_i
        b[jumped] = EMPTY

    b[end] = player
    return tuple(b)


# ----------------------------------------------------------------------
# Legal-move generation
# ----------------------------------------------------------------------
def _piece_captures(board, start_idx, player):
    """Return all complete capture chains starting from start_idx."""
    enemy = 'B' if player == 'A' else 'A'
    chains = []
    b = list(board)
    b[start_idx] = EMPTY  # piece leaves start

    def dfs(curr_idx, visited, path):
        found = False
        for jumped_idx, land_idx in JUMPS[curr_idx]:
            if b[jumped_idx] != enemy:
                continue
            if b[land_idx] != EMPTY:
                continue
            if land_idx in visited:
                continue

            # execute jump temporarily
            b[jumped_idx] = EMPTY
            b[land_idx] = player

            new_visited = visited | {land_idx} if land_idx != start_idx else visited
            dfs(land_idx, new_visited, path + [land_idx])
            found = True

            # backtrack
            b[land_idx] = EMPTY
            b[jumped_idx] = enemy

        if not found and len(path) > 1:
            chains.append(path[:])

    dfs(start_idx, set(), [start_idx])
    b[start_idx] = player
    return chains


def all_captures(board, player):
    caps = []
    for idx in range(CELLS):
        if board[idx] == player:
            caps.extend(_piece_captures(board, idx, player))
    caps.sort(key=lambda c: -len(c))   # longer chains first
    return caps


def all_slides(board, player):
    slides = []
    for idx in range(CELLS):
        if board[idx] == player:
            for nidx in NEIGHBORS[idx]:
                if board[nidx] == EMPTY:
                    slides.append([idx, nidx])
    return slides


def legal_moves(board, player):
    caps = all_captures(board, player)
    if caps:
        return caps
    return all_slides(board, player)


def any_legal_move(board, player):
    moves = legal_moves(board, player)
    return format_move(moves[0]) if moves else "MOVE 0,0 -> 0,1"


# ----------------------------------------------------------------------
# Evaluation
# ----------------------------------------------------------------------
def evaluate(board, player):
    enemy = 'B' if player == 'A' else 'A'
    my_cnt = board.count(player)
    opp_cnt = board.count(enemy)

    if opp_cnt == 0:
        return 100000
    if my_cnt == 0:
        return -100000

    score = (my_cnt - opp_cnt) * 100

    # mobility bonus
    for idx in range(CELLS):
        if board[idx] == player:
            for nidx in NEIGHBORS[idx]:
                if board[nidx] == EMPTY:
                    score += 2
        elif board[idx] == enemy:
            for nidx in NEIGHBORS[idx]:
                if board[nidx] == EMPTY:
                    score -= 2
    return score


# ----------------------------------------------------------------------
# Search
# ----------------------------------------------------------------------
def negamax(board, player, depth, alpha, beta, start_time, time_limit):
    if time.time() - start_time > time_limit:
        raise TimeoutError()

    enemy = 'B' if player == 'A' else 'A'

    if board.count(player) == 0:
        return -100000, None
    if board.count(enemy) == 0:
        return 100000, None

    moves = legal_moves(board, player)
    if not moves:
        return -100000, None

    if depth == 0:
        return evaluate(board, player), None

    best_move = None
    best_score = -float('inf')

    for move in moves:
        new_board = apply_move(board, move, player)
        score, _ = negamax(new_board, enemy, depth - 1,
                           -beta, -alpha, start_time, time_limit)
        score = -score

        if score > best_score:
            best_score = score
            best_move = move

        alpha = max(alpha, score)
        if alpha >= beta:
            break

    return best_score, best_move


def find_best_move(board, player, time_remaining):
    moves = legal_moves(board, player)
    if not moves:
        return None
    if len(moves) == 1:
        return format_move(moves[0])

    # emergency: almost no time left
    if time_remaining < 0.1:
        return format_move(moves[0])

    time_limit = max(0.05, min(1.5, time_remaining / 15.0))
    start_time = time.time()
    best_move = moves[0]

    for depth in range(1, 20):
        if time.time() - start_time > time_limit:
            break
        try:
            _, move = negamax(board, player, depth,
                              -float('inf'), float('inf'),
                              start_time, time_limit)
            if move is not None:
                best_move = move
        except TimeoutError:
            break

        if time.time() - start_time > time_limit * 0.85:
            break

    return format_move(best_move)


# ----------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------
def main():
    botname = os.environ['BOTNAME'].rstrip('\n')

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))

    infile = sock.makefile('r')
    outfile = sock.makefile('w')

    outfile.write(botname + '\n')
    outfile.flush()

    board = None
    my_color = None
    time_remaining = 30.0
    pending_move = None

    try:
        for line in infile:
            line = line.rstrip('\n')
            if not line:
                continue

            parts = line.split()
            if not parts:
                continue

            cmd = parts[0]

            if cmd == 'MATCH':
                pass

            elif cmd == 'GAME':
                my_color = parts[2]
                time_remaining = 30.0
                pending_move = None
                board = None

            elif cmd == 'BOARD':
                board = tuple(parts[1:])

            elif cmd == 'TURN':
                if board is None or my_color is None:
                    continue

                turn_start = time.time()
                fallback = any_legal_move(board, my_color)

                try:
                    move = find_best_move(board, my_color, time_remaining)
                except Exception:
                    move = fallback

                pending_move = move
                outfile.write(move + '\n')
                outfile.flush()
                time_remaining -= (time.time() - turn_start)

            elif cmd == 'OK':
                if pending_move is not None and board is not None:
                    move = parse_move(pending_move)
                    board = apply_move(board, move, my_color)
                    pending_move = None

            elif cmd == 'OPP':
                if board is not None and my_color is not None:
                    opp_line = ' '.join(parts[1:])
                    move = parse_move(opp_line)
                    opp_color = 'B' if my_color == 'A' else 'A'
                    board = apply_move(board, move, opp_color)

            elif cmd == 'DQ':
                pending_move = None

            elif cmd == 'GAME_END':
                pending_move = None
                board = None

            elif cmd == 'MATCH_END':
                pass

            elif cmd == 'TOURNAMENT_END':
                break

    finally:
        sock.close()


if __name__ == '__main__':
    main()