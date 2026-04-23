import socket
import json
import sys
from typing import List, Tuple, Optional

def is_goal(state: List[List[int]], n: int, m: int) -> bool:
    if len(state[n-1]) != m:
        return False
    return state[n-1] == list(range(m, 0, -1))

def apply_move(state: List[List[int]], fr: int, to: int) -> None:
    if fr is None or to is None:
        return
    disk = state[fr].pop()
    state[to].append(disk)

def copy_state(state: List[List[int]]) -> List[List[int]]:
    return [lst[:] for lst in state]

def get_legal_moves(state: List[List[int]], n: int) -> List[Tuple[int, int]]:
    moves = []
    for fr in range(n):
        if not state[fr]:
            continue
        disk = state[fr][-1]
        for to in range(n):
            if fr == to:
                continue
            tgt_stack = state[to]
            if not tgt_stack or tgt_stack[-1] > disk:
                moves.append((fr, to))
    return moves

def get_villain_options(state: List[List[int]], hero_to: int, n: int) -> List[int]:
    if not state[hero_to]:
        return []
    disk = state[hero_to][-1]
    options = []
    for d in [-1, 1]:
        tgt = hero_to + d
        if 0 <= tgt < n:
            tgt_stack = state[tgt]
            if not tgt_stack or tgt_stack[-1] > disk:
                options.append(tgt)
    return options

def evaluate(state: List[List[int]], n: int, m: int) -> int:
    goal = n - 1
    # Huge bonus for correct bottom-to-top stack on the goal tower (largest disks locked in place first)
    goal_stack = state[goal]
    correct = 0
    expected = list(range(m, 0, -1))
    for i in range(min(len(goal_stack), m)):
        if goal_stack[i] == expected[i]:
            correct += 1
        else:
            break
    score = correct * 10000
    
    # Position bonus: larger disks further toward the goal are much better
    for t, stack in enumerate(state):
        for d in stack:
            score += t * d * 10
    return score

def get_hero_move(state: List[List[int]], n: int, m: int) -> str:
    legal_moves = get_legal_moves(state, n)
    if not legal_moves:
        return "0 0"  # fallback (should never happen)
    
    best_score = -float('inf')
    best_move = legal_moves[0]
    
    for fr, to in legal_moves:
        temp_state = copy_state(state)
        apply_move(temp_state, fr, to)
        
        # Immediate win?
        if is_goal(temp_state, n, m):
            return f"{fr} {to}"
        
        # Villain's possible responses after this move
        villain_opts = get_villain_options(temp_state, to, n)
        if not villain_opts:
            # PASS -> state unchanged
            final_states = [temp_state]
        else:
            final_states = []
            for v_to in villain_opts:
                f_state = copy_state(temp_state)
                apply_move(f_state, to, v_to)
                final_states.append(f_state)
        
        # Villain will pick the worst (minimum) score for us
        min_score = float('inf')
        for f_state in final_states:
            sc = evaluate(f_state, n, m)
            if sc < min_score:
                min_score = sc
        
        if min_score > best_score:
            best_score = min_score
            best_move = (fr, to)
    
    return f"{best_move[0]} {best_move[1]}"

def get_villain_move(state: List[List[int]], n: int, m: int, last_move: Optional[Tuple[int, int]]) -> str:
    if last_move is None:
        return "PASS"
    hero_from, hero_to = last_move
    villain_opts = get_villain_options(state, hero_to, n)
    if not villain_opts:
        return "PASS"
    
    # Villain picks the move that hurts Hero the most (lowest evaluation)
    best_v_score = float('inf')
    best_tgt = villain_opts[0]
    
    for tgt in villain_opts:
        temp_state = copy_state(state)
        apply_move(temp_state, hero_to, tgt)
        sc = evaluate(temp_state, n, m)
        if sc < best_v_score:
            best_v_score = sc
            best_tgt = tgt
    
    return f"{hero_to} {best_tgt}"

def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(('localhost', 7474))
    # Bot name (change if you want a different identifier in the tournament)
    bot_name = "GrokTowersBot\n"
    s.sendall(bot_name.encode('utf-8'))
    
    f = s.makefile('r')
    
    n = 3
    m = 3
    local_states = {}
    roles = {}
    
    while True:
        try:
            line = f.readline().strip()
            if not line:
                continue
            
            parts = line.split()
            cmd = parts[0]
            
            if cmd == 'ROUND':
                print(f"[ROUND] {line}", file=sys.stderr)
                local_states.clear()
                roles.clear()
            elif cmd == 'BOARD':
                n = int(parts[1])
                m = int(parts[2])
                print(f"[BOARD] {n} towers, {m} disks", file=sys.stderr)
            elif cmd.startswith('GAME'):
                # GAME1 / GAME2 line
                game = cmd
                role = parts[1]
                roles[game] = role
                # Initial board state (all disks on tower 0)
                initial = [list(range(m, 0, -1))] + [[] for _ in range(n - 1)]
                local_states[game] = initial
                print(f"[{game}] Role: {role}", file=sys.stderr)
            
            elif cmd == 'YOURTURN':
                game_num = int(parts[1])
                game = f"GAME{game_num}"
                
                # Read STATE line
                state_line = f.readline().strip()
                if state_line.startswith('STATE '):
                    state_json = state_line[6:]
                    current_state = json.loads(state_json)
                    local_states[game] = current_state
                
                # Read LAST line
                last_line = f.readline().strip()
                last_move = None
                if last_line.startswith('LAST '):
                    lparts = last_line.split()
                    if lparts[1] != 'NONE':
                        last_move = (int(lparts[1]), int(lparts[2]))
                
                role = roles.get(game, 'HERO')
                if role == 'HERO':
                    move_str = get_hero_move(local_states[game], n, m)
                else:
                    move_str = get_villain_move(local_states[game], n, m, last_move)
                
                print(f"[{game} {role}] → {move_str}", file=sys.stderr)
                s.sendall((move_str + '\n').encode('utf-8'))
                
                # Immediately apply our own move to local view (server won't resend STATE until next turn)
                if move_str != "PASS":
                    try:
                        fr, to = map(int, move_str.split())
                        apply_move(local_states[game], fr, to)
                    except Exception:
                        pass  # malformed (should not happen)
            
            elif cmd == 'OPPONENT':
                # Update our view of the other simultaneous game
                gnum = int(parts[1])
                game = f"GAME{gnum}"
                player = parts[2]
                if len(parts) > 3 and parts[3] != 'PASS':
                    fr = int(parts[3])
                    to = int(parts[4])
                    if game in local_states:
                        apply_move(local_states[game], fr, to)
                # PASS does nothing to state
            
            elif cmd in ('RESULT', 'ROUND_SCORE', 'MATCHUP'):
                print(f"[{cmd}] {line}", file=sys.stderr)
            
            else:
                print(f"[UNKNOWN] {line}", file=sys.stderr)
        
        except Exception as e:
            print(f"Connection error: {e}", file=sys.stderr)
            break

if __name__ == "__main__":
    main()