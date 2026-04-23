import socket
import sys
import json

HOST = "localhost"
PORT = 7474

# ---------- Utilities ----------

def top_disk(tower):
    return tower[-1] if tower else None

def can_place(disk, tower):
    return not tower or tower[-1] > disk

def find_disk(state, disk):
    for i, t in enumerate(state):
        if t and t[-1] == disk:
            return i
    return None

def is_goal(state, m, goal_idx):
    return len(state[goal_idx]) == m and state[goal_idx] == list(range(m, 0, -1))


# ---------- Hero Strategy ----------

def hero_move(state, n, m):
    goal = n - 1

    best_move = None
    best_score = -1e9

    for i in range(n):
        if not state[i]:
            continue
        disk = state[i][-1]

        for j in range(n):
            if i == j:
                continue
            if can_place(disk, state[j]):
                # scoring heuristic
                score = 0

                # prefer moving toward goal
                score += (j - i)

                # prefer smaller disks
                score -= disk * 0.1

                # bonus for placing on goal
                if j == goal:
                    score += 5

                # avoid undoing progress
                if i > j:
                    score -= 0.5

                if score > best_score:
                    best_score = score
                    best_move = (i, j)

    return best_move


# ---------- Villain Strategy ----------

def villain_move(state, last_from, last_to, n):
    disk = top_disk(state[last_to])
    if disk is None:
        return "PASS"

    options = []
    for d in (-1, 1):
        to = last_to + d
        if 0 <= to < n and can_place(disk, state[to]):
            options.append(to)

    if not options:
        return "PASS"

    goal = n - 1

    # prefer moving away from goal
    best = None
    best_score = -1e9

    for to in options:
        score = 0
        score -= abs(goal - to)  # farther from goal is better

        if score > best_score:
            best_score = score
            best = to

    return (last_to, best)


# ---------- State Update ----------

def apply_move(state, move):
    if move == "PASS":
        return
    f, t = move
    disk = state[f].pop()
    state[t].append(disk)


# ---------- Client ----------

def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((HOST, PORT))

    f = s.makefile("rw")

    # register
    f.write("gpt5_3_bot\n")
    f.flush()

    games = {
        1: {"state": None, "role": None, "last": None},
        2: {"state": None, "role": None, "last": None},
    }

    while True:
        line = f.readline()
        if not line:
            break
        line = line.strip()

        if line.startswith("ROUND"):
            continue

        elif line.startswith("BOARD"):
            _, n, m = line.split()
            n = int(n)
            m = int(m)

            # init both games
            init = [list(range(m, 0, -1))] + [[] for _ in range(n - 1)]
            for g in games:
                games[g]["state"] = json.loads(json.dumps(init))
                games[g]["last"] = None

        elif line.startswith("GAME"):
            g = int(line[4])
            role = line.split()[1]
            games[g]["role"] = role

        elif line.startswith("YOURTURN"):
            g = int(line.split()[1])

            state_line = f.readline().strip()
            last_line = f.readline().strip()

            state = json.loads(state_line.split(" ", 1)[1])
            games[g]["state"] = state

            if last_line == "LAST NONE":
                last = None
            else:
                _, a, b = last_line.split()
                last = (int(a), int(b))
            games[g]["last"] = last

            role = games[g]["role"]

            if role == "HERO":
                move = hero_move(state, n, m)
                if move is None:
                    print("0 0")
                    f.write("0 0\n")
                else:
                    f.write(f"{move[0]} {move[1]}\n")
                f.flush()

                apply_move(state, move)

            else:  # VILLAIN
                if last is None:
                    f.write("PASS\n")
                    f.flush()
                    continue

                move = villain_move(state, last[0], last[1], n)

                if move == "PASS":
                    f.write("PASS\n")
                else:
                    f.write(f"{move[0]} {move[1]}\n")
                f.flush()

                apply_move(state, move if move != "PASS" else None)

        elif line.startswith("OPPONENT"):
            parts = line.split()
            g = int(parts[1])
            role = parts[2]

            if parts[3] == "PASS":
                continue

            f_t = int(parts[3])
            t_t = int(parts[4])

            apply_move(games[g]["state"], (f_t, t_t))

        elif line.startswith("RESULT"):
            continue

        elif line.startswith("ROUND_SCORE"):
            continue

        elif line.startswith("MATCHUP"):
            break

    s.close()


if __name__ == "__main__":
    main()