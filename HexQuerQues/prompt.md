# HexQuerQues — Tournament Spec

## Task

**Write a complete, self-contained Python 3.10 bot client that competes in this tournament.** The bot connects to the tournament server at `localhost:7474`, plays every game it is dealt to the best of its ability, and tries to win as many matches as possible. Use only the Python standard library. Do not leave placeholder strategies, demo stubs, or "STRATEGY GOES HERE" comments — the bot must implement a full strategy that picks legal moves and plays for the win.

You may add your model name as a comment at the top of the file (e.g. `# bot author: <model name and version>`).

## 1. The game

HexQuerQues is a two-player capture game played on a board of **four concentric hexagons** (rings) plus **radial spokes** that connect each vertex of an inner ring to the corresponding vertex of the next-outer ring.

- **24 vertices total**: 6 vertices on each of 4 rings.
- **Ring index `r`**: `0` is the innermost ring, `3` is the outermost.
- **Vertex index `i`**: `0..5`, with `i=0` at angle 30° (upper-right), increasing **counterclockwise** around the ring.
- **Lines on the board**:
  - 6 perimeter edges per ring (around the hexagon): vertex `(r, i)` is line-connected to `(r, (i+1) mod 6)` and to `(r, (i-1) mod 6)`.
  - Radial spokes between consecutive rings: vertex `(r, i)` is line-connected to `(r-1, i)` (when `r ≥ 1`) and `(r+1, i)` (when `r ≤ 2`).
- A vertex's **line neighbors** are exactly those reachable by one segment along the lines above. The full neighbor set for each ring class:
  - `(0, i)` (innermost): 3 neighbors — `(0, (i+1) mod 6)`, `(0, (i-1) mod 6)`, `(1, i)`.
  - `(1, i)`: 4 neighbors — `(1, (i+1) mod 6)`, `(1, (i-1) mod 6)`, `(0, i)`, `(2, i)`.
  - `(2, i)`: 4 neighbors — `(2, (i+1) mod 6)`, `(2, (i-1) mod 6)`, `(1, i)`, `(3, i)`.
  - `(3, i)` (outermost): 3 neighbors — `(3, (i+1) mod 6)`, `(3, (i-1) mod 6)`, `(2, i)`.

**Pieces and starting position.** Each player starts with **6 pieces**, distributed across the two outermost rings (`r = 3` and `r = 2`) in an **alternating** pattern around each ring:

- Player **A** (assigned at game start): pieces on `(3, 0), (3, 2), (3, 4), (2, 0), (2, 2), (2, 4)`.
- Player **B**: pieces on `(3, 1), (3, 3), (3, 5), (2, 1), (2, 3), (2, 5)`.

The two innermost rings (`r = 0` and `r = 1`) start empty.

**Movement and capture (classic Alquerques rules).**

- **Slide**: on your turn, if no capture is available anywhere on the board for any of your pieces, move one of your pieces along a single line segment to an empty adjacent vertex.
- **Capture (jump)**: if a capture is available for any of your pieces, you must capture. A capture is performed by jumping a single piece over an adjacent enemy along a straight line (same ring or same radial spoke) and landing on the empty vertex immediately beyond on that same line. The jumped enemy is removed from the board.
  - Same-ring jump: `(r, i)` jumps over enemy at `(r, (i+1) mod 6)` to land on empty `(r, (i+2) mod 6)`. Direction can be either way around the ring.
  - Radial jump: `(r, i)` jumps over enemy at `(r+1, i)` to land on empty `(r+2, i)` (requires `r+2 ≤ 3`). Or `(r, i)` jumps over enemy at `(r-1, i)` to land on empty `(r-2, i)` (requires `r-2 ≥ 0`). Note: radial jumps are only possible for `r ∈ {0, 1, 2, 3}` such that `r±2` stays on the board, i.e., the spoke segment is straight through three collinear vertices.
- **Chain capture**: after a successful capture, if the **same piece** (the one that just jumped, now sitting on its new landing vertex) can immediately make another capture from that landing vertex, **it must continue jumping**. The chain ends only when, from the same piece's current landing vertex, no further capture is available. Other pieces' capture availability does **not** affect chain continuation; the obligation to continue applies only to the piece whose chain is in progress. Each jump in the chain is a separate jump segment; you may change direction between segments.
- **Captured pieces are removed immediately.** When a jump segment is executed, the jumped enemy is removed from the board *before* the next segment is checked. Empty squares may be revisited within a chain (including the chain's starting vertex, which becomes empty when the first jump is made); a vertex containing your own piece or any unjumped enemy may not be landed on.
- **Forced capture**: if any of your pieces can capture at the start of your turn, you must take a capture. The server rejects any non-capture slide when a capture exists. The server also rejects any partial chain that ends while another capture from the chain's final landing vertex is still available.

**Game outcomes.**

- **Win**: capture all 6 of your opponent's pieces, or stalemate your opponent. *Stalemate* means it is the opponent's turn and they have no legal move (no slide and no capture). The server checks for legal-move existence before sending `TURN`; if a player has no legal moves, the server skips `TURN` for that player and emits `GAME_END` directly with that player as the loser.
- **Draw**: 40 consecutive **plies** (one ply = one player's half-move; 40 plies = 20 moves by each side) without a capture → draw; or the same exact position (full board state + side-to-move) occurs three times → draw. The server detects both conditions and emits `GAME_END ... DRAW` immediately when met.
- **Loss**: the opposite of win, or your timer flag-falls, or you are disqualified for an illegal/malformed move.

## 2. Tournament structure

The tournament is a **round-robin of 1v1 matchups**. With `B` registered bots, each pair of bots plays exactly one matchup; there are `C(B, 2)` matchups in total.

**Each matchup is 2 games played consecutively, with first-mover swapped between the games.**

- Game 1 of the matchup: bot X plays as A (first to move), bot Y plays as B.
- Game 2 of the matchup: bot Y plays as A, bot X plays as B.

**Matchup outcome (decided by the 2 game results combined):**

| Game results from a bot's perspective | Matchup outcome | Tournament points |
|---|---|---|
| 2 wins | win | 3 |
| 1 win + 1 draw | win | 3 |
| 1 win + 1 loss | draw | 1 |
| 2 draws | draw | 1 |
| 1 draw + 1 loss | loss | 0 |
| 2 losses | loss | 0 |

**Tournament standings**: total tournament points, descending. Tiebreak by total game wins; further tiebreak by total enemy pieces captured.

## 3. Wire framing

- All messages in both directions are **ASCII text**, lines terminated by a single `\n` (LF, byte `0x0a`). **CRLF is invalid.** A line containing `\r` may be treated as malformed.
- Every server message is a complete line ending in `\n`. Every bot message must be a complete line ending in `\n`.
- The server reads bot input with line buffering. You must flush after each line you send (e.g. `sock.sendall(line.encode())` or `print(..., flush=True)` if using `print` over a `socket.makefile`).
- Lines have no leading or trailing whitespace beyond the single terminating `\n`. A trailing space, leading space, double space, or any non-conforming whitespace makes the line malformed and the server responds `DQ malformed`.

## 4. Connection handshake

1. **Read your bot name from the `BOTNAME` environment variable.** Do not hardcode it; do not derive it from `sys.argv`; do not generate it. The exact bytes in `os.environ['BOTNAME']` (after stripping any trailing `\n`) are your bot identifier — use them verbatim.
2. Open a TCP connection to `localhost:7474`.
3. **Send the BOTNAME value as the first line**, terminated by a single `\n`. The server reads exactly one line as your bot identifier. The value must be 1–32 characters from the set `[A-Za-z0-9_-]` (printable ASCII, no spaces, no tabs, no control chars, no `\r`). A value violating these rules causes the server to immediately close the connection — no DQ message, no participation in the tournament.
4. Wait for a `MATCH` line announcing your first matchup. Until you receive `MATCH`, do not send anything.

## 5. Match and game protocol

The server announces matches in a server-chosen order. Bots not in the current match stay silently connected.

**Match start (server → both paired bots):**

```
MATCH <m> <opponent_name>
```

`<m>` is a 1-indexed matchup number for logging. `<opponent_name>` is the BOTNAME of the bot you are paired with. Each matchup contains exactly 2 games.

**Game start (server → both paired bots):**

```
GAME <g> <your_color>
BOARD <space-separated cell list>
```

- `<g>` is `1` or `2` (the game number within the matchup).
- `<your_color>` is `A` or `B`. The bot whose color is `A` moves first.
- `BOARD` is the starting position, encoded as **24 space-separated cells** in the fixed order `0,0 0,1 0,2 0,3 0,4 0,5 1,0 1,1 ... 3,5` (rings 0..3 outer-loop, vertices 0..5 inner-loop). Each cell is `A` (player A's piece), `B` (player B's piece), or `.` (empty).
- The starting `BOARD` literal is always exactly:
  ```
  BOARD . . . . . . . . . . . . A B A B A B A B A B A B
  ```
  (12 dots covering rings 0 and 1, then `A B A B A B` for ring 2 vertices 0..5, then `A B A B A B` for ring 3 vertices 0..5.) Total 24 tokens.

**Per turn:**

If your color is `A` (first to move), the very first server message after `BOARD` is `TURN`. If your color is `B`, the first server message after `BOARD` is `OPP <move_line>` (your opponent's first move as A); after you process it, the server sends you `TURN`.

When it is your turn, the server sends:

```
TURN
```

You then send exactly one move line:

```
MOVE <r1>,<i1> -> <r2>,<i2>
```

for a slide, or

```
MOVE <r1>,<i1> -> <r2>,<i2> -> <r3>,<i3> [-> <r4>,<i4> ...]
```

for a chain capture. The arrow token is the literal three characters `space-dash-greater-than-space`, i.e. ` -> `. Strict regex (the server uses `re.fullmatch`):

```
^MOVE [0-3],[0-5](( -> [0-3],[0-5]){1,12})$
```

A slide has exactly one arrow segment and the destination must be a line-neighbor of the source, and empty. A chain capture has 1 or more arrow segments, each segment being a single jump (source over an adjacent enemy on a line to the empty cell immediately beyond on that same line); the chain must continue as long as the piece can capture, and end only when no further capture is available from the piece's final position.

**Server response to your move:**

| Server line | Meaning |
|---|---|
| `OK <captures>` | Move accepted. `<captures>` is the number of enemy pieces captured by this move (0 for a slide, ≥ 1 for a jump chain). The server has updated the position. |
| `DQ <reason>` | Your move was illegal or malformed. The current game ends as a loss for you; the matchup continues with game 2 (or ends if game 2 is already played). |

Closed list of `DQ <reason>` strings (in precedence order):

| Trigger | DQ reason |
|---|---|
| Line doesn't match the move regex (whitespace, CRLF, non-MOVE prefix, bad coords, etc.) | `DQ malformed` |
| Source cell is not occupied by one of your pieces | `DQ wrong_owner_<r>,<i>` |
| First segment is a slide (one arrow, distance 1) but a capture exists somewhere on the board for any of your pieces | `DQ must_capture` |
| Slide destination is not a line-neighbor of the source, or not empty | `DQ illegal_slide_<r>,<i>->_<r>,<i>` |
| Jump segment isn't `(jumper, jumped, landing)` collinear-on-board with `jumped` adjacent enemy and `landing` empty beyond | `DQ illegal_jump_<r>,<i>->_<r>,<i>` |
| Chain ends but the piece's final position can still capture | `DQ chain_unfinished_at_<r>,<i>` |

After `DQ`, the server sends a `GAME_END` line for the current game (see below) and the bot stays connected for the rest of the matchup and tournament.

**Per turn for the non-active bot:**

While it is your opponent's turn, the server is silent. When the opponent finishes a turn, the server sends you:

```
OPP <move_line>
```

where `<move_line>` is the literal `MOVE ...` line your opponent submitted and the server accepted. You apply that move to your local board state. Both bots see every accepted move broadcast this way.

**Game end (server → both paired bots):**

```
GAME_END <g> <result>
```

- `<g>` is the game number.
- `<result>` is one of `A_WINS`, `B_WINS`, `DRAW`, `A_DQ`, `B_DQ`, `A_TIMEOUT`, `B_TIMEOUT`, `A_STALEMATED`, `B_STALEMATED`. `A_DQ` / `A_TIMEOUT` / `A_STALEMATED` all count as a loss for A and a win for B (and vice versa). `A_STALEMATED` is sent when it is A's turn and A has no legal move; in that case A never receives the `TURN` for that move, just `GAME_END`.

After `GAME_END` for game 1, the server sends `GAME 2 ...` to start game 2. After `GAME_END` for game 2, the server sends:

```
MATCH_END <m> <result_for_each_bot>
```

where `<result_for_each_bot>` is two space-separated tokens of the form `<botname>=<W|D|L>:<game_wins>` summarizing the matchup result.

**Tournament end:**

After the final matchup, the server sends:

```
TOURNAMENT_END
```

Stay connected for the duration of the tournament; do not set socket read timeouts.

## 6. Move validity reference

A move `MOVE r1,i1 -> r2,i2 -> ... -> rk,ik` (for `k ≥ 2`) is valid if and only if all of the following hold against the position at the start of your turn:

1. The line matches the move regex in §5.
2. `(r1, i1)` is occupied by your piece. Each subsequent `(rj, ij)` must satisfy the relevant slide-or-jump check below.
3. **Slide case** (`k = 2`, exactly one segment):
   - There is no capture available anywhere on the board for any of your pieces.
   - `(r2, i2)` is a line-neighbor of `(r1, i1)`.
   - `(r2, i2)` is empty.
4. **Capture case** (`k ≥ 2`, where the segment lengths and the on-board arithmetic identify each as a jump rather than a slide). For each segment `(rj, ij) -> (rj+1, ij+1)`:
   - There is exactly one vertex `(mj, nj)` strictly between `(rj, ij)` and `(rj+1, ij+1)` on a single board line.
     - Same-ring: `rj == rj+1` and `ij+1 == (ij ± 2) mod 6`, with the jumped vertex `(rj, (ij ± 1) mod 6)`.
     - Radial: `ij == ij+1` and `rj+1 == rj ± 2` with `rj+1 ∈ {0, 1, 2, 3}`, and the jumped vertex `(rj ± 1, ij)`.
   - The jumped vertex `(mj, nj)` is occupied by an enemy piece **at the moment that segment is executed** (i.e., not already removed by an earlier segment in this chain — you may not jump the same enemy twice).
   - `(rj+1, ij+1)` is empty at the moment that segment is executed (or it is your own starting vertex `(r1, i1)`, which is now empty because the piece left it; however revisiting any non-start vertex inside the chain is forbidden).
5. **Chain completeness**: after applying the chain, the piece sitting at `(rk, ik)` must have no further capture available (no enemy adjacent to it whose far side is an empty in-line vertex). If a capture is still available, the chain is not complete and the move is rejected.

There is no restriction on direction within a chain (you may zig-zag between same-ring jumps and radial jumps). You may not abort a chain early to avoid losing the piece.

## 7. Pace of play and timing

Each bot has a **per-game wall-clock budget of 30 seconds total** (chess-clock style — *not* a per-move limit). The 30 s budget is allocated for the bot's entire game. The clock starts decrementing the instant the server sends `TURN` to the bot and stops decrementing the instant the server reads the bot's complete (newline-terminated) move line. While the opponent is thinking or while server messages are being processed, the bot's clock is paused. At the start of each new game, the bot's clock is reset to a fresh 30 s.

If a bot's clock reaches 0 before its current `MOVE` line arrives, the server emits `DQ timeout` to that bot, and the game ends with that bot's color flagged in `GAME_END` (`A_TIMEOUT` or `B_TIMEOUT`). The matchup continues with game 2.

Bots may not send any line outside their own `TURN` window (i.e., no pre-emptive moves before `TURN`, no extra lines between `TURN` and `MOVE`). Anything sent outside that window is silently discarded by the server.

## 8. Constraints

- One TCP connection per bot, opened once at startup and held open until `TOURNAMENT_END` or socket close.
- Standard library only.
- Bot identifier from `BOTNAME` env var (see §4).
- Game timer 30 s per side per game; matchup is exactly 2 games; tournament structure is round-robin.
- The tournament may take many minutes wall-clock. Do not set socket read timeouts; idle reads should block.

## 9. Sample wire transcript

Illustrative — a single matchup between bots `alpha_bot` and `beta_bot`, showing one game in full and the start of the second game. The `>>` lines are bytes the bot sends, `<<` are bytes the server sends; this transcript is from `alpha_bot`'s point of view.

```
>> alpha_bot
<< MATCH 1 beta_bot
<< GAME 1 A
<< BOARD . . . . . . . . . . . . A B A B A B A B A B A B
<< TURN
>> MOVE 2,0 -> 1,0
<< OK 0
<< OPP MOVE 2,1 -> 1,1
<< TURN
>> MOVE 3,0 -> 2,0
<< OK 0
<< OPP MOVE 3,1 -> 2,1
<< TURN
>> MOVE 1,0 -> 1,2
<< OK 1
<< OPP MOVE 2,1 -> 0,1
<< TURN
>> MOVE 1,2 -> 1,4 -> 3,4
<< OK 2
<< OPP MOVE 0,1 -> 0,3
<< TURN
... (game continues until terminal state)
<< GAME_END 1 A_WINS
<< GAME 2 B
<< BOARD . . . . . . . . . . . . A B A B A B A B A B A B
<< OPP MOVE 2,0 -> 1,0
<< TURN
>> MOVE 2,1 -> 1,1
... (game 2 continues)
<< GAME_END 2 B_WINS
<< MATCH_END 1 alpha_bot=W:2 beta_bot=L:0
<< MATCH 2 ...
```

Walk-through:
- **Connect.** First line is the bot's `BOTNAME`. The server reads exactly one line as the bot identifier.
- **MATCH header.** `MATCH 1 beta_bot` announces the first matchup and the opponent.
- **GAME header.** `GAME 1 A` says this is game 1 and `alpha_bot` is color A (first to move). `BOARD` lists 24 cells in the fixed order `0,0 0,1 ... 3,5`.
- **TURN, MOVE, OK.** Bot's turn → server emits `TURN`. Bot sends `MOVE 2,0 -> 1,0` (radial slide inward). Server validates and accepts: `OK 0` (zero captures). The server then notifies the opponent via `OPP MOVE 2,0 -> 1,0` on their side.
- **Opponent move broadcast.** While `alpha_bot` waits, the server processes `beta_bot`'s move and broadcasts it via `OPP MOVE 2,1 -> 1,1`. `alpha_bot` updates its local board.
- **Capture.** `MOVE 1,0 -> 1,2` is a same-ring jump over the enemy at `1,1`, capturing it (`OK 1`). Since the piece at `1,2` has no further capture, the chain ends after one segment.
- **Game end and game 2.** After the win, server emits `GAME_END 1 A_WINS`, then `GAME 2 B` (alpha is now color B and goes second). The opponent's first move is broadcast as `OPP ...` since alpha is no longer first to move.
- **Match end.** `MATCH_END 1 alpha_bot=W:2 beta_bot=L:0` summarizes the matchup: alpha won the matchup, total 2 game wins; beta lost, 0 game wins.

## 10. Notes

- Track your local copy of the board state. The server announces every accepted move (your own via `OK` and the opponent's via `OPP`), but never re-broadcasts the full board between turns.
- A `DQ` ends the current game only. Stay connected; the matchup proceeds with game 2.
- The arrow token in `MOVE` is literally space-dash-greater-than-space; any other separator is `DQ malformed`.
- Coordinates are always 0-indexed and in decimal, with `r ∈ 0..3` and `i ∈ 0..5`.
- Do not send lines outside your `TURN` window. Bytes received outside the window are discarded.
