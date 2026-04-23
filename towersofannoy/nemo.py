import socket
import json
import sys
import re

class GameState:
    def __init__(self, num_towers, num_disks):
        self.num_towers = num_towers
        self.num_disks = num_disks
        self.towers = [[] for _ in range(num_towers)]
        # initial state: all disks on tower 0, largest at bottom (largest number)
        for d in range(num_disks, 0, -1):
            self.towers[0].append(d)
        self.last_move = None  # tuple (src, dst) of last move in this game
        self.hero_move_count = 0
        self.game_over = False
        self.winner = None  # 'HERO' or 'VILLAIN'

    def copy(self):
        new = GameState(self.num_towers, self.num_disks)
        new.towers = [list(t) for t in self.towers]
        new.last_move = self.last_move
        new.hero_move_count = self.hero_move_count
        new.game_over = self.game_over
        new.winner = self.winner
        return new

    def is_goal(self):
        target = self.towers[self.num_towers-1]
        if len(target) != self.num_disks:
            return False
        # expect descending order largest to smallest from bottom to top
        expected = list(range(self.num_disks, 0, -1))
        return target == expected

    def legal_hero_moves(self):
        moves = []
        for src in range(self.num_towers):
            if not self.towers[src]:
                continue
            top_disk = self.towers[src][-1]
            for dst in range(self.num_towers):
                if src == dst:
                    continue
                if not self.towers[dst] or self.towers[dst][-1] > top_disk:
                    moves.append((src, dst))
        return moves

    def apply_move(self, src, dst, is_hero_move):
        if src < 0 or src >= self.num_towers or not self.towers[src]:
            return False
        top_disk = self.towers[src][-1]
        if dst < 0 or dst >= self.num_towers:
            return False
        if self.towers[dst] and self.towers[dst][-1] < top_disk:
            return False
        # perform move
        self.towers[src].pop()
        self.towers[dst].append(top_disk)
        self.last_move = (src, dst)
        if is_hero_move:
            self.hero_move_count += 1
        # check win
        if self.is_goal():
            self.game_over = True
            self.winner = 'HERO'
        return True

    def villain_moves_after_hero_move(self, hero_src, hero_dst):
        # villain must move the disk that hero just moved (now at hero_dst)
        src = hero_dst
        if src < 0 or src >= self.num_towers or not self.towers[src]:
            return []
        top_disk = self.towers[src][-1]
        moves = []
        for dst in [src-1, src+1]:
            if 0 <= dst < self.num_towers:
                if not self.towers[dst] or self.towers[dst][-1] > top_disk:
                    moves.append((src, dst))
        return moves

    def apply_villain_move(self, src, dst):
        # src must equal last move's dst (hero's move)
        if self.last_move is None or src != self.last_move[1]:
            return False
        return self.apply_move(src, dst, is_hero_move=False)

    def must_pass(self):
        moves = self.villain_moves_after_hero_move(*self.last_move) if self.last_move else []
        return len(moves) == 0


class Bot:
    def __init__(self, name):
        self.name = name
        self.socket = None
        self.file = None
        self.game1 = None
        self.game2 = None
        self.role_game1 = None  # 'HERO' or 'VILLAIN'
        self.role_game2 = None
        self.move_requested = None  # game_num (1 or 2) when we need to move
        self.match_points = 0
        self.opponent_match_points = 0
        self.current_round = 0

    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect(('localhost', 7474))
        self.file = self.socket.makefile('rw', newline='\n')
        self.file.write(f"{self.name}_bot\n")
        self.file.flush()

    def close(self):
        if self.file:
            self.file.close()
        if self.socket:
            self.socket.close()

    def run(self):
        try:
            while True:
                line = self.file.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                if line.startswith('ROUND'):
                    self._handle_round(line)
                elif line.startswith('BOARD'):
                    self._handle_board(line)
                elif line.startswith('GAME1'):
                    self._handle_game1(line)
                elif line.startswith('GAME2'):
                    self._handle_game2(line)
                elif line.startswith('YOURTURN'):
                    self._handle_yourturn(line)
                elif line.startswith('STATE'):
                    self._handle_state(line)
                elif line.startswith('LAST'):
                    self._handle_last(line)
                elif line.startswith('OPPONENT'):
                    self._handle_opponent(line)
                elif line.startswith('RESULT'):
                    self._handle_result(line)
                elif line.startswith('ROUND_SCORE'):
                    self._handle_round_score(line)
                elif line.startswith('MATCHUP'):
                    self._handle_matchup(line)
                else:
                    # ignore unknown
                    pass
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
        finally:
            self.close()

    def _handle_round(self, line):
        parts = line.split()
        self.current_round = int(parts[1])

    def _handle_board(self, line):
        parts = line.split()
        n = int(parts[1])
        m = int(parts[2])
        self.game1 = GameState(n, m)
        self.game2 = GameState(n, m)

    def _handle_game1(self, line):
        parts = line.split()
        self.role_game1 = parts[1]

    def _handle_game2(self, line):
        parts = line.split()
        self.role_game2 = parts[1]

    def _handle_yourturn(self, line):
        parts = line.split()
        game_num = int(parts[1])
        self.move_requested = game_num

    def _handle_state(self, line):
        # extract JSON array
        match = re.search(r'\[.*\]', line)
        if not match:
            return
        state_json = match.group(0)
        towers = json.loads(state_json)
        if self.move_requested == 1:
            self.game1.towers = towers
        else:
            self.game2.towers = towers

    def _handle_last(self, line):
        parts = line.split()
        if parts[1] == 'NONE':
            last = None
        else:
            last = (int(parts[1]), int(parts[2]))
        if self.move_requested == 1:
            self.game1.last_move = last
        else:
            self.game2.last_move = last

    def _handle_opponent(self, line):
        # OPPONENT {1 or 2} HERO {from} {to}
        # OPPONENT {1 or 2} VILLAIN {from} {to}
        # OPPONENT {1 or 2} VILLAIN PASS
        parts = line.split()
        game_num = int(parts[1])  # which game the opponent played
        role = parts[2]
        if role == 'HERO':
            src = int(parts[3])
            dst = int(parts[4])
            # apply hero move to the other game state (the opponent's game)
            other_game = self.game2 if game_num == 1 else self.game1
            other_game.apply_move(src, dst, is_hero_move=True)
        elif role == 'VILLAIN':
            if parts[3] == 'PASS':
                # villain passed, no state change
                pass
            else:
                src = int(parts[3])
                dst = int(parts[4])
                other_game = self.game2 if game_num == 1 else self.game1
                other_game.apply_move(src, dst, is_hero_move=False)

    def _handle_result(self, line):
        parts = line.split()
        game_num = int(parts[1][5])  # GAME1 or GAME2
        outcome = parts[2]
        if game_num == 1:
            if outcome == 'WIN':
                self.game1.winner = 'HERO' if self.role_game1 == 'HERO' else 'VILLAIN'
                self.game1.game_over = True
            else:
                self.game1.winner = 'VILLAIN' if self.role_game1 == 'HERO' else 'HERO'
                self.game1.game_over = True
        else:
            if outcome == 'WIN':
                self.game2.winner = 'HERO' if self.role_game2 == 'HERO' else 'VILLAIN'
                self.game2.game_over = True
            else:
                self.game2.winner = 'VILLAIN' if self.role_game2 == 'HERO' else 'HERO'
                self.game2.game_over = True

    def _handle_round_score(self, line):
        parts = line.split()
        self.match_points = int(parts[1])
        self.opponent_match_points = int(parts[2])

    def _handle_matchup(self, line):
        parts = line.split()
        outcome = parts[1]
        # we could reset for next matchup, but server will send new ROUND etc.
        # just print for debugging
        # print(f"Matchup {outcome}: {self.match_points}-{self.opponent_match_points}")

    def make_move(self):
        if self.move_requested is None:
            return None
        game_num = self.move_requested
        game = self.game1 if game_num == 1 else self.game2
        role = self.role_game1 if game_num == 1 else self.role_game2
        if role == 'HERO':
            move = self.hero_move(game)
        else:
            move = self.villain_move(game)
        if move is None:
            # no legal move; for hero should not happen; for villain we will output PASS later
            return "PASS"
        src, dst = move
        return f"{src} {dst}"

    def hero_move(self, game):
        # Strategy: try to move the smallest disk (disk 1) towards target tower
        target = game.num_towers - 1
        # locate smallest disk
        smallest_loc = None
        for t_idx, tower in enumerate(game.towers):
            if tower and tower[-1] == 1:
                smallest_loc = t_idx
                break
        if smallest_loc is None:
            # fallback: any legal move
            moves = game.legal_hero_moves()
            return moves[0] if moves else None
        # compute direction towards target
        if smallest_loc < target:
            step = 1
        elif smallest_loc > target:
            step = -1
        else:
            # already at target, try to move it away? Actually we might need to move other disks.
            # fallback to any legal move
            moves = game.legal_hero_moves()
            return moves[0] if moves else None
        dst = smallest_loc + step
        if 0 <= dst < game.num_towers:
            if not game.towers[dst] or game.towers[dst][-1] > 1:
                return (smallest_loc, dst)
        # if that move not legal, try moving smallest disk away from target?
        dst2 = smallest_loc - step
        if 0 <= dst2 < game.num_towers:
            if not game.towers[dst2] or game.towers[dst2][-1] > 1:
                return (smallest_loc, dst2)
        # else any legal move
        moves = game.legal_hero_moves()
        return moves[0] if moves else None

    def villain_move(self, game):
        # villain must move the disk hero just moved
        if game.last_move is None:
            return None
        src = game.last_move[1]  # hero's dst
        if src < 0 or src >= game.num_towers or not game.towers[src]:
            return None
        top_disk = game.towers[src][-1]
        possible = []
        for dst in [src-1, src+1]:
            if 0 <= dst < game.num_towers:
                if not game.towers[dst] or game.towers[dst][-1] > top_disk:
                    possible.append((src, dst))
        if not possible:
            return None  # will lead to PASS
        target = game.num_towers - 1
        # choose move that maximizes distance of disk from target (to hinder)
        def dist(t):
            return abs(t - target)
        best = None
        best_dist = -1
        for s, d in possible:
            ddist = dist(d)
            if ddist > best_dist:
                best_dist = ddist
                best = (s, d)
        return best

if __name__ == '__main__':
    bot_name = "nemo_bot"  # can be any string
    bot = Bot(bot_name)
    try:
        bot.connect()
        bot.run()
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)