# bot author: ChatGPT GPT 5.5
#!/usr/bin/env python3
# bot author: GPT-5.5 Thinking

"""
SquishyWordBits tournament bot, Python 3.10, standard library only.

Strategy:
  * Load dictionary.txt before connecting.
  * Encode every positive-scoring dictionary word, keeping only the best word
    for each identical bit encoding.
  * Build a compact binary trie of word encodings.
  * For each round, scan the bitstream through the trie to find all word
    intervals, then solve the non-overlapping selection exactly with dynamic
    programming over bit positions.
"""

import os
import re
import socket
import sys
import time
from typing import List, Optional, Tuple

HOST = "localhost"
PORT = 7474
ROUND_BUDGET_SECONDS = 27.0  # leave margin for sending before the 30s server limit
BOTNAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

LETTER_BITS = [format(i, "b") for i in range(26)]


def encode_word(word: str) -> str:
    return "".join(LETTER_BITS[ord(ch) - 97] for ch in word)


class EncodingTrie:
    __slots__ = ("next0", "next1", "score", "word")

    def __init__(self) -> None:
        self.next0: List[int] = [-1]
        self.next1: List[int] = [-1]
        self.score: List[int] = [0]
        self.word: List[Optional[str]] = [None]

    def _new_node(self) -> int:
        idx = len(self.next0)
        self.next0.append(-1)
        self.next1.append(-1)
        self.score.append(0)
        self.word.append(None)
        return idx

    def insert(self, bits: str, word_upper: str, score: int) -> None:
        node = 0
        for b in bits:
            if b == "0":
                nxt = self.next0[node]
                if nxt < 0:
                    nxt = self._new_node()
                    self.next0[node] = nxt
            else:
                nxt = self.next1[node]
                if nxt < 0:
                    nxt = self._new_node()
                    self.next1[node] = nxt
            node = nxt

        old_score = self.score[node]
        old_word = self.word[node]
        # Same encoding can correspond to multiple dictionary words because the
        # letter code is not prefix-free. Submit the highest-scoring one.
        if score > old_score or (score == old_score and (old_word is None or word_upper < old_word)):
            self.score[node] = score
            self.word[node] = word_upper


def is_plain_lower_word(s: str) -> bool:
    return bool(s) and all("a" <= ch <= "z" for ch in s)


def find_dictionary_path() -> str:
    candidates = [
        os.path.join(os.getcwd(), "dictionary.txt"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "dictionary.txt"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError("dictionary.txt not found in cwd or beside bot script")


def load_trie() -> EncodingTrie:
    trie = EncodingTrie()
    path = find_dictionary_path()

    # De-duplicate exact words defensively; some word lists contain repeats.
    seen = set()
    with open(path, "r", encoding="ascii", errors="ignore") as f:
        for line in f:
            w = line.strip()
            if w in seen:
                continue
            seen.add(w)
            if not is_plain_lower_word(w):
                continue
            # Length <= 3 never helps maximize score because it is non-positive.
            if len(w) <= 3:
                continue
            score = len(w) - 3
            trie.insert(encode_word(w), w.upper(), score)
    return trie


def solve_round(bits: str, trie: EncodingTrie, start_time: float) -> List[Tuple[str, int]]:
    n = len(bits)
    by_end: List[List[Tuple[int, int, str]]] = [[] for _ in range(n + 1)]
    next0, next1, scores, words = trie.next0, trie.next1, trie.score, trie.word

    # Find encoded dictionary words that occur at each offset. This is normally
    # very fast for 20k bits, but keep a wall-clock guard so the bot always
    # submits something valid rather than timing out.
    for s in range(n):
        if (s & 1023) == 0 and time.monotonic() - start_time > ROUND_BUDGET_SECONDS:
            break
        node = 0
        for pos in range(s, n):
            if bits[pos] == "0":
                node = next0[node]
            else:
                node = next1[node]
            if node < 0:
                break
            sc = scores[node]
            if sc > 0:
                w = words[node]
                if w is not None:
                    by_end[pos + 1].append((s, sc, w))

    # Weighted interval scheduling over bit positions:
    # dp[i] = best score using only bits before i.
    dp = [0] * (n + 1)
    choice: List[Optional[Tuple[int, int, str]]] = [None] * (n + 1)

    for i in range(1, n + 1):
        best = dp[i - 1]
        best_choice = None
        for s, sc, w in by_end[i]:
            val = dp[s] + sc
            if val > best:
                best = val
                best_choice = (s, sc, w)
        dp[i] = best
        choice[i] = best_choice

    selected: List[Tuple[str, int]] = []
    i = n
    while i > 0:
        ch = choice[i]
        if ch is None:
            i -= 1
        else:
            s, sc, w = ch
            selected.append((w, s))
            i = s
    selected.reverse()
    return selected


def send_submission(sock: socket.socket, selected: List[Tuple[str, int]]) -> None:
    parts = []
    for w, off in selected:
        parts.append(f"WORD {w} {off}\n")
    parts.append("END\n")
    sock.sendall("".join(parts).encode("ascii"))


def main() -> int:
    botname = os.environ.get("BOTNAME", "").strip("\n")
    if not botname or not BOTNAME_RE.match(botname):
        print("BOTNAME must be 1-32 chars from [A-Za-z0-9_-]", file=sys.stderr)
        return 2

    try:
        trie = load_trie()
    except Exception as exc:
        print(f"failed to load dictionary: {exc}", file=sys.stderr)
        return 2

    with socket.create_connection((HOST, PORT)) as sock:
        # No socket read timeout: the spec says idle reads should block.
        sock.sendall((botname + "\n").encode("ascii"))
        reader = sock.makefile("r", encoding="ascii", newline="\n")

        while True:
            line = reader.readline()
            if line == "":
                return 0
            line = line.rstrip("\n")

            if line == "TOURNAMENT_END":
                return 0

            if not line.startswith("ROUND "):
                # Ignore status/noise defensively. The expected statuses after a
                # submission are consumed by the loop below.
                continue

            start = time.monotonic()
            try:
                _, round_no, bits = line.split(" ", 2)
            except ValueError:
                sock.sendall(b"END\n")
                continue

            if not bits or any(ch not in "01" for ch in bits):
                sock.sendall(b"END\n")
                continue

            selected = solve_round(bits, trie, start)
            send_submission(sock, selected)

            # Server then sends OK/INVALID and END_ROUND n. Consume through the
            # round terminator before waiting for the next ROUND.
            while True:
                reply = reader.readline()
                if reply == "":
                    return 0
                reply = reply.rstrip("\n")
                if reply == "TOURNAMENT_END":
                    return 0
                if reply == f"END_ROUND {round_no}":
                    break


if __name__ == "__main__":
    raise SystemExit(main())