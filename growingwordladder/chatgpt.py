import socket
import sys
from collections import deque, defaultdict

HOST = "localhost"
PORT = 7474
BOT_NAME = "gpt5_3_bot"

# -------------------------
# Load dictionary
# -------------------------
def load_dictionary(path="dictionary.txt"):
    words = set()
    buckets = defaultdict(set)
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            w = line.strip().upper()
            if not w:
                continue
            words.add(w)
            buckets[len(w)].add(w)
    return words, buckets

WORDS, BUCKETS = load_dictionary()

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# -------------------------
# Neighbor generation
# -------------------------
def neighbors(word):
    L = len(word)

    # CHANGE one letter
    for i in range(L):
        for c in ALPHABET:
            if c != word[i]:
                w = word[:i] + c + word[i+1:]
                if w in WORDS:
                    yield w

    # ADD one letter
    for i in range(L + 1):
        for c in ALPHABET:
            w = word[:i] + c + word[i:]
            if w in WORDS:
                yield w

    # REMOVE one letter
    if L > 1:
        for i in range(L):
            w = word[:i] + word[i+1:]
            if w in WORDS:
                yield w

# -------------------------
# Bidirectional BFS
# -------------------------
def bidirectional_bfs(start, goal):
    if start == goal:
        return [start]

    if start not in WORDS or goal not in WORDS:
        return None

    # Frontiers
    front = {start}
    back = {goal}

    # Parents
    parent_f = {start: None}
    parent_b = {goal: None}

    while front and back:
        # Expand smaller frontier
        if len(front) <= len(back):
            next_front = set()
            for word in front:
                for nb in neighbors(word):
                    if nb in parent_f:
                        continue
                    parent_f[nb] = word

                    if nb in parent_b:
                        return build_path(nb, parent_f, parent_b)

                    next_front.add(nb)
            front = next_front
        else:
            next_back = set()
            for word in back:
                for nb in neighbors(word):
                    if nb in parent_b:
                        continue
                    parent_b[nb] = word

                    if nb in parent_f:
                        return build_path(nb, parent_f, parent_b)

                    next_back.add(nb)
            back = next_back

    return None

def build_path(meeting, parent_f, parent_b):
    path = []

    # Forward side
    cur = meeting
    while cur:
        path.append(cur)
        cur = parent_f[cur]
    path.reverse()

    # Backward side
    cur = parent_b[meeting]
    while cur:
        path.append(cur)
        cur = parent_b[cur]

    return path

# -------------------------
# Networking
# -------------------------
def run():
    with socket.create_connection((HOST, PORT)) as sock:
        f = sock.makefile("rw", encoding="utf-8", newline="\n")

        # Send bot name
        f.write(BOT_NAME + "\n")
        f.flush()

        while True:
            line = f.readline()
            if not line:
                break

            line = line.strip()
            if not line:
                continue

            try:
                start, goal = line.split(",")
                start = start.strip().upper()
                goal = goal.strip().upper()
            except ValueError:
                continue

            path = bidirectional_bfs(start, goal)

            if not path:
                # No valid path -> lose immediately
                return

            # Send sequence
            for w in path:
                f.write(w + "\n")
            f.flush()

            # Read response
            resp = f.readline()
            if not resp or resp.strip() == "1":
                return
            # else "0" → continue next round

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        sys.exit(0)