#!/usr/bin/env python3
"""
Towers of Annoy - Tournament Bot
A Python 3.10 client for the adversarial Towers of Hanoi variant.
"""
import socket
import sys
import json


class TowersBot:
    def __init__(self, name: str):
        self.name = name
        self.sock = None
        self.buffer = ""

        # Current round/matchup state
        self.num_towers = 0
        self.num_disks = 0
        self.goal_tower = 0
        self.roles = {}          # game_id (1 or 2) -> 'HERO' or 'VILLAIN'
        self.hero_move_count = {}  # game_id -> number of hero moves made

        # Pending turn data (YOURTURN / STATE / LAST come in sequence)
        self.pending_turn = None
        self.pending_state = None

    def connect(self, host: str = 'localhost', port: int = 7474):
        """Connect to the tournament server and register."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))
        self._send(self.name)

    def _send(self, msg: str):
        """Send a line to the server."""
        self.sock.sendall(f"{msg}\n".encode())

    def _debug(self, msg: str):
        """Log to stderr (never goes to the server)."""
        print(msg, file=sys.stderr, flush=True)

    def run(self):
        """Main event loop."""
        while True:
            try:
                data = self.sock.recv(8192).decode()
                if not data:
                    self._debug("Server closed connection.")
                    break
                self.buffer += data

                # Process complete lines
                while '\n' in self.buffer:
                    line, self.buffer = self.buffer.split('\n', 1)
                    self._handle_line(line.strip())
            except Exception as e:
                self._debug(f"Fatal error: {e}")
                break

    def _handle_line(self, line: str):
        if not line:
            return

        parts = line.split()
        cmd = parts[0]

        if cmd == 'ROUND':
            self.hero_move_count = {1: 0, 2: 0}

        elif cmd == 'BOARD':
            self.num_towers = int(parts[1])
            self.num_disks = int(parts[2])
            self.goal_tower = self.num_towers - 1

        elif cmd == 'GAME1':
            self.roles[1] = parts[1]

        elif cmd == 'GAME2':
            self.roles[2] = parts[1]

        elif cmd == 'YOURTURN':
            self.pending_turn = int(parts[1])

        elif cmd == 'STATE':
            # Re-assemble JSON in case split() broke it apart
            self.pending_state = json.loads(' '.join(parts[1:]))

        elif cmd == 'LAST':
            if self.pending_turn is None or self.pending_state is None:
                return

            last_move = None
            if parts[1] != 'NONE':
                last_move = (int(parts[1]), int(parts[2]))

            self._handle_turn(self.pending_turn, self.pending_state, last_move)
            self.pending_turn = None
            self.pending_state = None

        elif cmd == 'OPPONENT':
            # We could track opponent moves for pattern detection,
            # but we rely on the authoritative STATE when it's our turn.
            pass

        elif cmd == 'RESULT':
            pass  # Game over notification

        elif cmd == 'ROUND_SCORE':
            pass

        elif cmd == 'MATCHUP':
            pass

    def _handle_turn(self, game_id: int, state: list, last_move):
        """Decide and send a move for the given game."""
        role = self.roles[game_id]

        if role == 'HERO':
            self.hero_move_count[game_id] = self.hero_move_count.get(game_id, 0) + 1
            move = self._find_hero_move(state)
            if move:
                self._send(f"{move[0]} {move[1]}")
            else:
                # Should never happen in a valid game, but avoid crashing
                self._debug("WARNING: No legal hero move found!")
                self._send("0 0")
        else:
            move = self._find_villain_move(state, last_move)
            self._send(move)

    # -----------------------------------------------------------------
    #  Move validation helpers
    # -----------------------------------------------------------------
    def _is_valid_hero_move(self, state: list, fr: int, to: int) -> bool:
        if fr == to:
            return False
        if fr < 0 or fr >= self.num_towers or to < 0 or to >= self.num_towers:
            return False
        if not state[fr]:
            return False
        disk = state[fr][-1]
        if state[to] and state[to][-1] < disk:
            return False
        return True

    def _is_valid_villain_move(self, state: list, hero_to: int, v_to: int) -> bool:
        if not state[hero_to]:
            return False
        disk = state[hero_to][-1]
        if v_to < 0 or v_to >= self.num_towers:
            return False
        if abs(v_to - hero_to) != 1:
            return False
        if state[v_to] and state[v_to][-1] < disk:
            return False
        return True

    # -----------------------------------------------------------------
    #  State evaluation (higher = better for Hero)
    # -----------------------------------------------------------------
    def _evaluate(self, state: list) -> int:
        """Score a board state from Hero's perspective."""
        # Immediate win
        if len(state[self.goal_tower]) == self.num_disks:
            return 10_000_000

        score = 0

        for disk in range(self.num_disks, 0, -1):
            loc = None
            for t, tower in enumerate(state):
                if disk in tower:
                    loc = t
                    break

            if loc == self.goal_tower:
                # Bonus for correct placement on goal tower
                score += disk * 2_000
            else:
                # Penalty for distance from goal, weighted by disk size
                dist = abs(loc - self.goal_tower)
                score -= dist * disk * 500

                # Extra penalty if this disk is buried under smaller disks
                for tower in state:
                    if disk in tower:
                        idx = tower.index(disk)
                        if idx < len(tower) - 1:
                            score -= disk * 300
                        break

        return score

    # -----------------------------------------------------------------
    #  Hero strategy: 1-ply greedy with villain-response simulation
    # -----------------------------------------------------------------
    def _find_hero_move(self, state: list):
        """
        Greedy best move: simulate our move + villain's best response,
        then pick the move with the best worst-case score.
        """
        # --- Fast path: place the next-needed disk directly on the goal ---
        goal_disks = state[self.goal_tower]
        next_needed = None
        for disk in range(self.num_disks, 0, -1):
            for t, tower in enumerate(state):
                if disk in tower:
                    if t != self.goal_tower:
                        next_needed = disk
                    break
            if next_needed is not None:
                break

        if next_needed is not None:
            for t, tower in enumerate(state):
                if next_needed in tower and tower[-1] == next_needed:
                    if self._is_valid_hero_move(state, t, self.goal_tower):
                        # Verify this disk is the correct next one for the goal stack
                        if not goal_disks or goal_disks[-1] == next_needed + 1:
                            return (t, self.goal_tower)
                    break

        # --- General greedy search ---
        best_move = None
        best_score = -float('inf')

        for fr in range(self.num_towers):
            if not state[fr]:
                continue
            disk = state[fr][-1]

            for to in range(self.num_towers):
                if not self._is_valid_hero_move(state, fr, to):
                    continue

                # Apply hero move
                ns = [list(t) for t in state]
                ns[fr].pop()
                ns[to].append(disk)

                # Check for immediate win
                if len(ns[self.goal_tower]) == self.num_disks:
                    return (fr, to)

                # Determine villain's legal responses
                villain_opts = []
                for v_to in (to - 1, to + 1):
                    if 0 <= v_to < self.num_towers:
                        if not ns[v_to] or ns[v_to][-1] > disk:
                            villain_opts.append(v_to)

                if not villain_opts:
                    # Villain forced to pass — big bonus
                    score = self._evaluate(ns) + 5_000
                else:
                    # Villain picks the worst response for us
                    worst = float('inf')
                    for v_to in villain_opts:
                        vs = [list(t) for t in ns]
                        vs[to].pop()
                        vs[v_to].append(disk)
                        s = self._evaluate(vs)
                        if s < worst:
                            worst = s
                    score = worst

                if score > best_score:
                    best_score = score
                    best_move = (fr, to)

        # Absolute fallback (should be unreachable in a legal game)
        if best_move is None:
            for fr in range(self.num_towers):
                if not state[fr]:
                    continue
                for to in range(self.num_towers):
                    if self._is_valid_hero_move(state, fr, to):
                        return (fr, to)

        return best_move

    # -----------------------------------------------------------------
    #  Villain strategy: minimize Hero's evaluation
    # -----------------------------------------------------------------
    def _find_villain_move(self, state: list, last_move):
        """
        Must move the exact disk the hero just moved to an adjacent tower.
        If no legal move exists, PASS.
        """
        if last_move is None:
            return "PASS"

        hero_from, hero_to = last_move

        if not state[hero_to]:
            return "PASS"

        disk = state[hero_to][-1]

        options = []
        for v_to in (hero_to - 1, hero_to + 1):
            if self._is_valid_villain_move(state, hero_to, v_to):
                options.append(v_to)

        if not options:
            return "PASS"

        # Pick the response that hurts Hero the most
        best_for_villain = None
        best_score = float('inf')

        for v_to in options:
            ns = [list(t) for t in state]
            ns[hero_to].pop()
            ns[v_to].append(disk)
            score = self._evaluate(ns)
            if score < best_score:
                best_score = score
                best_for_villain = v_to

        return f"{hero_to} {best_for_villain}"


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "KimiBot"
    if not name.endswith("_bot"):
        name += "_bot"

    bot = TowersBot(name)
    bot.connect()
    bot.run()


if __name__ == "__main__":
    main()