"""
Towers of Annoy Tournament Server.

Round-robin tournament with penalty-shootout matchups. Hero vs Villain
adversarial Hanoi on a line of towers. Each matchup = up to 5 rounds (+ sudden
death), each round = 2 simultaneous games with hero/villain roles swapped.
"""
import socket
import threading
import time
import random
import os
import json
import itertools

HOST = 'localhost'
PORT = 7474
REGISTRATION_WINDOW = 10.0
MOVE_TIMEOUT = 2.0
MAX_REGULAR_ROUNDS = 5
MAX_SUDDEN_DEATH = 5   # up to 10 total
LOG_PATH = 'results.log'
WIN_TOURNAMENT_PTS = 3
DRAW_TOURNAMENT_PTS = 1

# (towers, disks) per round. Rounds beyond the list length reuse the last entry.
ROUND_CONFIGS = [
    (4, 3),    # round 1: budget 9
    (5, 4),    # round 2: budget 17
    (7, 5),    # round 3: budget 33
    (9, 6),    # round 4: budget 65
    (12, 7),   # round 5: budget 129
]


def config_for_round(round_num):
    idx = min(round_num - 1, len(ROUND_CONFIGS) - 1)
    return ROUND_CONFIGS[idx]


def rotate_log():
    if not os.path.exists(LOG_PATH):
        return
    n = 1
    while os.path.exists(f"{LOG_PATH}.{n}"):
        n += 1
    for i in range(n - 1, 0, -1):
        os.rename(f"{LOG_PATH}.{i}", f"{LOG_PATH}.{i + 1}")
    os.rename(LOG_PATH, f"{LOG_PATH}.1")


# =============================================================================
# Game logic
# =============================================================================

class Game:
    def __init__(self, n, m, hero, villain):
        self.n = n
        self.m = m
        self.hero = hero
        self.villain = villain
        self.towers = [[] for _ in range(n)]
        self.towers[0] = list(range(m, 0, -1))  # bottom=m, top=1
        self.turn = 'HERO'
        self.winner = None
        self.hero_moves_made = 0
        self.budget = 2 ** m + 1
        # last_move: ('HERO', from, to) | ('VILLAIN', from, to) | ('VILLAIN', 'PASS') | None
        self.last_move = None
        # last_concrete_move: last move that actually moved a disk (for LAST reporting)
        self.last_concrete_move = None
        self.move_history = []

    def is_goal_state(self):
        target = list(range(self.m, 0, -1))
        return self.towers[self.n - 1] == target

    def is_over(self):
        return self.winner is not None

    def current_player(self):
        return self.hero if self.turn == 'HERO' else self.villain

    def _can_place(self, disk, to_t):
        if not self.towers[to_t]:
            return True
        return self.towers[to_t][-1] > disk

    def _apply(self, from_t, to_t):
        disk = self.towers[from_t].pop()
        self.towers[to_t].append(disk)

    def legal_villain_dests(self):
        """Destinations legal for the villain given last hero move."""
        if not self.last_move or self.last_move[0] != 'HERO':
            return []
        src = self.last_move[2]
        if not self.towers[src]:
            return []
        disk = self.towers[src][-1]
        return [t for t in (src - 1, src + 1)
                if 0 <= t < self.n and self._can_place(disk, t)]

    def hero_move(self, from_t, to_t):
        if not (0 <= from_t < self.n and 0 <= to_t < self.n):
            return False, "out of bounds"
        if from_t == to_t:
            return False, "same source and destination"
        if not self.towers[from_t]:
            return False, f"tower {from_t} is empty"
        disk = self.towers[from_t][-1]
        if not self._can_place(disk, to_t):
            return False, f"cannot place disk {disk} on tower {to_t}"
        self._apply(from_t, to_t)
        self.hero_moves_made += 1
        self.last_move = ('HERO', from_t, to_t)
        self.last_concrete_move = ('HERO', from_t, to_t)
        self.move_history.append(('HERO', from_t, to_t))
        if self.is_goal_state():
            self.winner = 'HERO'
            return True, "ok"
        self.turn = 'VILLAIN'
        return True, "ok"

    def villain_move(self, from_t, to_t):
        if not self.last_move or self.last_move[0] != 'HERO':
            return False, "no hero move to respond to"
        required_from = self.last_move[2]
        if from_t != required_from:
            return False, f"villain must source from tower {required_from}"
        if abs(to_t - from_t) != 1:
            return False, "must move to adjacent tower"
        if not (0 <= to_t < self.n):
            return False, "destination out of bounds"
        if not self.towers[from_t]:
            return False, "source tower empty"
        disk = self.towers[from_t][-1]
        if not self._can_place(disk, to_t):
            return False, f"cannot place disk {disk} on tower {to_t}"
        self._apply(from_t, to_t)
        self.last_move = ('VILLAIN', from_t, to_t)
        self.last_concrete_move = ('VILLAIN', from_t, to_t)
        self.move_history.append(('VILLAIN', from_t, to_t))
        if self.is_goal_state():
            self.winner = 'HERO'
            return True, "ok"
        if self.hero_moves_made >= self.budget:
            self.winner = 'VILLAIN'
            return True, "ok"
        self.turn = 'HERO'
        return True, "ok"

    def villain_pass(self):
        if self.legal_villain_dests():
            return False, "PASS illegal: legal villain moves exist"
        self.last_move = ('VILLAIN', 'PASS')
        # last_concrete_move unchanged — pass moved nothing
        self.move_history.append(('VILLAIN', 'PASS'))
        if self.is_goal_state():
            self.winner = 'HERO'
            return True, "ok"
        if self.hero_moves_made >= self.budget:
            self.winner = 'VILLAIN'
            return True, "ok"
        self.turn = 'HERO'
        return True, "ok"

    def forfeit(self, role):
        self.winner = 'VILLAIN' if role == 'HERO' else 'HERO'


# =============================================================================
# Client handling
# =============================================================================

class Client:
    def __init__(self, sock, name):
        self.sock = sock
        self.name = name
        self.tournament_pts = 0
        self.f = sock.makefile('r', encoding='utf-8')

    def send(self, data):
        try:
            self.sock.sendall(data.encode('utf-8'))
        except OSError:
            pass

    def readline(self, timeout=None):
        if timeout:
            self.sock.settimeout(timeout)
        try:
            line = self.f.readline()
            if not line:
                return None
            return line.strip()
        except (OSError, socket.timeout):
            return None
        finally:
            if timeout:
                self.sock.settimeout(None)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# =============================================================================
# Protocol formatting
# =============================================================================

def format_state(game):
    return json.dumps(game.towers)


def format_last(game):
    lm = game.last_concrete_move
    if lm is None:
        return "NONE"
    return f"{lm[1]} {lm[2]}"


def send_turn_prompt(client, game, game_num):
    payload = (
        f"YOURTURN {game_num}\n"
        f"STATE {format_state(game)}\n"
        f"LAST {format_last(game)}\n"
    )
    client.send(payload)


def format_opponent_msg(game_num, move):
    """move is ('HERO', from, to) | ('VILLAIN', from, to) | ('VILLAIN', 'PASS')."""
    role = move[0]
    if len(move) == 2 or move[1] == 'PASS':
        return f"OPPONENT {game_num} {role} PASS\n"
    return f"OPPONENT {game_num} {role} {move[1]} {move[2]}\n"


# =============================================================================
# Matchup logic
# =============================================================================

def apply_response(game, client, resp, game_num, log):
    """Apply a bot's response to a game. Returns True if advanced, None on forfeit."""
    role = game.turn
    if resp is None:
        log.write(f"      {client.name} ({role}) timed out in G{game_num}\n")
        game.forfeit(role)
        return None
    resp = resp.strip()

    if resp.upper() == 'PASS':
        if role == 'HERO':
            log.write(f"      {client.name} (HERO) illegally PASSed in G{game_num}\n")
            game.forfeit(role)
            return None
        ok, msg = game.villain_pass()
        if not ok:
            log.write(f"      {client.name} (VILLAIN) illegal PASS in G{game_num}: {msg}\n")
            game.forfeit(role)
            return None
        log.write(f"      {client.name} (VILLAIN) PASS in G{game_num}\n")
        return True

    parts = resp.split()
    try:
        from_t = int(parts[0])
        to_t = int(parts[1])
    except (ValueError, IndexError):
        log.write(f"      {client.name} ({role}) malformed '{resp}' in G{game_num}\n")
        game.forfeit(role)
        return None

    if role == 'HERO':
        ok, msg = game.hero_move(from_t, to_t)
    else:
        ok, msg = game.villain_move(from_t, to_t)
    if not ok:
        log.write(f"      {client.name} ({role}) illegal {from_t}->{to_t} in G{game_num}: {msg}\n")
        game.forfeit(role)
        return None

    log.write(f"      {client.name} ({role}) {from_t}->{to_t} in G{game_num}\n")
    return True


def send_game_results(game, game_num):
    if not game.is_over():
        return
    attr = f'_result_sent_{game_num}'
    if getattr(game, attr, False):
        return
    setattr(game, attr, True)

    if game.winner == 'HERO':
        game.hero.send(f"RESULT GAME{game_num} WIN\n")
        game.villain.send(f"RESULT GAME{game_num} LOSS\n")
    else:  # VILLAIN won
        game.villain.send(f"RESULT GAME{game_num} WIN\n")
        game.hero.send(f"RESULT GAME{game_num} LOSS\n")


def play_round(game1, game2, log):
    """Play two games in parallel while both are active, sequential otherwise."""
    while not (game1.is_over() and game2.is_over()):
        g1_active = not game1.is_over()
        g2_active = not game2.is_over()

        if g1_active and g2_active:
            p1 = game1.current_player()
            p2 = game2.current_player()

            if p1 is p2:
                # Same bot expected to act in both games (rare out-of-sync case).
                _take_turn(game1, 1, log)
                if not game2.is_over():
                    _take_turn(game2, 2, log)
            else:
                _take_parallel_turns(game1, 1, game2, 2, log)
        else:
            game = game1 if g1_active else game2
            game_num = 1 if g1_active else 2
            _take_turn(game, game_num, log)

        send_game_results(game1, 1)
        send_game_results(game2, 2)


def _take_turn(game, game_num, log):
    player = game.current_player()
    send_turn_prompt(player, game, game_num)
    resp = player.readline(timeout=MOVE_TIMEOUT)
    result = apply_response(game, player, resp, game_num, log)
    if result is not None and not game.is_over():
        other = game.current_player()  # turn already switched
        other.send(format_opponent_msg(game_num, game.last_move))


def _take_parallel_turns(game1, num1, game2, num2, log):
    p1 = game1.current_player()
    p2 = game2.current_player()

    send_turn_prompt(p1, game1, num1)
    send_turn_prompt(p2, game2, num2)

    responses = {}
    lock = threading.Lock()

    def grab(client, key):
        r = client.readline(timeout=MOVE_TIMEOUT)
        with lock:
            responses[key] = r

    t1 = threading.Thread(target=grab, args=(p1, 1), daemon=True)
    t2 = threading.Thread(target=grab, args=(p2, 2), daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=MOVE_TIMEOUT + 1)
    t2.join(timeout=MOVE_TIMEOUT + 1)

    r1 = apply_response(game1, p1, responses.get(1), num1, log)
    r2 = apply_response(game2, p2, responses.get(2), num2, log)

    if r1 is not None and not game1.is_over():
        game1.current_player().send(format_opponent_msg(num1, game1.last_move))
    if r2 is not None and not game2.is_over():
        game2.current_player().send(format_opponent_msg(num2, game2.last_move))


def run_matchup(client_a, client_b, log):
    score_a = 0
    score_b = 0
    max_rounds = MAX_REGULAR_ROUNDS + MAX_SUDDEN_DEATH
    round_num = 0

    while round_num < max_rounds:
        round_num += 1

        if round_num > 1:
            regular_left = max(0, MAX_REGULAR_ROUNDS - round_num + 1)
            max_catchup = regular_left * 2
            if abs(score_a - score_b) > max_catchup and round_num <= MAX_REGULAR_ROUNDS:
                break
            if round_num > MAX_REGULAR_ROUNDS and score_a != score_b:
                break

        n, m = config_for_round(round_num)
        budget = 2 ** m + 1

        log.write(f"  Round {round_num}: {n} towers, {m} disks, hero budget {budget}\n")

        for c in (client_a, client_b):
            c.send(f"ROUND {round_num}\n")
            c.send(f"BOARD {n} {m}\n")
        client_a.send("GAME1 HERO\nGAME2 VILLAIN\n")
        client_b.send("GAME1 VILLAIN\nGAME2 HERO\n")

        game1 = Game(n, m, hero=client_a, villain=client_b)
        game2 = Game(n, m, hero=client_b, villain=client_a)

        play_round(game1, game2, log)

        round_a = 0
        round_b = 0
        if game1.winner == 'HERO':
            round_a += 1
        else:
            round_b += 1
        if game2.winner == 'HERO':
            round_b += 1
        else:
            round_a += 1

        score_a += round_a
        score_b += round_b

        for gnum, game, hero_name, villain_name in (
            (1, game1, client_a.name, client_b.name),
            (2, game2, client_b.name, client_a.name),
        ):
            log.write(f"    Game {gnum} (HERO={hero_name}, VILLAIN={villain_name}): "
                      f"{game.winner} wins after {game.hero_moves_made}/{game.budget} hero moves\n")
            for entry in game.move_history:
                if len(entry) == 2:
                    log.write(f"      {entry[0]} PASS\n")
                else:
                    log.write(f"      {entry[0]} {entry[1]}->{entry[2]}\n")
            log.write(f"      final: {game.towers}\n")

        log.write(f"  Round {round_num} result: {client_a.name} +{round_a}, "
                  f"{client_b.name} +{round_b}  (match {score_a}-{score_b})\n")
        client_a.send(f"ROUND_SCORE {round_a} {round_b}\n")
        client_b.send(f"ROUND_SCORE {round_b} {round_a}\n")

    if score_a > score_b:
        result = f"{client_a.name} wins"
        client_a.send(f"MATCHUP WIN {score_a} {score_b}\n")
        client_b.send(f"MATCHUP LOSS {score_b} {score_a}\n")
        client_a.tournament_pts += WIN_TOURNAMENT_PTS
    elif score_b > score_a:
        result = f"{client_b.name} wins"
        client_b.send(f"MATCHUP WIN {score_b} {score_a}\n")
        client_a.send(f"MATCHUP LOSS {score_a} {score_b}\n")
        client_b.tournament_pts += WIN_TOURNAMENT_PTS
    else:
        result = "draw"
        client_a.send(f"MATCHUP DRAW {score_a} {score_b}\n")
        client_b.send(f"MATCHUP DRAW {score_b} {score_a}\n")
        client_a.tournament_pts += DRAW_TOURNAMENT_PTS
        client_b.tournament_pts += DRAW_TOURNAMENT_PTS

    log.write(f"  Matchup result: {result} ({score_a}-{score_b})\n\n")
    return result, score_a, score_b


# =============================================================================
# Tournament
# =============================================================================

def run_tournament():
    rotate_log()
    log = open(LOG_PATH, 'w', encoding='utf-8')

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(16)
    server_sock.settimeout(1.0)

    clients = []

    print(f"[*] Server live on {HOST}:{PORT}. Registration: {REGISTRATION_WINDOW}s")
    start_reg = time.time()
    while time.time() - start_reg < REGISTRATION_WINDOW:
        try:
            conn, addr = server_sock.accept()
            conn.settimeout(None)
            name_line = conn.makefile('r').readline().strip()
            if name_line:
                client = Client(conn, name_line)
                clients.append(client)
                print(f"[*] Bot '{name_line}' joined.")
        except socket.timeout:
            continue

    if len(clients) < 2:
        print("[!] Need at least 2 participants.")
        log.close()
        return

    print(f"[*] {len(clients)} bots registered. Starting round-robin.\n")
    log.write(f"Tournament: {len(clients)} bots\n")
    log.write(f"Bots: {', '.join(c.name for c in clients)}\n\n")

    matchups = list(itertools.combinations(range(len(clients)), 2))
    random.shuffle(matchups)

    for mi, (i, j) in enumerate(matchups):
        a, b = clients[i], clients[j]
        header = f"=== MATCHUP {mi + 1}/{len(matchups)}: {a.name} vs {b.name} ==="
        print(header)
        log.write(header + "\n")

        result, sa, sb = run_matchup(a, b, log)
        log.flush()

        print(f"  Result: {result} ({sa}-{sb})")
        print(f"  Standings: {a.name} {a.tournament_pts}, {b.name} {b.tournament_pts}")

    header = "\n" + "=" * 60 + "\nFINAL TOURNAMENT RESULTS\n" + "=" * 60
    print(header)
    log.write(header + "\n")

    for i, c in enumerate(sorted(clients, key=lambda c: -c.tournament_pts)):
        line = f"  #{i + 1}  {c.name:<24} {c.tournament_pts:>4} tournament points"
        print(line)
        log.write(line + "\n")

    log.close()
    server_sock.close()
    for c in clients:
        c.close()


if __name__ == "__main__":
    run_tournament()
