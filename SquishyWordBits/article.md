# AI coding contest day 15: SquishyWordBits. Kimi wins on a single-pass solver.

The fifteenth challenge is a bit-packing puzzle. Letters are encoded as variable-length binary numbers (a=`0`, b=`1`, c=`10`, d=`11`, e=`100`, … z=`11001`), with the encoding length given by the minimum bits needed to represent the letter's 0-indexed alphabet position. A word's encoding is the concatenation of its letters' codes, with no separators between letters. The encoding is *not* prefix-free: `a`'s code `0` is a prefix of `c`'s code `10`, so the same bit substring can correspond to multiple letter sequences.

Each round, the server sends the bot a single bitstream (uniform random `0`/`1` characters, 10,000 to 20,000 bits long). The bot replies with a set of `(word, offset)` pairs: dictionary words plus the bit position in the stream where each word's encoding starts. The set is valid if every word is in the dictionary, every word's encoding equals `bits[offset : offset + len(encoding)]`, and the bit intervals are pairwise disjoint. Each accepted word contributes `letters − 3` to the round score, so 1- and 2-letter words score negative, 3-letter words score zero, and longer words score increasingly. Round scores can be negative.

The format is 10 solo rounds, each with a 30-second wall-clock budget. Per-round ranking → tournament points: 1st = 10, 2nd = 7, 3rd = 5, 4th = 3, 5th = 1, 6th and below = 0. Ties on round score break by earliest submission timestamp at the server. Tournament total = sum of round points.

9 bots competed. **GLM (5.1) is DNF.** Three regeneration attempts each terminated with `finish_reason=length` after the model burned its full reasoning budget without emitting a single output token. By the rule, three ICoTL attempts is the cutoff; GLM never produced a bot file.

## The results

| Rank | Bot | Pts | 1sts | Total score |
|---|---|---|---|---|
| **#1** | **Kimi (K2.6)** | **83** | **8** | 31,915 |
| **#2** | **ChatGPT (GPT 5.5)** | 42 | 1 | 31,915 |
| **#3** | **Claude (Opus 4.7)** | 35 | 0 | 31,915 |
| **#4** | **Grok (Expert 4.20)** | 32 | 1 | 31,915 |
| **#5** | **Gemini (Pro 3.1)** | 30 | 0 | 31,915 |
| **#6** | **MiMo (V2.5-Pro)** | 23 | 0 | 31,915 |
| **#7** | **Nemotron (3 Super)** | 15 | 0 | 31,915 |
| **#8** | **Muse (Spark)** | 0 | 0 | 31,915 |
| **#9** | **DeepSeek (V4-Pro)** | 0 | 0 | 24,030 |
| DNF | GLM (5.1) | — | — | — |

*(1sts is the number of rounds the bot finished 1st in. Total score is the cumulative `letters − 3` summed across the 10 rounds. DNF: did not finish.)*

The dominant feature of the standings: **eight bots posted byte-identical round scores on every single round.** Their per-round score sequence was

```
[2210, 2393, 2612, 2807, 3078, 3271, 3493, 3722, 3958, 4371]
```

Total 31,915 each. DeepSeek alone deviated, scoring about 75% of optimum (`[1688, 1811, 1948, 2143, 2327, 2502, 2620, 2753, 2943, 3295]`, total 24,030). With eight bots tied on score every round, the per-round ranking, and therefore the entire tournament, was decided almost entirely by **submission timestamp**.

## The convergent solver

Every model that produced working code converged on the same algorithm:

1. Build a binary trie of every dictionary word's bit encoding once at startup.
2. For each `ROUND <n> <bits>`, walk the trie from every starting position in the bitstream to enumerate all `(start, end, word, weight)` intervals where the word's encoding ends at `end`.
3. Solve weighted interval scheduling on those intervals to find the maximum-weight set of non-overlapping placements. Since intervals can be sorted by end-position, this is a 1D dynamic program.
4. Emit `WORD <word> <offset>` for each chosen interval, then `END`.

This is the textbook approach. The optimum is unique up to alternative packings of the same total score, and every implementation that ran the DP correctly found it. The 8-way score tie is a direct consequence: when nine bots all use the same algorithm, eight of them get the right answer.

The differentiation across the field reduced to two things: how fast each bot's solver actually runs in Python, and (in DeepSeek's case) a subtle correctness bug in the trie itself.

## Average submission times across the 10 rounds

| Bot | Avg | Min | Max | Points |
|---|---|---|---|---|
| **Kimi** | **0.214 s** | 0.05 | 0.85 | 83 |
| ChatGPT | 1.084 s | 0.05 | 3.41 | 42 |
| Gemini | 1.116 s | 0.57 | 1.83 | 30 |
| Claude | 1.198 s | 0.31 | 2.83 | 35 |
| MiMo | 1.221 s | 0.34 | 2.28 | 23 |
| Grok | 1.280 s | 0.09 | 2.52 | 32 |
| Nemotron | 1.818 s | 0.64 | 4.17 | 15 |
| Muse | 2.396 s | 1.40 | 3.53 | 0 |

The structure: one fast outlier (Kimi, **5× faster** than the next-best on average), one cluster of five bots in the 1.0–1.3 s range, two genuinely slower implementations (Nemotron, Muse), and DeepSeek which would fall into the cluster on speed but never reaches cluster *score*.

Looking at Kimi's per-round times specifically:

```
[0.85, 0.05, 0.05, 0.83, 0.06, 0.06, 0.07, 0.07, 0.05, 0.05]
```

Two outliers (R1 = 0.85 s cold start, R4 = 0.83 s) and **eight rounds in the 50–70 ms range**. The next-best bot's *minimum* round time is 0.05 s (ChatGPT and Grok each had a single fast round), but their averages sit around 1.1–1.3 s. Kimi's win is 5× faster on the round-by-round average and 15–20× faster in steady state.

That kind of speed gap is multiplicative, not additive. It's not a Nagle batching issue or a `setsockopt` decoration. It's the algorithm.

## Kimi: a single-pass DP

Most of the other bots run the trie-and-DP in two phases. First, a scan phase walks the bitstream from every starting position to materialize a list of every word-occurrence interval `(start, end, weight, word)`. Then a separate DP phase runs weighted interval scheduling over that list. On a 20,000-bit stream against a ~340,000-word dictionary, the candidate list can hold hundreds of thousands of entries. Building it dominates per-round runtime.

Kimi merges the two phases into one backward pass:

```python
for p in range(n - 1, -1, -1):
    best_val = best[p + 1]
    best_end = -1
    best_w = ''
    node = 0
    for q in range(p, n):
        if b[q]:
            node = ch1_local[node]
        else:
            node = ch0_local[node]
        if node == -1:
            break
        lw = bl[node]
        if lw >= 4:
            end = q + 1
            val = (lw - 3) + best[end]
            if val > best_val:
                best_val = val
                best_end = end
                best_w = bw[node]
    best[p] = best_val
    choice_end[p] = best_end
    choice_word[p] = best_w
```

For each starting position `p` (working from the end of the bitstream backward), the inner loop walks the trie forward and *immediately* checks whether each terminal node it reaches improves `best[p]`, using `best[end]`, which has already been computed because of the backward iteration order. There is no candidate list. The trie-walk and the DP update happen in one fused loop. Memory is `O(n)` for the dp array. The other bots' solvers allocate `O(n × dict_density)` candidate lists and iterate them twice.

Three other implementation choices fall out of that:

- **Length-≥4 cutoff at trie-construction time.** Kimi excludes any dictionary word with fewer than 4 letters before inserting it into the trie (`if not word or len(word) < 4: continue`). Words shorter than 4 letters score zero or negative under the `letters − 3` formula. There is no game-theoretic reason to include them. Adding a short word to a packing only ever takes bit-space away from longer words. Other bots include all 370K words and rely on the DP to ignore zero-and-negative-weight intervals; that's correct, but the inner trie-walk visits more terminal nodes per scan position than it needs to.
- **Bit-array conversion at the start of each round.** `bit_arr = [0 if c == '0' else 1 for c in bits]` runs once on the bitstream. Inside the inner loop, `if b[q]:` is an int truthiness check; the alternative (`if bitstream[q] == '1':` with a string) is materially slower in CPython because each access allocates a single-character string and runs a comparison.
- **Local variable shadowing of the trie arrays.** `ch0_local = ch0; ch1_local = ch1; bl = best_len; bw = best_word; b = bit_arr` rebinds the function-scope names so the inner loop reads them from local-variable slots rather than chasing closures or attribute lookups. This is a pure CPython optimization, but in a 5-million-iteration loop on a 20K-bit stream, it matters.

With those four choices, Kimi's per-round time stays at 50–70 ms on 8 of 10 rounds. The next-fastest *steady-state* bot's per-round time is 6–10× higher.

## The medium cluster: ChatGPT, Gemini, Claude, MiMo, Grok

Five bots in the 1.0–1.3 s range, all running the standard two-phase solver. Within the cluster the per-round ordering is largely a function of inner-loop tightness and per-round Python variance: GC pauses, allocator behavior, byte-code warmup. Across 10 rounds the variance integrates out into a points spread of 23–42:

- **ChatGPT (avg 1.08 s)**: a class-based recursive trie with a `score` field per node. Single-best round of 0.05 s won round 4; otherwise consistent 0.5–1.4 s.
- **Claude (avg 1.20 s)**: explicit `candidates_by_end` list pre-allocated for the bitstream length, plus dp/take arrays. Three top-3 placements but no firsts; banks 35 points on consistency.
- **Grok (avg 1.28 s)**: 0.09 s round-1 first place accounts for 10 of its 32 points; the rest tail up to 2.5 s.
- **Gemini (avg 1.12 s)**: array-based trie much like Kimi's, but two-phase scan + DP. Most consistent round-to-round (range 0.57–1.83) with no fast outlier round.
- **MiMo (avg 1.22 s)**: trie + DP without the length cutoff. The slowest of the cluster on average.

Five bots, all writing the same answer to the same socket. Separated by inner-loop micro-optimizations and by which one's GC happened to fire on which round.

## The slow tail: Nemotron and Muse

Nemotron's average 1.82 s and Muse's 2.40 s aren't unlucky; they're consistently slower than the cluster. Muse's *minimum* round time (1.40 s) is worse than the cluster's *average*, and Muse never ranks higher than 6th in any round. Both score the optimum on every round, but neither ever gets close enough to the front of the line to claim a top-5 placement. Muse's 0 tournament points despite 31,915 total score is the cleanest illustration of the day's central fact: in a tied-score field, you need to be inside the top 5 by submission time to score anything.

The slowness traces to per-round overhead in trie traversal. Both bots run the scan in pure Python without the inner-loop micro-optimizations the cluster uses. At 20,000 bits and ~340,000 trie entries, those small per-iteration costs accumulate.

## DeepSeek: the trie-overwrite bug

DeepSeek implements the same trie + interval scheduling, with a length-≥3 cutoff. Its solver runs the standard DP. But its per-round score is 75% of optimum, and the gap is consistent: every round it shorts the rest of the field by 500–1100 score-points.

The bug is in the trie. DeepSeek stores a single `word` per node:

```python
trie = [(0, 0, None, 0)]  # (child0, child1, word, weight)
```

When a second dictionary word's encoding ends at the same trie node, the second insertion overwrites the first. (This happens because the encoding is not prefix-free: for example, `c` and `ba` both encode to `10`, so any word that begins with `c` shares a trie node with words that begin with `ba`.) Whichever word DeepSeek inserts *last* at that node is the only one its solver can submit. The DP then has fewer candidate intervals to choose from, and the optimal packing it finds is a packing over an impoverished set. The structural ceiling lands right around 75% of the true optimum, which matches the scores observed on every round.

This is a real algorithmic difference, not a speed difference. It earns DeepSeek a unique 9th place. On a field where everyone else converges on the maximum, DeepSeek alone is at a lower number.

## The verdict

The challenge surfaces three independent signals in the same standings:

- **#1 Kimi**: a real solver-engineering win. Single-pass trie+DP merge, length-≥4 cutoff, bit-array conversion, local-variable shadowing. Average 0.21 s per round, 50–70 ms on 8 of 10 rounds. Five times faster than the medium cluster on average.
- **#2–#6 (the medium cluster)**: five bots running the standard two-phase solver. Their relative ordering is largely a function of inner-loop tightness and per-round variance.
- **#7–#8 (Nemotron, Muse)**: same algorithm, slower implementations. No structural problems, just looser code.
- **#9 DeepSeek**: the only bot whose trie misses words on encoding collisions. A correctness bug worth ~25% of optimum on every round.

The DNF is informative on its own: GLM 5.1 burned through its reasoning-token budget three times in a row without emitting a single Python token. The model knows it's being asked to write a bot, walks the problem far enough to fill the budget thinking, and never starts writing.

When eight of nine frontier models converge on the same algorithm and the standings are decided by who wrote the tightest hot loop, the title isn't really evidence about reasoning. It's evidence about implementation discipline. Kimi shipped the smallest, fastest correct bot in the field, and won.

---

*Model versions for this challenge: Claude Opus 4.7, Gemini Pro 3.1, Grok Expert 4.20, ChatGPT GPT 5.5, MiMo V2.5-Pro, Nemotron 3 Super, GLM 5.1 (DNF, ICoTL × 3 in generation), Kimi K2.6, Meta Muse Spark, DeepSeek V4-Pro. 9 bots played 10 rounds each on bitstreams of 10,000 to 20,000 uniform-random bits. 30-second wall-clock per bot per round. Bots were generated by sending `prompt.md` to each OpenRouter model in a single chat completion request (no `max_tokens` cap, `temperature=0.2`); five model bots were authored via direct chat. Server code, prompt, generated bots, and the per-round submission lists are at [github.com/rayonnant-ai/aicc](https://github.com/rayonnant-ai/aicc).*
