# bot author: HexQuerQuesBot-1.0
import socket
import os
import sys
import time
import random
import collections

# --- Constants and board topology -------------------------------------------------
RINGS = 4
SIDES = 6
CELL_COUNT = RINGS * SIDES

def coord_to_idx(r, i):
    return r * 6 + i

def idx_to_coord(idx):
    return divmod(idx, 6)

# Precomputed slide neighbours (line neighbours)
NEIGHBORS = [[] for _ in range(CELL_COUNT)]
# Precomputed jump vectors: (jumped_idx, landing_idx) for each source
JUMPS = [[] for _ in range(CELL_COUNT)]

for r in range(RINGS):
    for i in range(SIDES):
        idx = coord_to_idx(r, i)
        # same ring neighbours
        NEIGHBORS[idx].append(coord_to_idx(r, (i + 1) % SIDES))
        NEIGHBORS[idx].append(coord_to_idx(r, (i - 1) % SIDES))
        # radial neighbours
        if r < 3:
            NEIGHBORS[idx].append(coord_to_idx(r + 1, i))
        if r > 0:
            NEIGHBORS[idx].append(coord_to_idx(r - 1, i))

        # Same‑ring jumps (both directions)
        JUMPS[idx].append((coord_to_idx(r, (i + 1) % SIDES),
                           coord_to_idx(r, (i + 2) % SIDES)))
        JUMPS[idx].append((coord_to_idx(r, (i - 1) % SIDES),
                           coord_to_idx(r, (i - 2) % SIDES)))
        # Radial outward jump
        if r + 2 <= 3:
            JUMPS[idx].append((coord_to_idx(r + 1, i),
                               coord_to_idx(r + 2, i)))
        # Radial inward jump
        if r - 2 >= 0:
            JUMPS[idx].append((coord_to_idx(r - 1, i),
                               coord_to_idx(r - 2, i)))

# --- Zobrist hashing ------------------------------------------------------------
random.seed(2024)                     # fixed seed for reproducibility
ZOBRIST_CELL = [[random.getrandbits(64) for _ in range(3)] for _ in range(CELL_COUNT)]
ZOBRIST_TURN = random.getrandbits(64)

def piece_int(p):
    if p == 'A':
        return 1
    if p == 'B':
        return 2
    return 0

def zobrist_hash(board, turn):
    h = 0
    for idx, p in enumerate(board):
        h ^= ZOBRIST_CELL[idx][piece_int(p)]
    if turn == 'A':
        h ^= ZOBRIST_TURN
    return h

# --- State representations ------------------------------------------------------
StateMin = collections.namedtuple('StateMin', ['board', 'turn', 'halfmove_clock'])

class GameState:
    """Full game state including repetition counts."""
    __slots__ = ('board', 'turn', 'halfmove_clock', 'pos_counts')
    def __init__(self, board, turn, halfmove_clock, pos_counts):
        self.board = board
        self.turn = turn
        self.halfmove_clock = halfmove_clock
        self.pos_counts = pos_counts

# --- Move generation (capture obligations apply) ---------------------------------
def get_captures_for_pos(board, enemy, idx):
    """Return list of (jumped_idx, landing_idx) that are legal right now."""
    caps = []
    for jumped, land in JUMPS[idx]:
        if board[jumped] == enemy and board[land] == '.':
            caps.append((jumped, land))
    return caps

def _gen_chains(board, turn, enemy, cur_idx, chain_sofar):
    """Yield all maximal capture chains starting from cur_idx (already part of chain)."""
    caps = get_captures_for_pos(board, enemy, cur_idx)
    if not caps:
        yield chain_sofar[:]          # chain complete, make a copy
        return
    for jumped, land in caps:
        # apply jump
        board[cur_idx] = '.'
        board[jumped] = '.'
        board[land] = turn
        chain_sofar.append(land)
        yield from _gen_chains(board, turn, enemy, land, chain_sofar)
        # undo
        chain_sofar.pop()
        board[land] = '.'
        board[cur_idx] = turn
        board[jumped] = enemy

def legal_moves(state: StateMin):
    """List of legal moves, respecting the forced‑capture rule."""
    board = state.board
    turn = state.turn
    enemy = 'A' if turn == 'B' else 'B'

    # check whether any friendly piece can capture
    has_cap = False
    for idx in range(CELL_COUNT):
        if board[idx] == turn and get_captures_for_pos(board, enemy, idx):
            has_cap = True
            break

    if has_cap:
        # forced capture – generate all maximal chains
        moves = []
        for src_idx in range(CELL_COUNT):
            if board[src_idx] == turn:
                caps = get_captures_for_pos(board, enemy, src_idx)
                if caps:
                    # work on a copy so the generator doesn't trash the original
                    board_copy = board[:]
                    for chain in _gen_chains(board_copy, turn, enemy, src_idx, [src_idx]):
                        moves.append(chain)
        return moves
    else:
        # no capture – simple slides
        moves = []
        for idx in range(CELL_COUNT):
            if board[idx] == turn:
                for nidx in NEIGHBORS[idx]:
                    if board[nidx] == '.':
                        moves.append([idx, nidx])
        return moves

# --- Move application (game state with repetition) --------------------------------
def apply_move_to_game(state: GameState, move):
    """Return (new_GameState, n_captures)."""
    board = state.board[:]
    turn = state.turn
    enemy = 'A' if turn == 'B' else 'B'
    n_captures = 0

    for i in range(len(move) - 1):
        src = move[i]
        dst = move[i + 1]
        r_s, i_s = divmod(src, 6)
        r_d, i_d = divmod(dst, 6)

        # slide?
        if ((r_s == r_d and (i_d == (i_s + 1) % 6 or i_d == (i_s - 1) % 6)) or
            (i_s == i_d and abs(r_d - r_s) == 1)):
            board[dst] = turn
            board[src] = '.'
        else:
            # jump – identify the enemy piece between src and dst
            if r_s == r_d:
                if i_d == (i_s + 2) % 6:
                    jumped = r_s * 6 + (i_s + 1) % 6
                else:
                    jumped = r_s * 6 + (i_s - 1) % 6
            else:
                if r_d == r_s + 2:
                    jumped = (r_s + 1) * 6 + i_s
                else:
                    jumped = (r_s - 1) * 6 + i_s
            board[jumped] = '.'
            board[src] = '.'
            board[dst] = turn
            n_captures += 1

    new_turn = 'B' if turn == 'A' else 'A'
    new_halfmove = 0 if n_captures > 0 else state.halfmove_clock + 1
    new_pos_counts = state.pos_counts.copy()
    h = zobrist_hash(board, new_turn)
    new_pos_counts[h] += 1
    return GameState(board, new_turn, new_halfmove, new_pos_counts), n_captures

# --- Minimal move application for search ------------------------------------------
def apply_move_minimal(state: StateMin, move):
    """Return a new StateMin after applying *move*."""
    board = state.board[:]
    turn = state.turn
    enemy = 'A' if turn == 'B' else 'B'
    n_captures = 0

    for i in range(len(move) - 1):
        src = move[i]
        dst = move[i + 1]
        r_s, i_s = divmod(src, 6)
        r_d, i_d = divmod(dst, 6)

        if ((r_s == r_d and (i_d == (i_s + 1) % 6 or i_d == (i_s - 1) % 6)) or
            (i_s == i_d and abs(r_d - r_s) == 1)):
            board[dst] = turn
            board[src] = '.'
        else:
            if r_s == r_d:
                if i_d == (i_s + 2) % 6:
                    jumped = r_s * 6 + (i_s + 1) % 6
                else:
                    jumped = r_s * 6 + (i_s - 1) % 6
            else:
                if r_d == r_s + 2:
                    jumped = (r_s + 1) * 6 + i_s
                else:
                    jumped = (r_s - 1) * 6 + i_s
            board[jumped] = '.'
            board[src] = '.'
            board[dst] = turn
            n_captures += 1

    new_turn = 'B' if turn == 'A' else 'A'
    new_halfmove = 0 if n_captures > 0 else state.halfmove_clock + 1
    return StateMin(board, new_turn, new_halfmove)

# --- Evaluation ----------------------------------------------------------------
POSITION_BONUS = [30, 20, 10, 0]   # ring 0 is best, ring 3 the worst

def evaluate(state: StateMin):
    """Heuristic value from the point of view of the player whose turn it is."""
    board = state.board
    turn = state.turn
    enemy = 'A' if turn == 'B' else 'B'
    score = 0
    for idx, p in enumerate(board):
        r = idx // 6
        if p == turn:
            score += 100 + POSITION_BONUS[r]
        elif p == enemy:
            score -= 100 + POSITION_BONUS[r]
    return score

def evaluate_quick(state: StateMin):
    """Material‑only evaluation, used for move ordering."""
    board = state.board
    turn = state.turn
    enemy = 'A' if turn == 'B' else 'B'
    score = 0
    for p in board:
        if p == turn: score += 100
        elif p == enemy: score -= 100
    return score

# --- Alpha‑beta search with draw detection and transposition table ---------------
def alphabeta(state, depth, alpha, beta, deadline, stop_flag, path_hashes, tt):
    if stop_flag[0]:
        return 0, None
    if time.monotonic() > deadline:
        stop_flag[0] = True
        return 0, None

    # draw by 40‑ply rule
    if state.halfmove_clock >= 40:
        return 0, None

    h = zobrist_hash(state.board, state.turn)
    # draw by repetition (2‑fold in search to avoid cycles)
    if h in path_hashes:
        return 0, None

    # transposition table lookup
    entry = tt.get(h)
    if entry and entry[0] >= depth:
        d, score, flag, best = entry
        if flag == 0:
            return score, best
        elif flag == 1:      # lower bound
            alpha = max(alpha, score)
        else:                # upper bound
            beta = min(beta, score)
        if alpha >= beta:
            return score, best

    moves = legal_moves(state)
    if not moves:
        # no legal move → current player loses
        return -10000, None

    if depth == 0:
        return evaluate(state), None

    # move ordering by quick evaluation
    moves_scored = []
    for mv in moves:
        child = apply_move_minimal(state, mv)
        moves_scored.append((evaluate_quick(child), mv))
    moves_scored.sort(reverse=True, key=lambda x: x[0])

    best_val = -float('inf')
    best_move = None
    path_hashes.add(h)
    alpha_orig = alpha

    for _, mv in moves_scored:
        child = apply_move_minimal(state, mv)
        val, _ = alphabeta(child, depth - 1, -beta, -alpha, deadline, stop_flag, path_hashes, tt)
        val = -val
        if val > best_val:
            best_val = val
            best_move = mv
        alpha = max(alpha, val)
        if alpha >= beta:
            break
        if stop_flag[0]:
            break

    path_hashes.remove(h)

    # store in transposition table
    flag = 0
    if best_val <= alpha_orig:
        flag = 2      # upper bound
    elif best_val >= beta:
        flag = 1      # lower bound
    tt[h] = (depth, best_val, flag, best_move)

    return best_val, best_move

# --- Time‑managed move selection ------------------------------------------------
def choose_move(game_state, game_time_left):
    state_min = StateMin(game_state.board, game_state.turn, game_state.halfmove_clock)
    turn_start = time.monotonic()

    if game_time_left > 5.0:
        budget = min(3.0, game_time_left * 0.3)
    else:
        budget = max(0.1, game_time_left - 1.0)

    deadline = turn_start + budget
    stop_flag = [False]
    best_move = None
    depth = 1
    tt = {}

    while depth <= 60:
        val, move = alphabeta(state_min, depth, -float('inf'), float('inf'),
                              deadline, stop_flag, set(), tt)
        if stop_flag[0]:
            break
        if move is not None:
            best_move = move
        depth += 1

    if best_move is None:
        # fallback to first legal move (should never happen during normal play)
        moves = legal_moves(state_min)
        best_move = moves[0] if moves else None
    return best_move

# --- Wire protocol helpers ------------------------------------------------------
def parse_move_line(line):
    """Convert a 'MOVE r,i -> r,i ...' string into a list of cell indices."""
    if not line.startswith('MOVE '):
        return None
    coords = []
    for token in line[5:].split():
        if token == '->':
            continue
        r, i = map(int, token.split(','))
        coords.append(coord_to_idx(r, i))
    return coords

def move_to_str(move):
    parts = []
    for idx in move:
        r, i = idx_to_coord(idx)
        parts.append(f"{r},{i}")
    return "MOVE " + " -> ".join(parts)

# --- Main event loop -----------------------------------------------------------
def main():
    botname = os.environ['BOTNAME'].strip()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 7474))
    sock.sendall((botname + '\n').encode())
    f = sock.makefile('r', buffering=1)

    current_game_state = None
    game_time_left = 30.0
    turn_start_time = None
    my_color = None
    disqualified = False

    for line in f:
        line = line.rstrip('\n')
        if not line:
            continue

        if line.startswith('MATCH '):
            # MATCH <m> <opponent_name>
            pass

        elif line.startswith('GAME '):
            parts = line.split()
            my_color = parts[2]
            game_time_left = 30.0
            turn_start_time = None
            current_game_state = None
            disqualified = False

        elif line.startswith('BOARD '):
            tokens = line.split()[1:]
            board = tokens[:CELL_COUNT]     # exactly 24 tokens
            # initial turn is always A
            pos_counts = collections.Counter()
            h = zobrist_hash(board, 'A')
            pos_counts[h] = 1
            current_game_state = GameState(board, 'A', 0, pos_counts)

        elif line.startswith('TURN'):
            if disqualified:
                continue    # game is already over for us
            turn_start_time = time.monotonic()
            move = choose_move(current_game_state, game_time_left)

            # send move
            move_str = move_to_str(move)
            sock.sendall((move_str + '\n').encode())

            # optimistically update own state
            new_state, _ = apply_move_to_game(current_game_state, move)
            current_game_state = new_state

            # deduct used time
            elapsed = time.monotonic() - turn_start_time
            game_time_left -= elapsed
            turn_start_time = None

        elif line.startswith('OPP '):
            move_part = line[4:]    # "MOVE ..."
            move = parse_move_line(move_part)
            if move is not None and current_game_state is not None:
                new_state, _ = apply_move_to_game(current_game_state, move)
                current_game_state = new_state

        elif line.startswith('OK '):
            # already applied optimistically
            pass

        elif line.startswith('DQ '):
            disqualified = True

        elif line.startswith('GAME_END'):
            current_game_state = None
            turn_start_time = None
            disqualified = False

        elif line.startswith('MATCH_END'):
            pass

        elif line == 'TOURNAMENT_END':
            break

    sock.close()

if __name__ == '__main__':
    main()