# LLM Comparison (`llmcomp`)

A repository for evaluating AI frontier models on simple programming tasks to see how well they perform in practice.

## Overview

This project aims to benchmark various Large Language Models (LLMs) by giving them specific, well-defined programming challenges. The goal is to see if they can produce valid, working, and correct code for tasks that require a bit more than just basic syntax knowledge.

## Tests

### 1. Noisy Soviet Postcodes (`noisy_numbers/`)

**Task:** Write a Python 3.10 client that reads six-digit Soviet postal codes from noisy PPM images sent over TCP. Digits are drawn on a 52-dot grid. Images have 5% pixel noise with progressive scaling (±0–10%) and rotation (±0–10°). 100 rounds. Standard library only.

*This is a rerun of the original Day 1 challenge ("sovietpost"), where every model scored zero. In that version, bots were given reference images of the digit glyphs but no structured data — every model invented wrong digit templates because LLMs cannot do spatial reasoning on pixel data. For the rerun, the prompt provides all 52 dot coordinates and stroke sequences as text.*

**Results:**
- **Grok (Expert 4.2):** 8 points (1st). Used dot coordinates to probe the image directly with required-vs-forbidden stroke scoring. Many near-misses with 5/6 digits correct.
- **MiMo:** 0 points. Pipeline ran but cell segmentation was misaligned.
- **Claude (Opus 4.6):** 0 points. Correct 7-segment digit model, but erosion destroyed all image content. Sent `000000` every round.
- **Gemini (Pro 3.1):** 0 points. Built templates from provided stroke data, but matching always picked digit 8 (most ink). Sent `888888` every round.
- **ChatGPT (GPT 5.3):** 0 points. Eliminated round 1 (I/O timeout).
- **Nemotron:** 0 points. Eliminated round 1 (timeout).

For more details on this test, see the [article](noisy_numbers/article.md) and the [prompt](noisy_numbers/prompt.md).

### 2. Word Racer Champion (`wordracerchampion/`)

**Task:** Write a Python 3.10 client that connects to a TCP server, receives a 15×15 letter grid, and races to find and submit valid dictionary words traced adjacently on the grid. Scoring: `letters − 6`. Five bots compete simultaneously in a ten-second round, five rounds total.

**Results:**
- **Claude (Opus 4.6):** Scored +1,251 cumulative, winning all five rounds. Only bot to filter for profitable word lengths (7+), with a pipelined three-thread architecture.
- **MiMo:** Scored +78 cumulative. Array-based trie with length-sorted output — correct strategy, but batch-then-submit was too slow to beat Claude's streaming pipeline.
- **Gemini (Pro 3.1):** Scored 0 in all five rounds. Too slow to claim any words before Claude.
- **Grok (Expert 4.2):** Scored −2,431 cumulative. Submitted all words including unprofitable short ones, throttled by synchronous I/O.
- **ChatGPT (GPT 5.3):** Scored −118,969 cumulative. Same short-word mistake as Grok but with async I/O, flooding the server with thousands of negative-scoring submissions per round.

For more details on this test, see the [article](wordracerchampion/article.md) and the [prompt](wordracerchampion/prompt.md).

### 3. Growing Word Ladder (`growingwordladder/`)

**Task:** Write a Python 3.10 client for a multi-round word ladder tournament. Each round, the server sends a start word and a goal word. Bots must find a path between them — each step changing, adding, or removing exactly one letter — with all intermediate words in a million-word dictionary. First valid submission wins the round. Bots that fail to submit within 5 seconds of the winner are eliminated. 100 rounds.

**Results:**
- **Claude (Opus 4.6):** Won all 100 rounds (avg 192ms). Bidirectional BFS with neighbor caching, frontier size heuristic, and frozenset dictionary.
- **Grok (Expert 4.2):** Survived all 100 rounds, won 0 (avg 269ms). Correct algorithm but no caching.
- **Gemini (Pro 3.1):** Survived all 100 rounds, won 0 (avg 271ms). Correct algorithm but no caching.
- **ChatGPT (GPT 5.3):** Survived all 100 rounds, won 0 (avg 274ms). Correct algorithm but no caching.

For more details on this test, see the [article](growingwordladder/article.md) and the [prompt](growingwordladder/prompt.md).

### 4. The Amazing Teleportal Maze (`amazed/`)

**Task:** Write a Python 3.10 client to navigate a 2D ASCII maze with teleportals under foggy conditions. No map — bots must explore, remember what they've seen, and find the exit in as few steps as possible. 100 rounds of increasing maze size. Exceeding 500 moves or timing out = elimination.

**Results:**
- **Claude (Opus 4.6):** Won 80 of 100 rounds. BFS exploration biased toward exit corner, immediate portal link resolution from TELEPORT coordinates.
- **Grok (Expert 4.2):** Won 20 of 100 rounds. BFS exploration without directional bias, portal detection by letter matching only.
- **Gemini (Pro 3.1):** Eliminated round 5. Protocol desynchronization on larger mazes.
- **ChatGPT (GPT 5.3):** Eliminated round 8. Move timeout on larger mazes.
- **MiMo:** Eliminated round 1. `.strip()` destroyed spaces in the 5×5 view.

For more details on this test, see the [article](amazed/article.md) and the [prompt](amazed/prompt.md).

### 5. The Subway Speedrun (`subwayspeedrun/`)

**Task:** Write a Python 3.10 client that solves subway routing optimization: given a network with schedules, transfer hubs, and variable travel times, find the fastest route visiting every station. 10 rounds of increasing difficulty (3-11 lines, 12-119 stations). NP-hard combinatorial optimization with real timetable constraints.

**Results:**
- **Claude (Opus 4.6):** 22 points (1st). Won 8 of 10 rounds with Dijkstra + permutation search + timetable simulation. Failed on 8+ line networks (permutation explosion).
- **Gemini (Pro 3.1):** 6 points (2nd). Won rounds 1-2 with the fastest times, then crashed permanently due to `heapq` tuple comparison bug.
- **Nemotron:** 6 points (3rd). Dijkstra with schedule awareness, but couldn't scale past 55 stations.
- **Grok (Expert 4.2):** 4 points (4th). Instant DFS with no schedule modeling. Produced invalid routes on larger networks.
- **ChatGPT (GPT 5.3):** 0 points. Beam search crashed every round — same `heapq` tuple comparison bug as Gemini.
- **MiMo:** 0 points. Hardcoded wrong transfer stations in every route.

For more details on this test, see the [article](subwayspeedrun/article.md) and the [prompt](subwayspeedrun/prompt.md).

## Medal Tally

| Model | Postcodes | Word Racer | Word Ladder | Maze | Subway | Gold | Silver | Bronze |
|---|---|---|---|---|---|---|---|---|
| **Claude (Opus 4.6)** | — | Gold | Gold | Gold | Gold | **4** | 0 | 0 |
| **Grok (Expert 4.2)** | Gold | — | Silver | Silver | — | **1** | **2** | 0 |
| **Gemini (Pro 3.1)** | — | — | Bronze | DQ | Silver | 0 | **1** | **1** |
| **MiMo** | — | Silver | DNP | DQ | DQ | 0 | **1** | 0 |
| **Nemotron** | DQ | DNP | DNP | DNP | Bronze | 0 | 0 | **1** |
| **ChatGPT (GPT 5.3)** | DQ | — | — | DQ | DQ | 0 | 0 | 0 |

*DQ = disqualified (crashed, invalid output, or eliminated early). DNP = did not participate. — = finished but did not medal. Postcodes: Grok scored 8/100, all others scored 0 (no silver/bronze awarded). Subway: Gemini and Nemotron tied on 6 points, but Gemini won 2 rounds vs 0, taking silver.*

