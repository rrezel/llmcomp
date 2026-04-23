# Day 9 Challenge: Towers of Annoy

**Task:** Write a Python 3.10 client that plays a two-player adversarial variant of the Towers of Hanoi in a round-robin tournament.

---

### 1. Overview

Standard Towers of Hanoi — classic disks-on-towers rules — but with an antagonist. One bot plays **Hero** and tries to move all disks from the leftmost tower to the rightmost. The other bot plays **Villain** and tries to prevent that.

The villain's move is tightly constrained: after every hero move, the villain **must move the exact disk the hero just moved, to an adjacent tower**. The villain still obeys Hanoi placement rules (no larger disk on a smaller one). If the villain literally has no legal move, they must pass.

Hero has a limited budget of `2^m + 1` moves, where `m` is the number of disks. If the hero doesn't finish within that budget, the villain wins.

The tournament is a round-robin: every bot plays a matchup against every other bot. Each matchup uses a penalty-shootout format (see section 3).

---

### 2. Connection & Registration

* Connect via TCP to `localhost:7474`.
* Send your bot name followed by a newline: `{model_name}_bot\n`

---

### 3. Matchup Flow

Each matchup between two bots proceeds as follows:

**Penalty shootout format:**
* Up to 5 rounds per matchup. Each round = 2 games played simultaneously on the same board configuration.
* In Game 1 you play Hero; your opponent plays Villain.
* In Game 2 you play Villain; your opponent plays Hero.
* **1 match point per game won** — whether you won as Hero (reached the goal) or as Villain (prevented the opponent's hero from reaching the goal within budget).
* After 5 rounds, whichever bot has more match points wins the matchup (**3 tournament points** to the winner, **0** to the loser).
* If tied, sudden-death rounds continue until one player leads after a round.
* If still tied after 10 rounds, both players get **1 tournament point**.
* The server may terminate a matchup early if the outcome is decided.

---

### 4. Round Start

At the start of each round the server sends:

```
ROUND {n}
BOARD {num_towers} {num_disks}
GAME1 {HERO|VILLAIN}
GAME2 {HERO|VILLAIN}
```

* `BOARD 6 4` means 6 towers and 4 disks.
* `GAME1 HERO` means you play Hero in Game 1. The other game has the opposite role.

**Initial state:** all `m` disks stacked on tower `0`, largest at bottom, smallest on top. Goal: all `m` disks stacked in the same order on tower `n - 1`.

---

### 5. Turn Flow

Hero always moves first. Hero and villain then alternate. The server tells your bot when it's your turn in a given game:

```
YOURTURN {1 or 2}
STATE [[bottom,...,top], [...], ..., [...]]
LAST {from_tower} {to_tower}
```

* `STATE` is a JSON array of `n` sub-arrays — the stack of each tower bottom-to-top. Disks are integers `1..m`, where `1` is the smallest.
* `LAST` reports the previous move in this game. On the very first hero turn (before any move has been made) the line is `LAST NONE`.

You respond with a single line containing your move:

```
{from_tower} {to_tower}\n
```

Both are 0-indexed. Example: `0 2` moves the top disk of tower 0 onto tower 2.

**Villain-specific requirements:**
* `{from_tower}` must equal the previous hero move's `{to_tower}` (you must move the disk the hero just moved).
* `{to_tower}` must be `{from_tower} + 1` or `{from_tower} - 1` (linear adjacency; no wrap-around).
* The move must be Hanoi-legal (cannot place a larger disk on a smaller one).

**Villain with no legal move.** If both adjacent towers are out of bounds or would be a larger-on-smaller placement, the villain must respond with:

```
PASS
```

`PASS` is illegal if any legal villain move exists — submitting `PASS` in that case forfeits the game.

---

### 6. Opponent Notification

After both bots have completed a move-exchange in their respective games (hero move + villain move, or hero move + pass, or a win-on-hero-move that skips villain), each bot is sent a summary of what happened in the *other* game:

```
OPPONENT {1 or 2} HERO {from} {to}
OPPONENT {1 or 2} VILLAIN {from} {to}
OPPONENT {1 or 2} VILLAIN PASS
```

You must maintain your own view of both games' state between turns. The server does not re-send `STATE` unless it's your turn.

---

### 7. End of Game

A game ends as soon as any of the following happens:

* **Hero wins** — after any move (hero *or* villain), tower `n - 1` contains all `m` disks correctly stacked (largest at bottom, smallest at top). The game ends immediately, with no further villain response.
* **Villain wins** — the hero has made `2^m + 1` moves without achieving the goal state. (Villain passes and forfeits do not count toward this budget; only hero moves do.)
* **Forfeit** — a bot submits an illegal move, malformed input, or times out. That bot forfeits; the opponent wins the game.

The server notifies both bots:

```
RESULT GAME{1 or 2} {WIN|LOSS}
```

When both games of a round have finished:

```
ROUND_SCORE {your_match_points} {opponent_match_points}
```

When the matchup ends:

```
MATCHUP {WIN|LOSS|DRAW} {your_total} {opponent_total}
```

---

### 8. Board Configurations

Board size grows across rounds of a matchup:

| Round | Towers (n) | Disks (m) | Hero budget (2^m + 1) |
|---|---|---|---|
| 1 | 4 | 3 | 9 |
| 2 | 5 | 4 | 17 |
| 3 | 7 | 5 | 33 |
| 4 | 9 | 6 | 65 |
| 5 | 12 | 7 | 129 |

Sudden-death rounds (rounds 6–10) reuse the round 5 configuration.

---

### 9. Rules Recap

1. **Adjacency:** towers are in a line, `0` through `n - 1`. Tower `i` is adjacent to towers `i - 1` and `i + 1` only.
2. **Disk placement:** a disk may be placed on an empty tower or on top of a strictly larger disk. Applies to both hero and villain.
3. **Hero:** each turn, pick any legal Hanoi move — any source tower, any destination tower.
4. **Villain:** each turn, move the disk the hero just moved to an adjacent tower, or `PASS` if no such move is legal.
5. **Win check runs after every move, hero or villain.** If the goal state is reached, the game ends immediately.
6. **Budget:** hero is capped at `2^m + 1` moves. Villain moves and passes don't consume the budget.

---

### 10. Constraints

* **Language:** Standalone Python 3.10 script using only the **Standard Library**.
* **Timeout:** 2 seconds per move.
* **Invalid move** (illegal placement, wrong source for villain, non-adjacent for villain, `PASS` when a legal move exists, out of bounds, malformed input, timeout) = you forfeit that game. The opponent wins that game.
* **Port:** `localhost:7474`.
* **Indexing:** towers are 0-based; tower `0` is the start, tower `n - 1` is the goal. Disk sizes are `1..m`, where `1` is smallest.
