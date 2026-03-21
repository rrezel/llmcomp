import socket
import sys
import string
from collections import deque

# --- Algorithm Implementation ---

def get_neighbors(word, word_set):
    """Generates valid 1-step transformations and checks them against the dictionary in O(1)."""
    neighbors = []
    alphabet = string.ascii_uppercase
    word_len = len(word)

    # 1. Change 1 letter
    for i in range(word_len):
        for c in alphabet:
            if c != word[i]:
                new_word = word[:i] + c + word[i+1:]
                if new_word in word_set:
                    neighbors.append(new_word)

    # 2. Add 1 letter
    for i in range(word_len + 1):
        for c in alphabet:
            new_word = word[:i] + c + word[i:]
            if new_word in word_set:
                neighbors.append(new_word)

    # 3. Remove 1 letter
    for i in range(word_len):
        new_word = word[:i] + word[i+1:]
        if new_word in word_set:
            neighbors.append(new_word)

    return neighbors

def expand_layer(queue, visited_current, visited_other, word_set):
    """Expands one layer of the BFS, looking for an intersection with the other side."""
    for _ in range(len(queue)):
        current = queue.popleft()
        
        for neighbor in get_neighbors(current, word_set):
            if neighbor in visited_other:
                # Intersection found
                visited_current[neighbor] = current
                return neighbor
                
            if neighbor not in visited_current:
                visited_current[neighbor] = current
                queue.append(neighbor)
    return None

def construct_path(intersection, visited_start, visited_goal):
    """Reconstructs the full path once an intersection is found."""
    # Path from start to intersection
    path_start = []
    curr = intersection
    while curr is not None:
        path_start.append(curr)
        curr = visited_start.get(curr)
    path_start.reverse()
    
    # Path from intersection to goal (skipping the intersection to avoid duplication)
    path_goal = []
    curr = visited_goal.get(intersection)
    while curr is not None:
        path_goal.append(curr)
        curr = visited_goal.get(curr)
        
    return path_start + path_goal

def find_ladder_bidirectional(start, goal, word_set):
    """Executes a bi-directional BFS for maximum speed."""
    if start not in word_set or goal not in word_set:
        return None
    if start == goal:
        return [start]

    visited_start = {start: None}
    visited_goal = {goal: None}
    
    q_start = deque([start])
    q_goal = deque([goal])
    
    while q_start and q_goal:
        # Always expand the smaller frontier to minimize branching
        if len(q_start) <= len(q_goal):
            intersection = expand_layer(q_start, visited_start, visited_goal, word_set)
        else:
            intersection = expand_layer(q_goal, visited_goal, visited_start, word_set)
            
        if intersection:
            return construct_path(intersection, visited_start, visited_goal)
            
    return None

# --- Network & Core Loop ---

def load_dictionary(filepath="dictionary.txt"):
    try:
        print(f"Loading dictionary from {filepath}...")
        # Using a set is mandatory here for O(1) lookups
        with open(filepath, 'r', encoding='utf-8') as f:
            word_set = set(line.strip().upper() for line in f)
        print(f"Loaded {len(word_set)} words.")
        return word_set
    except FileNotFoundError:
        print(f"CRITICAL: {filepath} not found. Exiting.")
        sys.exit(1)

def main():
    word_set = load_dictionary()
    
    host = 'localhost'
    port = 7474
    bot_name = "gemini_3_1_pro_bot\n" 
    
    try:
        with socket.create_connection((host, port)) as sock:
            # makefile provides robust buffered text I/O over TCP
            f = sock.makefile('rw', encoding='utf-8')
            
            print(f"Connected to {host}:{port}. Registering bot...")
            f.write(bot_name)
            f.flush()
            
            while True:
                line = f.readline()
                if not line:
                    print("Connection closed by server.")
                    break
                    
                line = line.strip()
                if not line:
                    continue
                    
                # Handle Server Acknowledgment Codes
                if line == '0':
                    print("[✓] Sequence Accepted! Surviving to the next round.")
                    continue
                elif line == '1':
                    print("[X] Disqualified or Timed Out (Code 1). Terminating.")
                    break
                    
                # Handle New Challenges
                if ',' in line:
                    start_word, goal_word = line.split(',', 1)
                    print(f"\n[!] Challenge: {start_word} -> {goal_word}")
                    
                    path = find_ladder_bidirectional(start_word, goal_word, word_set)
                    
                    if path:
                        # Assemble block and send via TCP
                        submission = "\n".join(path) + "\n"
                        f.write(submission)
                        f.flush()
                        print(f"--> Submitted path of length {len(path)}.")
                    else:
                        print("--> No path found. Awaiting server timeout.")
                        
    except ConnectionRefusedError:
        print(f"Connection refused. Ensure the tournament server is running at {host}:{port}.")
    except Exception as e:
        print(f"Fatal Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()