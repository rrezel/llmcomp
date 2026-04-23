# AI coding contest day 9: Towers of Annoy. Gemini ran the table.

The ninth challenge is an adversarial variant of the Towers of Hanoi. One bot plays Hero and tries to move all `m` disks from tower 0 to tower `n-1`; the other plays Villain. After every hero move, the villain *must* move that same disk to an adjacent tower (or pass if it can't). The hero has a tight budget of `2^m + 1` moves — barely more than the optimal Hanoi solution of `2^m − 1` — so almost any wasted move is fatal. Round-robin tournament with penalty-shootout matchups: each matchup is up to 5 rounds (+ sudden death), each round is 2 simultaneous games with hero and villain roles swapped.

Round sizes grow over the matchup: `(n, m)` of `(4, 3)`, `(5, 4)`, `(7, 5)`, `(9, 6)`, `(12, 7)` — budgets 9, 17, 33, 65, 129.

Two bots never connected: Claude (Opus 4.7) and MiMo (V2-Pro) both got stuck in runaway chain-of-thought loops and produced no code. Six bots competed: 15 matchups, 136 games played.

## The results

| Bot | Won | Lost | Tied | Pts |
|---|---|---|---|---|
| **Gemini (Pro 3.1)** | 5 | 0 | 0 | **15** |
| **Kimi (K2.6)** | 3 | 1 | 1 | **10** |
| **Grok (Expert 4.2)** | 3 | 1 | 1 | **10** |
| **ChatGPT (GPT 5.3)** | 1 | 3 | 1 | **4** |
| **Nemotron (3 Super)** | 0 | 3 | 2 | **2** |
| **GLM (5.1)** | 0 | 4 | 1 | **1** |
| **Claude (Opus 4.7)** | — | — | — | **DNF** |
| **MiMo (V2-Pro)** | — | — | — | **DNF** |

Across the 136 games, the hero won 36 (26%) and the villain won 100 (74%). Most of those "hero wins" were *forfeit* wins against bots that never submitted a move; only **Gemini ever actually solved the adversarial Hanoi on the board**, winning 6 games by reaching the goal state within budget against functioning opponents.

## Gemini: the only one that played the game

Gemini's 283-line bot is the only implementation that actually searches the adversarial game tree. Minimax with alpha-beta pruning, iterative deepening within a 1.8s timeout, weighted disk-position heuristic (exponential weights + a `+10000` bonus for disks "locked" on the goal tower and `-50` for blockers), and path-set cycle detection so the search doesn't loop forever on repeated positions. Villain's narrow move set is explicitly modeled as a constrained branch, rather than approximated.

Result: **5 matchups, 5 wins, 0 losses**. As hero, Gemini won 15 of 17 games. As villain, Gemini won 17 of 17 — a 100% block rate. Across the whole tournament, it passed (i.e., had no legal villain move to force) only 29 times — the lowest of any villain — meaning it usually had a choice and picked the one that hurt the hero most.

The margin against the other "real" bots was stark: Gemini beat Kimi 7-1 and Grok 7-1, each conceding only one game, and beat GPT 6-0. No one else even threatened it.

## Kimi and Grok: statistically identical 1-ply greedy

Kimi (K2.6, 334 lines) and Grok (Expert 4.2, 228 lines) implement the same core idea with different code: on each turn, enumerate legal moves, simulate the opponent's best response one ply ahead, and pick the move with the best worst-case evaluation. Kimi adds a large bonus (`+5000`) for positions where the villain is forced to pass; Grok uses a narrower distance/burying heuristic.

Their records came out *exactly* identical — 3 wins, 1 loss, 1 draw, 10 points, 39% hero win rate, 87% villain win rate, and 11 real villain wins each. They drew each other 10-10 and each lost only to Gemini. The 1-ply lookahead is enough to beat GPT/Nemo/GLM but not enough to solve the actual Hanoi puzzle: **neither bot won a single hero game against a functioning villain**. All their hero "wins" were forfeits against GPT, Nemo, and GLM.

Kimi passed 68 times as villain; Grok passed 81. Against Gemini, both were regularly forced into passes that gave the hero free moves. A 1-ply bot can't set up the multi-move villain-traps that the heuristic would need to prevent this.

## Three different ways to forfeit everything

**Nemotron (3 Super, 346 lines)** defines a full `make_move()` method with hero and villain strategies — but the main `run()` loop reads server messages and *never calls it*. The bot updates its internal state on every `YOURTURN`, `STATE`, `LAST` message and then loops back to `readline` without ever sending a response. Result: **29 hero forfeits, 9 villain forfeits, zero moves sent in the entire tournament**. A one-line `self.sock.send(...)` inside the `YOURTURN` handler would have let the bot compete.

**GLM (5.1, 218 lines)** crashes on the very first server message. Its handler reads the `ROUND` command and tries `self.n = int(parts[2]); self.m = int(parts[3])` — but `ROUND {n}` only has two parts. `IndexError`, process dies. GLM's 1 tournament point came from its draw with Nemo: both bots were non-responsive, so every round of that matchup split 1-1 on mutual forfeits for 20 rounds of sudden death until the 10-round cap kicked in.

**ChatGPT (GPT 5.3, 222 lines)** has a different bug: `elif line.startswith("MATCHUP"): break` exits the main loop on *any* `MATCHUP` message — which means GPT disconnects after its very first matchup and forfeits the remaining four. GPT's 4 tournament points are entirely from that first matchup (a 6-0 forfeit-win against GLM) plus one draw with Nemo (again: two broken bots, 10-10 mutual forfeits). GPT's actual strategy code never gets tested.

## Claude and MiMo: no code at all

Claude (Opus 4.7) and MiMo (V2-Pro) both got stuck in runaway chain-of-thought loops on the prompt and produced no code — their `claude.py` and `mimo.py` files remained empty. A 2-player adversarial Hanoi with villain constraints and role swapping is evidently enough to push some reasoning models into an infinite analysis spiral. These are the same two models that finished 1st and 3rd on Day 8 (Laden Knight's Tour) a week earlier; failure here was not about capability but about a specific failure mode of extended deliberation.

## The verdict

Gemini's dominance is the story: **it's the only bot that actually implemented adversarial search**, and against a field where three of the six competitors couldn't even respond to the server correctly, that was the entire contest. Kimi and Grok's tie at 2nd is the second story — two independently-written 1-ply greedy bots with identical outcomes, split only from Gemini by one critical missing layer of lookahead.

The gap between Gemini and everyone else was not a matter of heuristic tuning or evaluation subtlety — it was about whether the bot even attempted to model the opponent. A minimax-with-alpha-beta template is a 150-line problem; producing one under time pressure is apparently still a model-differentiating challenge. And when two top models (Claude and MiMo) can't produce any code at all, the bar for "actually plays the game" is low enough that Gemini's minimax becomes unbeatable by default.

---

*Model versions for this challenge: Gemini Pro 3.1, Kimi K2.6, Grok Expert 4.2, ChatGPT GPT 5.3, Nemotron 3 Super, GLM 5.1. Claude Opus 4.7 and MiMo-V2-Pro were entered but failed to produce code and did not connect. Board configurations grew from 4×3 (9 hero moves) up to 12×7 (129 hero moves). All bots connected to `localhost:7474` simultaneously; no bot saw the others' code or scores between rounds. Server code, prompt, and generated clients at [github.com/rrezel/llmcomp](https://github.com/rrezel/llmcomp).*
