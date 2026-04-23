import sys
import socket
import json
import time
import math

# Pre-compute weights for fast evaluation (supports up to 15 disks)
WEIGHTS = [1000 ** d for d in range(15)]

def get_tops(pos_tuple, n):
    """
    Returns an array of length n where tops[t] is the smallest disk 
    on tower t, or 1000 if the tower is empty.
    """
    tops = [1000] * n
    for d, t in enumerate(pos_tuple):
        if d < tops[t]:
            tops[t] = d
    return tops

def apply_move(pos_tuple, d, t_dst):
    new_pos = list(pos_tuple)
    new_pos[d] = t_dst
    return tuple(new_pos)

def evaluate_state(pos_tuple, n, m):
    """
    Domain-specific evaluation heuristic for Towers of Hanoi.
    Incentivizes moving the largest out-of-place disk to the goal (n-1),
    and heavily penalizes smaller blocking disks on the source/destination.
    """
    score = 0.0
    in_place = True
    target_src = -1

    for d in range(m - 1, -1, -1):
        p = pos_tuple[d]
        w = WEIGHTS[d]
        if in_place:
            if p == n - 1:
                # Disk is locked in correctly at the target tower
                score += 100000 * w
            else:
                in_place = False
                target_src = p
                # Strongly pull the largest out-of-place disk towards n-1
                score += p * 100 * w
        else:
            # For disks smaller than the current target disk
            if p == target_src or p == n - 1:
                # Penalize blockers on the source and destination towers
                score -= 50 * w
            else:
                # Encourage smaller disks to move further right if possible
                score += p * w
                
    return score

class TimeoutException(Exception):
    pass

def minimax(pos_tuple, n, m, depth, alpha, beta, is_hero, end_time, path, last_d=None, last_dst=None):
    if time.time() > end_time:
        raise TimeoutException()

    # Win condition or max depth reached
    if depth == 0 or all(p == n - 1 for p in pos_tuple):
        # Bonus for winning faster (larger depth remaining = better)
        return evaluate_state(pos_tuple, n, m) + (depth * 100), None

    if is_hero:
        max_eval = -math.inf
        best_move = None
        tops = get_tops(pos_tuple, n)

        # Generate Hero valid moves
        moves = []
        for t_src in range(n):
            d = tops[t_src]
            if d == 1000: continue
            for t_dst in range(n):
                if t_src != t_dst and d < tops[t_dst]:
                    moves.append((d, t_src, t_dst))

        # Move ordering: evaluate right-most destinations first to improve alpha-beta pruning
        moves.sort(key=lambda x: x[2], reverse=True)

        for move in moves:
            d, t_src, t_dst = move
            new_pos = apply_move(pos_tuple, d, t_dst)
            
            if new_pos in path:
                eval_score = -math.inf # Heavily penalize cycle-inducing moves
            else:
                new_path = path | {new_pos}
                eval_score, _ = minimax(new_pos, n, m, depth - 1, alpha, beta, False, end_time, new_path, d, t_dst)

            if eval_score > max_eval:
                max_eval = eval_score
                best_move = move

            alpha = max(alpha, eval_score)
            if beta <= alpha:
                break

        return max_eval, best_move

    else:
        min_eval = math.inf
        best_move = None
        tops = get_tops(pos_tuple, n)

        # Generate Villain valid moves (tightly constrained to `last_d` to adjacent towers)
        v_moves = []
        for t_nxt in (last_dst - 1, last_dst + 1):
            if 0 <= t_nxt < n:
                if last_d < tops[t_nxt]:
                    v_moves.append(t_nxt)

        if not v_moves:
            # Must pass
            eval_score, _ = minimax(pos_tuple, n, m, depth - 1, alpha, beta, True, end_time, path)
            return eval_score, "PASS"

        for t_nxt in v_moves:
            new_pos = apply_move(pos_tuple, last_d, t_nxt)
            
            if new_pos in path:
                eval_score = -math.inf # Hero repeats, very good for Villain
            else:
                new_path = path | {new_pos}
                eval_score, _ = minimax(new_pos, n, m, depth - 1, alpha, beta, True, end_time, new_path)

            if eval_score < min_eval:
                min_eval = eval_score
                best_move = t_nxt

            beta = min(beta, eval_score)
            if beta <= alpha:
                break

        return min_eval, best_move


class TowersOfAnnoyBot:
    def __init__(self, host, port, name):
        self.host = host
        self.port = port
        self.name = name
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.games = {1: {}, 2: {}}
        self.n = 0
        self.m = 0

    def connect(self):
        try:
            self.sock.connect((self.host, self.port))
            self.sock.sendall(f"{self.name}_bot\n".encode())
            self.rfile = self.sock.makefile('r')
            print(f"Connected to {self.host}:{self.port} as {self.name}_bot")
        except ConnectionRefusedError:
            print(f"Failed to connect to {self.host}:{self.port}")
            sys.exit(1)

    def run(self):
        while True:
            line = self.rfile.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue

            parts = line.split()
            cmd = parts[0]

            if cmd == "BOARD":
                self.n = int(parts[1])
                self.m = int(parts[2])
            elif cmd == "GAME1":
                self.games[1]['role'] = parts[1]
            elif cmd == "GAME2":
                self.games[2]['role'] = parts[1]
            elif cmd == "YOURTURN":
                game_id = int(parts[1])
                state_line = self.rfile.readline().strip()
                last_line = self.rfile.readline().strip()

                state_str = state_line[6:] # Strip "STATE "
                board_state = json.loads(state_str)

                last_parts = last_line.split()
                if last_parts[1] == "NONE":
                    last_move = None
                else:
                    last_move = (int(last_parts[1]), int(last_parts[2]))

                self.handle_turn(game_id, board_state, last_move)
                
    def handle_turn(self, game_id, board_state, last_move):
        pos = [0] * self.m
        for t_idx, tower in enumerate(board_state):
            for disk in tower:
                pos[disk - 1] = t_idx
        pos_tuple = tuple(pos)
        role = self.games[game_id]['role']

        if role == 'HERO':
            move = self.get_best_hero_move(pos_tuple, self.n, self.m, 1.8)
            self.sock.sendall(f"{move[1]} {move[2]}\n".encode())
        else:
            move = self.get_best_villain_move(pos_tuple, self.n, self.m, last_move, 1.8)
            if move == "PASS":
                self.sock.sendall(b"PASS\n")
            else:
                self.sock.sendall(f"{last_move[1]} {move}\n".encode())

    def get_best_hero_move(self, pos_tuple, n, m, timeout):
        end_time = time.time() + timeout
        best_move = None
        depth = 1
        
        while time.time() < end_time:
            try:
                _, move = minimax(pos_tuple, n, m, depth, -math.inf, math.inf, True, end_time, {pos_tuple})
                if move is not None:
                    best_move = move
                depth += 1
            except TimeoutException:
                break

        if best_move is None:
            # Emergency fallback (highly unlikely due to depth 1 speed)
            tops = get_tops(pos_tuple, n)
            for t_src in range(n):
                d = tops[t_src]
                if d == 1000: continue
                for t_dst in range(n):
                    if t_src != t_dst and d < tops[t_dst]:
                        return (d, t_src, t_dst)
        return best_move

    def get_best_villain_move(self, pos_tuple, n, m, last_move, timeout):
        end_time = time.time() + timeout
        last_dst = last_move[1]
        tops = get_tops(pos_tuple, n)
        last_d = tops[last_dst]

        best_move = None
        depth = 1
        
        while time.time() < end_time:
            try:
                _, move = minimax(pos_tuple, n, m, depth, -math.inf, math.inf, False, end_time, {pos_tuple}, last_d, last_dst)
                if move is not None:
                    best_move = move
                depth += 1
            except TimeoutException:
                break

        if best_move is None:
            # Emergency Fallback
            for t_nxt in (last_dst - 1, last_dst + 1):
                if 0 <= t_nxt < n and last_d < tops[t_nxt]:
                    return t_nxt
            return "PASS"
        return best_move


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Towers of Annoy Bot')
    parser.add_argument('--name', type=str, default='gemini', help='Base name of the bot')
    parser.add_argument('--host', type=str, default='localhost', help='Server IP')
    parser.add_argument('--port', type=int, default=7474, help='Server Port')
    
    args = parser.parse_args()

    bot = TowersOfAnnoyBot(args.host, args.port, args.name)
    bot.connect()
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\nBot shutting down.")