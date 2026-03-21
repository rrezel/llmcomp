import socket
import sys
from collections import deque

# Global dictionary for O(1) lookups
print("Loading dictionary.txt...", file=sys.stderr)
try:
    with open("dictionary.txt", "r", encoding="utf-8") as f:
        dictionary = {line.strip().upper() for line in f if line.strip() and line.strip().isalpha()}
    print(f"Loaded {len(dictionary):,} words.", file=sys.stderr)
except FileNotFoundError:
    print("Error: dictionary.txt not found in current directory!", file=sys.stderr)
    sys.exit(1)

def get_neighbors(word: str) -> list[str]:
    """Generate all valid neighbors using exactly one insert/delete/substitute."""
    neighbors = []
    n = len(word)
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    
    # Deletions (length n-1)
    for i in range(n):
        candidate = word[:i] + word[i+1:]
        if candidate in dictionary:
            neighbors.append(candidate)
    
    # Substitutions (same length)
    for i in range(n):
        orig = word[i]
        for c in letters:
            if c != orig:
                candidate = word[:i] + c + word[i+1:]
                if candidate in dictionary:
                    neighbors.append(candidate)
    
    # Insertions (length n+1)
    for i in range(n + 1):
        for c in letters:
            candidate = word[:i] + c + word[i:]
            if candidate in dictionary:
                neighbors.append(candidate)
    
    return neighbors

def find_ladder(start: str, goal: str) -> list[str] | None:
    """Bidirectional BFS to find ANY valid ladder (fastest possible in unweighted graph)."""
    if start == goal:
        return [start]
    if start not in dictionary or goal not in dictionary:
        return None

    # Forward search (from start)
    fwd_queue = deque([start])
    fwd_parent = {start: None}
    
    # Backward search (from goal)
    bwd_queue = deque([goal])
    bwd_parent = {goal: None}

    while fwd_queue and bwd_queue:
        # Expand forward side
        curr = fwd_queue.popleft()
        for neigh in get_neighbors(curr):
            if neigh not in fwd_parent:
                fwd_parent[neigh] = curr
                fwd_queue.append(neigh)
                if neigh in bwd_parent:
                    # Reconstruct path
                    path_fwd = []
                    at = neigh
                    while at is not None:
                        path_fwd.append(at)
                        at = fwd_parent[at]
                    path_fwd.reverse()
                    
                    path_bwd = []
                    at = neigh
                    while at is not None:
                        path_bwd.append(at)
                        at = bwd_parent[at]
                    return path_fwd + path_bwd[1:]
        
        # Expand backward side
        curr = bwd_queue.popleft()
        for neigh in get_neighbors(curr):
            if neigh not in bwd_parent:
                bwd_parent[neigh] = curr
                bwd_queue.append(neigh)
                if neigh in fwd_parent:
                    # Reconstruct path
                    path_fwd = []
                    at = neigh
                    while at is not None:
                        path_fwd.append(at)
                        at = fwd_parent[at]
                    path_fwd.reverse()
                    
                    path_bwd = []
                    at = neigh
                    while at is not None:
                        path_bwd.append(at)
                        at = bwd_parent[at]
                    return path_fwd + path_bwd[1:]
    
    return None  # No path (extremely rare with this operation set)

def main():
    bot_name = "grok_bot"
    print(f"Starting bot: {bot_name}", file=sys.stderr)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('localhost', 7474))
        sock.sendall((bot_name + '\n').encode('utf-8'))
        print("Connected to server at localhost:7474", file=sys.stderr)
        
        # Use makefile for clean, buffered line-by-line reading (handles any batching)
        reader = sock.makefile('r', encoding='utf-8')
        
        while True:
            # Receive challenge (START,GOAL)
            line = reader.readline()
            if not line:
                print("Server closed connection.", file=sys.stderr)
                break
            line = line.strip()
            if not line or ',' not in line:
                continue
            
            start, goal = [x.strip().upper() for x in line.split(',', 1)]
            print(f"New challenge: {start} -> {goal}", file=sys.stderr)
            
            path = find_ladder(start, goal)
            if path:
                print(f"Path found ({len(path)} words) - submitting...", file=sys.stderr)
                submission = '\n'.join(path) + '\n'
                sock.sendall(submission.encode('utf-8'))
            else:
                print("No path found (will be disqualified)", file=sys.stderr)
                continue  # Server will timeout/DQ us
            
            # Receive server verdict (0 = accepted, 1 = disqualified)
            resp_line = reader.readline().strip()
            if resp_line == '0':
                print("✅ Round accepted - ready for next challenge", file=sys.stderr)
            elif resp_line == '1':
                print("❌ Disqualified / timeout. Exiting tournament.", file=sys.stderr)
                break
            else:
                print(f"Unknown server response: {resp_line}", file=sys.stderr)
                break
                
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
    finally:
        sock.close()
        print("Client terminated.", file=sys.stderr)

if __name__ == "__main__":
    main()