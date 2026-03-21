#!/usr/bin/env python3
"""
Growing Word Ladder Tournament Client — claude_bot

Strategy:
  • Pure on-the-fly neighbour generation (no giant precomputed maps).
  • Bidirectional BFS — keeps the explored frontier tiny.
  • Per-round neighbour cache — avoids duplicate string work when
    both search directions touch the same word.
"""

import socket
import sys


# ── Dictionary ───────────────────────────────────────────────────────────────

ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def load_dictionary(path: str = "dictionary.txt") -> frozenset:
    with open(path, "r") as fh:
        return frozenset(line.strip().upper() for line in fh if line.strip())


# ── Neighbour generation (on-the-fly, cached per round) ─────────────────────

_cache = {}


def get_neighbours(word, word_set):
    """All words reachable by exactly one change / add / remove."""
    hit = _cache.get(word)
    if hit is not None:
        return hit

    L = len(word)
    result = []

    # 1) Change exactly one letter — 25·L candidates
    for i in range(L):
        pre = word[:i]
        suf = word[i + 1:]
        orig = word[i]
        for c in ALPHA:
            if c != orig:
                w = pre + c + suf
                if w in word_set:
                    result.append(w)

    # 2) Add exactly one letter — 26·(L+1) candidates
    for i in range(L + 1):
        pre = word[:i]
        suf = word[i:]
        for c in ALPHA:
            w = pre + c + suf
            if w in word_set:
                result.append(w)

    # 3) Remove exactly one letter — L candidates
    for i in range(L):
        w = word[:i] + word[i + 1:]
        if w in word_set:
            result.append(w)

    _cache[word] = result
    return result


# ── Bidirectional BFS ────────────────────────────────────────────────────────


def find_path(start, goal, word_set):
    if start == goal:
        return [start]
    if start not in word_set or goal not in word_set:
        return None

    _cache.clear()

    # parent maps: word -> predecessor (None for root)
    fwd_parent = {start: None}
    bwd_parent = {goal: None}
    fwd_front = [start]
    bwd_front = [goal]

    def _reconstruct(meeting):
        """Build the full path through the meeting point."""
        path = []
        w = meeting
        while w is not None:
            path.append(w)
            w = fwd_parent[w]
        path.reverse()
        w = bwd_parent[meeting]
        while w is not None:
            path.append(w)
            w = bwd_parent[w]
        return path

    def _expand(front, own, other):
        """Expand one BFS level. Returns next frontier list, or a meeting-point word."""
        nxt = []
        for w in front:
            for nb in get_neighbours(w, word_set):
                if nb in own:
                    continue
                own[nb] = w
                if nb in other:
                    return nb  # meeting point
                nxt.append(nb)
        return nxt

    while fwd_front and bwd_front:
        # Always expand the smaller frontier first
        if len(fwd_front) <= len(bwd_front):
            result = _expand(fwd_front, fwd_parent, bwd_parent)
            if isinstance(result, str):
                return _reconstruct(result)
            fwd_front = result
        else:
            result = _expand(bwd_front, bwd_parent, fwd_parent)
            if isinstance(result, str):
                return _reconstruct(result)
            bwd_front = result

    return None


# ── Network I/O ──────────────────────────────────────────────────────────────


def main():
    # Load dictionary before connecting (startup cost is OK)
    print("[*] Loading dictionary ...", flush=True)
    word_set = load_dictionary()
    print(f"[*] {len(word_set):,} words loaded.", flush=True)

    # Connect
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("localhost", 7474))
    sf = sock.makefile("rb")  # buffered reader for clean line reads
    sock.sendall(b"claude_bot\n")
    print("[*] Connected as claude_bot", flush=True)

    round_num = 0
    try:
        while True:
            # ── Read challenge ───────────────────────────────────────
            raw = sf.readline()
            if not raw:
                print("[!] Server closed connection.", flush=True)
                break

            line = raw.decode().strip()
            if not line:
                continue

            # Guard against stray verdict lines
            if line == "1":
                print("[!] Disqualified / game over.", flush=True)
                break
            if line == "0":
                continue
            if "," not in line:
                continue

            start, goal = line.split(",", 1)
            start = start.strip().upper()
            goal = goal.strip().upper()
            round_num += 1
            print(f"[R{round_num}] {start} -> {goal}", end=" ... ", flush=True)

            # ── Solve ────────────────────────────────────────────────
            path = find_path(start, goal, word_set)

            if path:
                payload = "".join(w + "\n" for w in path)
                sock.sendall(payload.encode())
                print(f"sent {len(path)} words ({len(path)-1} steps).", flush=True)
            else:
                # No path found — send stub, accept disqualification
                sock.sendall(f"{start}\n{goal}\n".encode())
                print("NO PATH -- sent stub.", flush=True)

            # ── Read verdict ─────────────────────────────────────────
            raw = sf.readline()
            if not raw:
                print("[!] Server closed connection.", flush=True)
                break

            verdict = raw.decode().strip()
            if verdict == "0":
                print(f"[R{round_num}] Accepted.", flush=True)
            else:
                print(f"[R{round_num}] Rejected ({verdict}).", flush=True)
                break

    except (ConnectionError, BrokenPipeError, OSError) as exc:
        print(f"[!] Connection error: {exc}", flush=True)
    finally:
        sf.close()
        sock.close()
        print("[*] Disconnected.", flush=True)


if __name__ == "__main__":
    main()