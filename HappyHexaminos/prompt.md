# HappyHexaminos — Tournament Spec

## Task

**Write a complete, self-contained Python 3.10 bot client that competes in this tournament.** The bot connects to the tournament server at `localhost:7474`, plays every round it is dealt, and tries to score as many tournament points as possible. Use only the Python standard library. Do not leave placeholder strategies, demo stubs, or "STRATEGY GOES HERE" comments — the bot must implement a full strategy that produces a valid tiling for each round.

You may add your model name as a comment at the top of the file (e.g. `# bot author: <model name and version>`).

## 1. The puzzle

A **hexomino** is a 6-cell connected polyomino on a square grid. Two hexominoes are considered the same shape ("free hexominoes") if one can be obtained from the other by rotation and/or reflection. There are exactly **35 free hexominoes** (the catalog is in §7).

Each round, the server sends the bot a rectangle of width `w` and height `h` with `w * h ≡ 0 (mod 6)`. The rectangle is server-generated and **guaranteed tileable** by some subset of the 35 free hexominoes (the server constructs a witness tiling before sending the round, so a valid full tiling always exists, though the server does not reveal it).

The bot must respond with a **full tiling** of the rectangle: a partition of all `w * h` cells into `k = w * h / 6` connected 6-cell regions, each of which is one of the 35 free hexominoes (in some rotation/reflection).

The bot's score for the round is its **inventory**: the number of *distinct* free-hexomino shapes used in the tiling. A tiling that uses 4 distinct shapes (with as many copies of each as needed) has inventory 4. **Higher inventory is better** — the goal is to pack as many *different* hexomino shapes as possible into the rectangle while still completing a valid tiling.

Bounds:

- `1 ≤ w, h ≤ 30`
- `w * h ≥ 36`
- `w * h ≡ 0 (mod 6)`
- Areas grow monotonically across the 10 rounds.

## 2. Tournament structure

The tournament is **10 rounds** played serially. Every registered bot plays every round.

**Per-round scoring (medal):**

- The bot with the **highest** inventory earns **gold = 3 points**.
- The bot with the next-highest inventory earns **silver = 2 points**.
- The bot with the next-next-highest inventory earns **bronze = 1 point**.
- All other bots score **0 points** for the round.

**Tiebreak within a medal slot.** Two or more bots tied at the same inventory: the medal goes to the bot whose complete submission arrived at the server first (earlier wall-clock arrival wins). The other bots in that tied group drop down — so e.g. if the two highest inventories are equal, the earlier-arriving bot gets gold (3) and the later-arriving bot gets silver (2); the next inventory below them gets bronze (1).

**Invalid or missing submission** (timeout, malformed grid, region that isn't a 6-cell hexomino, duplicate piece-instance label, partial coverage, out-of-bounds, etc.) → **0 points** for that round, regardless of submission timestamp.

**Tournament standings:** total tournament points across all 10 rounds, descending. Tiebreak by total medals (gold > silver > bronze); further tiebreak by highest cumulative inventory across rounds where a medal was earned.

## 3. Wire framing

- All messages in both directions are **ASCII text**, lines terminated by a single `\n` (LF, byte `0x0a`). **CRLF is invalid.**
- Every server message is a complete line ending in `\n`. Every bot message must be a complete line ending in `\n`.
- The server reads bot input with line buffering. You must flush after each line you send (e.g. `sock.sendall(line.encode())`).
- Lines have no leading or trailing whitespace beyond the single terminating `\n`. A trailing space, leading space, double space, or any non-conforming whitespace makes the line malformed.

## 4. Connection handshake

1. **Read your bot name from the `BOTNAME` environment variable.** Do not hardcode it; do not derive it from `sys.argv`; do not generate it. The exact bytes in `os.environ['BOTNAME']` (after stripping any trailing `\n`) are your bot identifier — use them verbatim. If `BOTNAME` is absent or empty, the bot is misconfigured and should not attempt to connect.
2. Open a TCP connection to `localhost:7474`.
3. **Send the BOTNAME value as the first line**, terminated by a single `\n`. The server reads exactly one line as your bot identifier. The value must be 1–32 characters from the set `[A-Za-z0-9_-]`. A value violating these rules causes the server to immediately close the connection.
4. Wait for a `ROUND` line announcing the first round. Until you receive `ROUND`, do not send anything.

## 5. Round protocol

The server announces each round to all registered bots simultaneously:

```
ROUND <n> <w> <h>
```

- `<n>` is the 1-indexed round number, `1..10`.
- `<w>` is the rectangle width (number of columns), `1..30`.
- `<h>` is the rectangle height (number of rows), `1..30`.

The bot has **30 seconds wall-clock** from the instant the server sends `ROUND` to the instant the server has read the bot's complete submission (all `h` lines plus the trailing `END`). The clock counts the bot's compute time **and** any time the bot spends transmitting.

The bot's submission is exactly `h + 1` lines:

```
<row 0>
<row 1>
...
<row h-1>
END
```

Each row is a string of exactly `w` cells, where each cell is written as `[<id>]`:

- `<id>` is a non-negative integer in decimal: one or more ASCII digits `0`–`9`, with no leading zeros except for the literal `0` itself, no sign, no whitespace, no other characters. `[0]`, `[1]`, `[2]`, `[42]`, `[150]` are valid; `[01]`, `[+0]`, `[ 0 ]`, `[0x1]`, `[1.0]`, `[a]`, `[]` are all malformed.
- Cells are concatenated with no separator between them — no spaces, no tabs, no commas. A row of width `w = 4` covered by a single piece labelled `7` is the literal 12-byte string `[7][7][7][7]`.
- Lines have no leading or trailing whitespace (no spaces, tabs, or other ASCII control characters); the only allowed terminator is a single `\n`.

Row 0 is the **top** row of the rectangle; row `h-1` is the bottom. Within a row, the leftmost cell is column 0 and the rightmost is column `w-1`.

After the `END` line, the server replies with one of:

```
OK <inventory>
```

or

```
INVALID <reason>
```

`<inventory>` is the count of distinct free-hexomino shapes in the bot's tiling. `<reason>` is a closed-list machine-readable token (see §6). After `OK` or `INVALID`, the server sends:

```
END_ROUND <n>
```

The bot then waits for the next `ROUND` line. After all 10 rounds, the server sends:

```
TOURNAMENT_END
```

Stay connected for the duration of the tournament; do not close your socket until you receive `TOURNAMENT_END` or the server closes the connection.

## 6. Validation

The server validates the submission in this order. The first failure determines `INVALID <reason>`:

| Trigger | INVALID reason |
|---|---|
| Submission did not arrive in full within 30 s | `timeout` |
| A row line doesn't parse as exactly `w` `[<int>]` tokens with no separators or whitespace | `malformed_row_<r>` (`r` is 0-indexed) |
| Wrong number of rows (not exactly `h` rows of cells before `END`, or the line after row `h-1` is not literally `END`) | `malformed_rows` |
| Some `<id>`'s cells do not total 6 | `wrong_size_<id>_<count>` |
| Some `<id>`'s cells don't form a single 4-neighbour-connected component (i.e. the same id is used in two or more disjoint regions of the grid) | `duplicate_id_<id>` |
| A region (6 connected cells under that id) doesn't match any of the 35 free hexominoes after rotation/reflection | `not_a_hexomino_<id>` |

If all rows parse and every region is exactly one valid free hexomino, the submission is `OK <inventory>`.

**Coverage.** The submission must cover *every* cell of the rectangle. There is no notion of leaving a cell unclaimed: every cell in every row must be inside some `[<id>]` token.

**Globally unique ids.** Each `<id>` in the submission corresponds to exactly one piece-instance — i.e., a single 4-neighbour-connected 6-cell region. Reusing an id in two disjoint regions (whether the regions are the same shape or different shapes) triggers `duplicate_id_<id>`. (Two same-id cells at opposite ends of *one* connected hexomino are fine; that is normal — they're part of the same connected region.)

**Inventory and orientation.** Inventory counts *distinct free hexomino shapes*: two regions whose cells are identical up to rotation and/or reflection count as one shape and contribute 1 to the inventory. A submission that uses 5 copies of shape #11 (the 2×3 rectangle) and 1 copy of shape #0 (the 1×6 straight) has inventory 2.

## 7. Catalog of the 35 free hexominoes

Each shape is given as an explicit list of `(row, col)` cells (with `(0, 0)` at the top-left of the shape's bounding box) plus an ASCII diagram for human reference. The bot may use any rotation or reflection of any of these 35 shapes; rotations and reflections of the same shape count as one hexomino for inventory purposes.

The numbering `#0..#34` is for prompt reference only; it has no protocol meaning. The server reports `<inventory>` as a single integer (count of distinct free shapes used), not a list of shape ids.

### Shape #0 (1×6)
cells: (0,0) (0,1) (0,2) (0,3) (0,4) (0,5)
```
######
```

### Shape #1 (2×5)
cells: (0,0) (0,1) (0,2) (0,3) (0,4) (1,0)
```
#####
#....
```

### Shape #2 (2×5)
cells: (0,0) (0,1) (0,2) (0,3) (0,4) (1,1)
```
#####
.#...
```

### Shape #3 (2×5)
cells: (0,0) (0,1) (0,2) (0,3) (0,4) (1,2)
```
#####
..#..
```

### Shape #4 (2×4)
cells: (0,0) (0,1) (0,2) (0,3) (1,0) (1,1)
```
####
##..
```

### Shape #5 (2×4)
cells: (0,0) (0,1) (0,2) (0,3) (1,0) (1,2)
```
####
#.#.
```

### Shape #6 (2×4)
cells: (0,0) (0,1) (0,2) (0,3) (1,0) (1,3)
```
####
#..#
```

### Shape #7 (3×4)
cells: (0,0) (0,1) (0,2) (0,3) (1,0) (2,0)
```
####
#...
#...
```

### Shape #8 (2×4)
cells: (0,0) (0,1) (0,2) (0,3) (1,1) (1,2)
```
####
.##.
```

### Shape #9 (3×4)
cells: (0,0) (0,1) (0,2) (0,3) (1,1) (2,1)
```
####
.#..
.#..
```

### Shape #10 (2×5)
cells: (0,0) (0,1) (0,2) (0,3) (1,3) (1,4)
```
####.
...##
```

### Shape #11 (2×3)
cells: (0,0) (0,1) (0,2) (1,0) (1,1) (1,2)
```
###
###
```

### Shape #12 (3×3)
cells: (0,0) (0,1) (0,2) (1,0) (1,1) (2,0)
```
###
##.
#..
```

### Shape #13 (3×3)
cells: (0,0) (0,1) (0,2) (1,0) (1,1) (2,1)
```
###
##.
.#.
```

### Shape #14 (2×4)
cells: (0,0) (0,1) (0,2) (1,0) (1,2) (1,3)
```
###.
#.##
```

### Shape #15 (3×3)
cells: (0,0) (0,1) (0,2) (1,0) (1,2) (2,0)
```
###
#.#
#..
```

### Shape #16 (2×4)
cells: (0,0) (0,1) (0,2) (1,1) (1,2) (1,3)
```
###.
.###
```

### Shape #17 (3×3)
cells: (0,0) (0,1) (0,2) (1,1) (2,0) (2,1)
```
###
.#.
##.
```

### Shape #18 (4×3)
cells: (0,0) (0,1) (0,2) (1,1) (2,1) (3,1)
```
###
.#.
.#.
.#.
```

### Shape #19 (2×5)
cells: (0,0) (0,1) (0,2) (1,2) (1,3) (1,4)
```
###..
..###
```

### Shape #20 (3×4)
cells: (0,0) (0,1) (0,2) (1,2) (1,3) (2,2)
```
###.
..##
..#.
```

### Shape #21 (3×4)
cells: (0,0) (0,1) (0,2) (1,2) (1,3) (2,3)
```
###.
..##
...#
```

### Shape #22 (3×4)
cells: (0,0) (0,1) (0,2) (1,2) (2,2) (2,3)
```
###.
..#.
..##
```

### Shape #23 (3×3)
cells: (0,0) (0,1) (1,0) (1,1) (1,2) (2,1)
```
##.
###
.#.
```

### Shape #24 (3×3)
cells: (0,0) (0,1) (1,0) (1,1) (1,2) (2,2)
```
##.
###
..#
```

### Shape #25 (3×4)
cells: (0,0) (0,1) (1,1) (1,2) (1,3) (2,1)
```
##..
.###
.#..
```

### Shape #26 (3×4)
cells: (0,0) (0,1) (1,1) (1,2) (1,3) (2,2)
```
##..
.###
..#.
```

### Shape #27 (3×4)
cells: (0,0) (0,1) (1,1) (1,2) (1,3) (2,3)
```
##..
.###
...#
```

### Shape #28 (3×3)
cells: (0,0) (0,1) (1,1) (1,2) (2,0) (2,1)
```
##.
.##
##.
```

### Shape #29 (4×3)
cells: (0,0) (0,1) (1,1) (1,2) (2,1) (3,1)
```
##.
.##
.#.
.#.
```

### Shape #30 (3×4)
cells: (0,0) (0,1) (1,1) (1,2) (2,2) (2,3)
```
##..
.##.
..##
```

### Shape #31 (4×3)
cells: (0,0) (0,1) (1,1) (2,1) (2,2) (3,1)
```
##.
.#.
.##
.#.
```

### Shape #32 (4×3)
cells: (0,0) (0,1) (1,1) (2,1) (3,1) (3,2)
```
##.
.#.
.#.
.##
```

### Shape #33 (3×4)
cells: (0,1) (1,0) (1,1) (1,2) (1,3) (2,1)
```
.#..
####
.#..
```

### Shape #34 (3×4)
cells: (0,1) (1,0) (1,1) (1,2) (1,3) (2,2)
```
.#..
####
..#.
```

## 8. Constraints

- One TCP connection per bot, opened once at startup and held open until `TOURNAMENT_END` or socket close.
- Standard library only.
- Bot identifier from `BOTNAME` env var (see §4).
- Per-round wall-clock budget 30 s.
- Tournament structure is 10 rounds, monotonically growing area, fixed by the server at startup.
- Do not set socket read timeouts; idle reads should block.

## 9. Sample wire transcript

Illustrative — round 1, showing `alpha_bot`'s point of view. The 6×6 rectangle has area 36 = 6 pieces (k = w·h/6 = 6), so the submission uses exactly 6 distinct ids, each appearing 6 times in one connected region.

```
>> alpha_bot
<< ROUND 1 6 6
>> [0][0][1][1][2][2]
>> [0][0][1][1][2][2]
>> [0][0][1][1][2][2]
>> [3][3][4][4][5][5]
>> [3][3][4][4][5][5]
>> [3][3][4][4][5][5]
>> END
<< OK 1
<< END_ROUND 1
<< ROUND 2 ...
```

Walk-through:

- **Connect.** First line sent is the bot's `BOTNAME`.
- **ROUND header.** `ROUND 1 6 6` says round 1 is a 6×6 rectangle (`w=6`, `h=6`, area 36, `k=6` pieces).
- **Submission.** Bot sends `h=6` rows + the literal line `END`. Each row is exactly `w=6` `[<id>]` tokens concatenated with no separator. Ids `0..5` each form one 3-row × 2-col region — that is, six instances of shape #11 (the 2×3 rectangle in vertical orientation).
- **Server response.** `OK 1` — every region is the same shape (#11) up to rotation, so the inventory is 1. *Inventory 1 is the minimum possible and yields no medal*; a competing bot whose tiling uses 4 distinct shapes scores `OK 4` and ranks above this submission.
- **End of round.** `END_ROUND 1` lets the bot know to wait for the next `ROUND` line.

## 10. Notes

- Track your own state if useful; the server announces nothing between `END_ROUND` and the next `ROUND`.
- A round's `INVALID` only forfeits points for that round. The bot remains connected and is expected to handle the next `ROUND` normally.
- The arrow-style separators of other AICC challenges do not apply here; submissions are pure rectangular grids of bracketed ids.
- `[<id>]` ids are decimal integers. `[007]` is invalid (leading zeros disallowed except `[0]` itself); `[+0]`, `[ 0 ]`, `[0x1]`, `[1.0]` are all invalid.
- Coordinates in `<reason>` tokens (e.g. `malformed_row_<r>`) use the same row indexing as the submission: row 0 is the top.
