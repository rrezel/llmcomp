import socket
import json
import sys

def solve_hanoi(n, m, src, dst):
    """Iterative solution for standard Towers of Hanoi, only moving to adjacent towers."""
    total_disks = m
    steps = []
    # In the standard recursive solution, disk k (1-indexed from smallest)
    # always moves in one direction if total_disks is odd, and the other if even.
    directions = {i: (1 if total_disks % 2 == 1 else -1) for i in range(1, total_disks + 1)}
    
    states = {i: [] for i in range(n)}
    for i in range(total_disks, 0, -1):
        states[src].append(i)
    
    num_moves = 2 ** total_disks - 1
    
    for _ in range(num_moves):
        # 1. Find the smallest disk (1)
        pos1 = -1
        for t in range(n):
            if states[t] and states[t][-1] == 1:
                pos1 = t
                break
        
        d1 = directions[1]
        next_pos1 = (pos1 + d1) % n
        steps.append((pos1, next_pos1))
        states[pos1].pop()
        states[next_pos1].append(1)
        
        # 2. Find the next disk to move (only one other legal move exists)
        pos_other = -1
        for t in range(n):
            if t != next_pos1 and states[t]:
                if pos_other == -1 or states[t][-1] < states[pos_other][-1]:
                    pos_other = t
        
        if pos_other != -1:
            disk_val = states[pos_other][-1]
            # Try moving in its designated direction
            d_other = directions[disk_val]
            next_pos_cand = (pos_other + d_other) % n
            
            if next_pos_cand == next_pos1 or (states[next_pos_cand] and states[next_pos_cand][-1] < disk_val):
                # Target is occupied by disk 1 or a smaller disk, reverse direction
                next_pos_other = (pos_other - d_other) % n
            else:
                next_pos_other = next_pos_cand
                
            steps.append((pos_other, next_pos_other))
            states[pos_other].pop()
            states[next_pos_other].append(disk_val)
            
    return steps

class Bot:
    def __init__(self, name):
        self.name = name
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect(('localhost', 7474))
        self.buf = ''
        self.send(self.name + '\n')
        
        # Matchup state
        self.games = {}   # game_id -> dict of game state
        self.n = 0
        self.m = 0
        self.budget = 0
        
    def send(self, msg):
        self.sock.sendall(msg.encode('utf-8'))
        
    def recv_line(self):
        while '\n' not in self.buf:
            data = self.sock.recv(4096)
            if not data:
                sys.exit(0)
            self.buf += data.decode('utf-8')
        line, self.buf = self.buf.split('\n', 1)
        return line.strip()
        
    def run(self):
        while True:
            line = self.recv_line()
            if not line:
                continue
            
            parts = line.split()
            cmd = parts[0]
            
            if cmd == 'ROUND':
                self.n = int(parts[2])
                self.m = int(parts[3])
                self.budget = 2 ** self.m + 1
                self.games = {}
                
            elif cmd == 'GAME1':
                g1_role = parts[1]
                g2_role = 'VILLAIN' if g1_role == 'HERO' else 'HERO'
                self.games[1] = {'role': g1_role, 'state': None, 'hero_moves': 0}
                self.games[2] = {'role': g2_role, 'state': None, 'hero_moves': 0}
                
            elif cmd == 'YOURTURN':
                game_id = int(parts[1])
                game = self.games[game_id]
                
                # Read STATE
                state_line = self.recv_line()
                state_json = state_line[len('STATE '):]
                game['state'] = json.loads(state_json)
                
                # Read LAST
                last_line = self.recv_line()
                last_parts = last_line.split()
                last_move = None
                if last_parts[1] != 'NONE':
                    last_move = (int(last_parts[1]), int(last_parts[2]))
                    
                if game['role'] == 'HERO':
                    self.play_hero(game_id, game, last_move)
                else:
                    self.play_villain(game_id, game, last_move)
                    
            elif cmd == 'OPPONENT':
                game_id = int(parts[1])
                role = parts[2]
                game = self.games[game_id]
                if len(parts) > 3:  # It was a move, not PASS
                    fr = int(parts[3])
                    to = int(parts[4])
                    self.apply_move(game, fr, to, role)
                    
            elif cmd == 'RESULT':
                pass # Result acknowledged
                
            elif cmd == 'ROUND_SCORE':
                pass # Round score acknowledged
                
            elif cmd == 'MATCHUP':
                pass # Matchup finished, loop will start new matchup or end
                
    def apply_move(self, game, fr, to, role):
        """Applies a move to the game state and checks for hero win."""
        state = game['state']
        disk = state[fr].pop()
        state[to].append(disk)
        
        # Check if hero wins after this move
        if state[-1] == list(range(self.m, 0, -1)):
            game['hero_won'] = True
            
        # Track hero moves
        if role == 'HERO':
            game['hero_moves'] = game.get('hero_moves', 0) + 1
            
    def play_hero(self, game_id, game, last_move):
        # If villain's last move caused a win, don't move (should be caught by server, but just in case)
        if game.get('hero_won'):
            return
            
        # Apply villain's last move if any
        if last_move is not None:
            self.apply_move(game, last_move[0], last_move[1], 'VILLAIN')
            if game.get('hero_won'):
                return
                
        # Check budget
        if game['hero_moves'] >= self.budget:
            return
            
        # If no strategy or hero moves exhausted, pick valid move
        # The theoretical best takes 2^m-1 hero moves, but with 2^m+1 budget we have exactly 1 spare move.
        # A single miss-step means we cannot win. We play perfectly if possible.
        
        valid_moves = self.get_valid_hero_moves(game['state'])
        move = valid_moves[0] if valid_moves else (0, 1)
        self.send(f"{move[0]} {move[1]}\n")
        
    def play_villain(self, game_id, game, last_move):
        # Apply hero's last move
        if last_move is not None:
            self.apply_move(game, last_move[0], last_move[1], 'HERO')
            if game.get('hero_won'):
                return
        
        fr = last_move[1]
        disk = game['state'][fr][-1]
        
        # Check adjacent moves
        for to in [fr - 1, fr + 1]:
            if 0 <= to < self.n:
                if not game['state'][to] or game['state'][to][-1] > disk:
                    self.send(f"{fr} {to}\n")
                    self.apply_move(game, fr, to, 'VILLAIN')
                    return
                    
        # No valid move
        self.send("PASS\n")
        
    def get_valid_hero_moves(self, state):
        moves = []
        tops = {}
        for i in range(self.n):
            if state[i]:
                tops[i] = state[i][-1]
                
        for fr, dsk in tops.items():
            for to in range(self.n):
                if fr != to and (not state[to] or state[to][-1] > dsk):
                    moves.append((fr, to))
        return moves

if __name__ == '__main__':
    bot_name = "glm_annoy_tactic_bot"
    bot = Bot(bot_name)
    bot.run()
