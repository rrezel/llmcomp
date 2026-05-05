# SquishyWordBits — Tournament Spec

## Task

**Write a complete, self-contained Python 3.10 bot client that competes in this tournament.** The bot connects to the tournament server at `localhost:7474`, plays every round it is dealt, and tries to score as many tournament points as possible. Use only the Python standard library. Do not leave placeholder strategies, demo stubs, or "STRATEGY GOES HERE" comments — the bot must implement a full strategy that produces submissions for each round.

You may add your model name as a comment at the top of the file (e.g. `# bot author: <model name and version>`).

## 1. The puzzle

Each round, the server sends the bot a single **bitstream**: a string of `0` and `1` characters with no other separators. The bot must respond with a set of dictionary words whose bit encodings appear at non-overlapping positions in the bitstream.

### Letter encoding

Each lowercase letter is encoded as the binary representation of its 0-indexed alphabet position, written with the **minimum** number of bits and no leading zeros (with the single exception that `a` = `0`). Concretely, letter at 0-indexed position `i` encodes to `format(i, "b")`. Bit-lengths by letter:

- 1 bit: `a` = `0`, `b` = `1`
- 2 bits: `c` = `10`, `d` = `11`
- 3 bits: `e` = `100`, `f` = `101`, `g` = `110`, `h` = `111`
- 4 bits: `i` = `1000`, `j` = `1001`, `k` = `1010`, `l` = `1011`, `m` = `1100`, `n` = `1101`, `o` = `1110`, `p` = `1111`
- 5 bits: `q` = `10000`, `r` = `10001`, `s` = `10010`, `t` = `10011`, `u` = `10100`, `v` = `10101`, `w` = `10110`, `x` = `10111`, `y` = `11000`, `z` = `11001`

The encoding is **not prefix-free**: `a`'s code `0` is a prefix of `c`'s code `10`, and `b`'s code `1` is a prefix of every multi-bit code. So the same bit substring can correspond to multiple letter sequences.

### Word encoding

A word's bit encoding is the **concatenation** of its letters' codes, in order, with **no separators**. Example: `cat` encodes as `code(c) || code(a) || code(t)` = `10` || `0` || `10011` = `10010011` (8 bits).

A word `w` "occurs at offset `p`" in the bitstream if `bitstream[p : p + len(encoding(w))]` equals the word's bit encoding.

### Per-round score

The bot submits a set of `(word, offset)` pairs. The set is valid if:

- Every word is a lowercase English word in the dictionary (the bot submits in uppercase; the server lowercases to look up).
- Every word's bit encoding occurs at the claimed offset in the round's bitstream.
- The bit intervals `[offset, offset + len(encoding(word)))` are **pairwise disjoint**: no two submitted words may overlap any bit position.

Each accepted word contributes `letters − 3` to the round score, where `letters` is the word's letter count. So:

- A 3-letter word contributes 0.
- A 4-letter word contributes 1.
- A 10-letter word contributes 7.
- A 1-letter or 2-letter word contributes a *negative* amount (−2 or −1).

The round's score is the sum of contributions across all accepted words. Round scores can be negative if the bot submits more short words than long ones.

### Per-round ranking

| Rank by round score | Points |
|---|---|
| 1st | 10 |
| 2nd | 7 |
| 3rd | 5 |
| 4th | 3 |
| 5th | 1 |
| 6th and below | 0 |

Ties on round score are broken by **earliest submission timestamp** at the server (earlier wins the higher rank; later bots drop down). Invalid submissions (malformed lines, non-dictionary words, overlap, encoding mismatch, timeout) score 0 round-score and 0 tournament points for that round, regardless of timing.

## 2. Tournament structure

The tournament is **10 rounds** played serially. Every registered bot plays every round. Bitstream lengths grow monotonically across rounds; later rounds have more bits and admit more (and longer) words. Tournament total = sum of round points across the 10 rounds.

**Tournament standings:** total tournament points across all 10 rounds, descending. Tiebreak by total wins (1st-place finishes), then by total cumulative round score across rounds.

## 3. Wire framing

- All messages in both directions are **ASCII text**, lines terminated by a single `\n` (LF, byte `0x0a`). **CRLF is invalid.**
- Every server message is a complete line ending in `\n`. Every bot message must be a complete line ending in `\n`.
- The server reads bot input with line buffering. You must flush after each line you send (e.g. `sock.sendall(line.encode())`).
- Lines have no leading or trailing whitespace beyond the single terminating `\n`.

## 4. Connection handshake

1. **Read your bot name from the `BOTNAME` environment variable.** Do not hardcode it; do not derive it from `sys.argv`; do not generate it. The exact bytes in `os.environ['BOTNAME']` (after stripping any trailing `\n`) are your bot identifier — use them verbatim. If `BOTNAME` is absent or empty, the bot is misconfigured and should not attempt to connect.
2. Open a TCP connection to `localhost:7474`.
3. **Send the BOTNAME value as the first line**, terminated by a single `\n`. The server reads exactly one line as your bot identifier. The value must be 1–32 characters from the set `[A-Za-z0-9_-]`. A value violating these rules causes the server to immediately close the connection.
4. Wait for a `ROUND` line announcing the first round. Until you receive `ROUND`, do not send anything.

## 5. Round protocol

The server announces each round to all registered bots simultaneously:

```
ROUND <n> <bits>
```

- `<n>` is the 1-indexed round number, `1..10`.
- `<bits>` is the bitstream — a contiguous string of `0` and `1` characters, length between 200 and 20,000. There are no other characters between `ROUND <n> ` and the closing `\n`. The bitstream length is `len(bits)`.

The bot has **30 seconds wall-clock** from the instant the server sends `ROUND` to the instant the server has read the bot's complete submission. The clock counts the bot's compute time and any time spent transmitting.

The bot's submission is one or more `WORD` lines followed by a single `END` line:

```
WORD <word> <offset>
WORD <word> <offset>
...
WORD <word> <offset>
END
```

- `<word>` is one or more uppercase ASCII letters `A`–`Z`.
- `<offset>` is a non-negative integer in decimal (no leading zeros except `0`, no sign), giving the bit position in the round's bitstream where the word's encoding starts.
- The bot may submit zero `WORD` lines (just `END` alone). In that case the round score is 0.
- The bot must close the submission with the literal line `END`. The server reads lines until it sees `END` or the deadline expires.

After the `END` line (or after the 30 s deadline), the server replies with one of:

```
OK <round_score> <word_count>
```

or

```
INVALID <reason>
```

`<round_score>` is the sum of `letters - 3` across all accepted words; `<word_count>` is the number of accepted words. `<reason>` is a closed-list machine-readable token (see §6). After `OK` or `INVALID`, the server sends:

```
END_ROUND <n>
```

The bot then waits for the next `ROUND` line. After all 10 rounds, the server sends:

```
TOURNAMENT_END
```

Stay connected for the duration of the tournament; do not close your socket until you receive `TOURNAMENT_END` or the server closes the connection.

## 6. Validation

The server validates the submission as a unit. The first failure determines `INVALID <reason>`:

| Trigger | INVALID reason |
|---|---|
| The submission did not arrive (no `END` line received) within 30 s | `timeout` |
| Some line before `END` doesn't match `^WORD [A-Z]+ [0-9]+$` (wrong prefix, lowercase, non-letter chars in word, leading zero in offset, leading or trailing whitespace) | `malformed_<i>` (`i` is the 0-indexed line number among the bot's submission lines) |
| Some submitted word's lowercased form isn't in the dictionary | `not_in_dictionary_<i>` |
| Some word's bit encoding doesn't equal `bitstream[offset : offset + len(encoding)]`, or `offset + len(encoding) > len(bitstream)` (i.e., the encoding would run past the end of the bitstream) | `not_in_bitstream_<i>` |
| Two submitted words occupy overlapping bit intervals | `overlap_<i>_<j>` (`i < j`, both 0-indexed) |

If all checks pass, the server replies `OK <round_score> <word_count>`.

## 7. Dictionary

The dictionary is provided to the bot at runtime. The file `dictionary.txt` is present in the bot's working directory at the path `./dictionary.txt`: roughly 370,000 lowercase English words, one per line, A–Z only. The bot can read it directly with `open("dictionary.txt")` (or with an absolute path derived from `__file__` if the bot is launched from a different cwd). The bot does not need to ship its own dictionary or transmit one over the wire.

For validation, the server lowercases the bot's submitted `<word>` (which is uppercase on the wire) and checks membership against the same `dictionary.txt`.

## 8. Constraints

- One TCP connection per bot, opened once at startup and held open until `TOURNAMENT_END` or socket close.
- Standard library only.
- Bot identifier from `BOTNAME` env var (see §4).
- Per-round wall-clock budget 30 s.
- Tournament structure is 10 rounds played serially, fixed by the server at startup.
- Do not set socket read timeouts; idle reads should block.

## 9. Sample wire transcript

Illustrative — one round, showing `alpha_bot`'s point of view.

```
>> alpha_bot
<< ROUND 1 00110100101001110001100100111011101100100111001011
>> WORD STRETCH 5
>> WORD CATS 35
>> END
<< OK 5 2
<< END_ROUND 1
<< ROUND 2 ...
>> END
<< OK 0 0
<< END_ROUND 2
<< ROUND 3 ...
>> WORD ABCDEFGH 0
>> END
<< INVALID not_in_dictionary_0
<< END_ROUND 3
<< ROUND 4 ...
(no submission)
<< INVALID timeout
<< END_ROUND 4
```

Walk-through:

- **Round 1**: bitstream is 50 bits (smaller than the 200-bit minimum, used here for illustration). The encoding of `STRETCH` is the 28-bit string `1001010011100011001001110111`, which equals `bits[5:33]`. The encoding of `CATS` is the 13-bit string `1001001110010`, which equals `bits[35:48]`. Both words are in the dictionary; the intervals `[5, 33)` and `[35, 48)` are disjoint. Round score = `(7 − 3) + (4 − 3)` = `4 + 1` = `5`. Server replies `OK 5 2`.
- **Round 2**: bot submits an empty set (`END` alone, no preceding `WORD` line). Round score = 0. `OK 0 0`.
- **Round 3**: bot submits `WORD ABCDEFGH 0`. The word isn't in the dictionary, so `INVALID not_in_dictionary_0`. The bot scores 0 round-score and 0 tournament points for the round, then proceeds.
- **Round 4**: bot doesn't respond within the deadline. Server emits `INVALID timeout`, then `END_ROUND 4`. Round 4 also scored 0.

A hypothetical mixed submission like `WORD A 0` (1-letter, scores `1 − 3 = −2`) plus `WORD CATS 13` (4-letter, scores `1`) would yield a total of `−1`, illustrating how round scores can go negative when short words dominate.

## 10. Notes

- The bitstream has no canonical letter segmentation; the server only checks that each submitted word's encoded bits match the bits at the claimed offset, not how the rest of the bitstream might be parsed.
- Submitted words need not align to any "natural" letter boundary in any pre-existing parse of the bitstream — there is no such boundary.
- A round's `INVALID` only forfeits points for that round. The bot remains connected and is expected to handle the next `ROUND` normally. The server still sends `END_ROUND <n>` after `INVALID <reason>`.
- If the bot can't or doesn't want to submit any word, send `END` alone (round score 0) or simply not respond (the server emits `INVALID timeout` after 30 s; round still scores 0).
- Submitted words are uppercase A–Z; the server lowercases for dictionary lookup. Hyphens, apostrophes, digits, and any other characters in the word make the line malformed.
- The `<offset>` is a bit position, 0-indexed, into the round's bitstream. Offset 0 is the first bit of the bitstream.
