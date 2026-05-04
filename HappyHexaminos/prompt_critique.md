========================================================================
# Perplexity  (:7824, fact-checking, web sources)  [26.0s]
========================================================================
Ambiguities and gaps in safety, scope, and practicality

- “The bot connects to the tournament server at localhost:7474 …” and expects a specific handshake. What happens if the BOTNAME contains invalid characters or is missing? The spec says use BOTNAME exactly as provided, but doesn’t specify behavior if environment variable is missing or malformed. This could lead to immediate disconnection without a helpful error.

- Round timing: “The bot has 30 seconds wall-clock from the instant the server sends ROUND to the instant the server has read the bot's complete submission.” What if the network latency or OS scheduling causes the bot’s computation to exceed 30 seconds but the submission is still being transmitted? The spec doesn’t define a precise boundary for partial submissions or timeout handling during transmission.

- Round submission format: “The bot’s submission is exactly h + 1 lines.” If a line is too short/long or contains non-bracket content, the server returns malformed_row_<r>. The spec enumerates malformed_row_<r> and other errors, but it does not specify whether the bot can send additional lines after END in such a case. The behavior for mid-round reattempts is unclear.

- Inventory calculation: Inventory is the number of distinct free hexomino shapes used. The spec requires a tiling but does not constrain that some shapes must necessarily be used. However, it does not define a cap on the number of pieces per shape; while inventory minimizes, there is no explicit minimum inventory strategy. This creates ambiguity for evaluators wanting a baseline.

- Tie-breaker workflow: “Earlier wall-clock arrival wins” within a tied inventory. The spec does not specify how to report timing or how to handle network jitter. If two bots submit consecutively within milliseconds, how is order determined? It implies server-provided timestamps, but not how clocks are synchronized.

- Validation order: The server validates in a fixed order. If a submission has multiple violations, the first encountered defines INVALID. This makes it hard to diagnose multiple issues; an implementer might need to guess which error will trigger first in edge cases.

- Hexomino catalog usage: The server validates that each region is one of the 35 free hexominoes. It relies on canonicalization under 8 rotations/reflections. The spec does not expose the canonicalization algorithm, so implementers must rely on their own geometric equivalence, which could yield inconsistencies if there’s any bug.

- Data encoding and ASCII rules: All messages are ASCII with strict line endings. If an implementation uses a library that emits CRLF or adds trailing spaces, the server may reject with malformed_row_<r> or other invalid errors. The spec is precise but imposes a heavy strictness on encodings.

- Concurrency and multiple rounds: The spec says 10 rounds, areas monotonically growing. If a bot fails a round (INVALID), it still must handle subsequent rounds. The protocol does not specify reconnection semantics beyond waiting for the next ROUND after END_ROUND. Implementers must ensure resilience to repeated invalid rounds.

- Resource constraints and performance: The per-round 30-second budget includes all time to compute and transmit. The spec does not specify the maximum memory usage or CPU-limits. A naive tiling algorithm that exhausts CPU could block subsequent rounds if not properly isolated.

- Self-contained strategy requirement: “Do not leave placeholder strategies.” The spec demands a full tiling strategy. It’s easy to create a tiling that uses many shapes; an implementer could exploit a loophole by repeatedly tiling with a fixed subset, but the lack of a verifier for minimality could pressure exploiters.

- Handling of END and ROUND: After END, server replies with OK or INVALID and then END_ROUND <n>, followed by next ROUND. The spec does not specify whether a bot can send additional data after OK/INVALID line (likely not). Implementers must strictly adhere to the exact one-line reply pattern per round.

Notable inconsistencies

- The catalog numbering and the shapes’ canonical forms are described, but it is stated that the server reports inventory as a single integer, not a list. There is no ambiguity here, but it’s easy to misinterpret that multiple shapes might be labeled differently in tilings.

- The “31–35 hexominoes” list uses a fixed catalog in the prompt. The spec ties shapes to inventory only by distinct shapes used, not by labeling, which is consistent but could cause confusion for implementers who try to map to ids.

Underspecified edge cases

- What if w or h is 1 or 2 but still tileable by hexominoes? The constraints allow up to 30; minimum area is 36, but if w=1, h=36 is tileable only in specific cases; the server guarantees tileability, but the spec doesn’t discuss degenerate shapes. Implementers must handle arbitrary valid inputs.

- What if the server’s witness tiling uses all 35 hexominoes in a round; inventory would be 35. The scoring favors low inventories, but the spec doesn’t constrain the maximum inventory or provide guidance on how to avoid high inventories beyond strategy choice.

- If the server misbehaves (malformed END, or END_ROUND out of order), what should the bot do? The spec expects normal operation but doesn’t define error handling for protocol-level faults beyond INVALID.

- Network interruptions: If connection drops mid-round, the spec doesn’t specify retry or reconnection behavior beyond the normal per-round protocol.

- Timeouts: If rounds are longer than expected due to server latency, the 30-second budget still applies. The spec doesn’t define a reconnection or timeout policy for the entire tournament in case of long stalls.

Specific quotes and what’s wrong

- “The bot has 30 seconds wall-clock from the instant the server sends ROUND to the instant the server has read the bot's complete submission” — No guidance on partial submissions, or whether the server will wait for a complete submission after 30s or drop and reattempt, leading to ambiguity about timeout handling [round protocol timing].

- “The submission is exactly h + 1 lines” — If a line has a syntax issue, the server returns malformed_row_<r>. The spec doesn’t define whether the bot may retry within the same round after a malformed row, or if the round is immediately aborted; it only defines the error code path [round protocol error handling].

- “(If your answer includes a generated file … you must call share_files)” in system reminder — Not relevant to the prompt critique, but indicates deliverables in case of file outputs; the spec’s behavior on file outputs is clear, but not tied to this critique.

- “A rectangle is guaranteed tileable by some subset of the 35 free hexominoes” — The spec relies on server knowledge of the valid tiling witness; it doesn’t define how to verify tiling validity locally beyond the server’s checks [consistency between local tiling generation and server validation].

- “Globally unique ids” — If an id repeated in two separate regions, the server flags duplicate_id_<id>. The spec doesn’t explain how a bot could generate two separate regions with the same label in a plausible tiling; this is clear, but the edge case of reusing id across rounds is not discussed beyond global uniqueness per submission [state leakage across regions].

- “No leading zeros except 0 itself” — The spec enforces id formatting strictly. It would help to specify error handling if an id like  is used for multiple shapes, but the server will flag as duplicate_id_<id>. The edge case of repeated use across round submissions isn’t directly stated.

Illustrative example: What to fix or clarify if you were revising this prompt

- Add explicit timeout behavior: does a 30-second budget cause an outright disconnect, or can the bot still submit a partial tiling that later completes?

- Clarify retry policy: if INVALID is returned, can the bot retry within the same round, or must it await the next ROUND?

- Define behavior for BOTNAME issues: if BOTNAME is missing or invalid, should the bot emit a specific error before disconnecting, or rely on server to close the connection?

- Specify minimum and maximum inventory expectations for typical rounds, or provide a baseline scoring target to avoid perpetual low-inventory tilings that might be too hard to achieve across varied w/h.

- State how to measure and report time usage if the 30-second budget is very tight due to large tiling computations, to avoid unintentional timeouts.

Recommendations for implementers

- Treat the protocol as a strict finite-state machine: on startup, read BOTNAME, connect, send first line, await ROUND, then for each round, compute a full h-line tiling within 30s, send h lines plus END, flush, then read OK/INVALID and END_ROUND, and proceed. Handle timeouts gracefully and reject rounds with INVALID if any invariants fail.

- Implement robust input parsing for rows: validate exact bracket structure, width w, and integer ids without leading zeros, and ensure global id uniqueness within a single round.

- Use a tiling strategy that intentionally minimizes inventory, but ensure correctness. You may implement a simple canonical tiling using a limited set of hexomino shapes to minimize risk of invalid tilings by sticking to a small, well-supported subset.

- Consider deterministic, well-tested algorithms for hexomino tiling or leverage precomputed witness tilings provided by the server when feasible to reduce risk of invalid tilings.

- Include comprehensive error handling and clear logs for each round to help diagnose INVALID reasons quickly.

Would you like me to produce a focused checklist of clarifications to send to the spec author, or generate a template Python 3.10 bot that adheres to these interpretations with conservative tiling logic?

========================================================================
# Grok  (:7823, logic, repo cross-ref, brutal honesty)  [99.3s]
========================================================================
**1. Ambiguities**

- "Same id appears in two non-adjacent (4-neighbour) cells → `duplicate_id_<id>`"  
  Any connected 6-cell region necessarily contains pairs of same-id cells that are not 4-adjacent (e.g. the two ends of the straight hexomino, or any compact shape). A reasonable reader could interpret this as "trigger duplicate_id on every valid hexomino", which contradicts the later "disconnected_<id>" bullet and the global-unique-id rule. The parenthetical note "equivalent to the duplicate_id case but reported separately for clarity if all id cells share a label" makes the intent even less clear.

- The entire §7 catalog block (starting "#0 (1×6) #1 (2×5) #2 (2×5) #3 (2×5)\n###### ##### ##### #####\n                 #.... .#... ..#..")  
  Shapes are crammed onto shared lines with inconsistent leading spaces, staggered continuations, and no per-shape bounding-box separators. Two competent readers can extract materially different cell sets for at least #1–#3, #4–#7, #32–#34, etc. (e.g. exactly which # cells belong to which labeled shape on the misaligned second line). This is fatal because bots must produce shapes the server will accept after its own (unspecified) canonicalization.

- "after canonicalization over 8 rotations + reflections" (§6)  
  No definition of the canonical form (lex-smallest coordinate string? min-bounding-box normalized? min-id first cell? etc.). Two readers could implement different normalization and therefore disagree on whether a given region matches one of the 35.

**2. Underspecified edge cases**

- 1-row and 2-row rectangles (bounds allow `h=1, w=36,42,…` or `h=2, w=18,…`). Only the straight #0 can tile a 1-row board; many shapes cannot fit at all. Spec gives no guidance on how the bot must handle these thin cases while still producing a valid low-inventory tiling.

- What happens if `os.environ['BOTNAME']` is missing, contains invalid characters, or has trailing whitespace other than `\n`? Spec says "use them verbatim" after stripping trailing `\n`, but does not say what the bot should do on KeyError or after stripping.

- Server messages other than the documented ones (e.g. malformed ROUND line, premature TOURNAMENT_END, extra data after END). No error-handling behavior specified; bot could reasonably either crash or ignore, leading to different implementations.

- Exact definition of "the instant the server has read the bot's complete submission". Does it include the final `\n` of END, or the moment the server’s recv returns? Affects the 30 s wall-clock window and tie-break ordering on localhost.

**3. Protocol / interface gotchas**

- Line termination: "lines terminated by a single `\n` (LF, byte `0x0a`). CRLF is invalid." + "You must flush after each line you send (e.g. `sock.sendall(line.encode())`)"  
  The example does not show a flush, yet the text mandates one. On some Python socket wrappers or buffered files this produces different wire behavior (partial lines, delayed delivery) that can trigger server-side malformed_row or timeout.

- Row parsing is frame-sensitive: rows are variable-length strings of concatenated `[id]` tokens (3 chars for id<10, 4 for 10–99, etc.). Spec gives no reference parser or exact grammar beyond "parses as `[<int>]` × w". Tiny differences in whitespace, leading zeros, or bracket handling will be reported as `malformed_row_<r>` with no further diagnostic.

- No guidance on socket recv buffering / line splitting. A naïve `recv(1024)` loop without proper partial-line buffering can mis-frame ROUND / END_ROUND / OK lines, especially under load or when the server sends multiple lines in one packet.

**4. Inconsistencies**

- Sample transcript (§9) shows ids 0–7 on a 6×6 board (implying at least 8 pieces) yet the walk-through states "in a real submission with 6 pieces, exactly 6 distinct ids appear". The transcript is labelled "illustrative" but still directly contradicts the "exactly one piece-instance" rule and the validation logic.

- Validation table first checks for "Same id appears in two non-adjacent …" before the disconnected check, yet the global rule "Reusing an id, even for two regions of the same shape, is `duplicate_id_<id>`" is stated later. The two descriptions are not compatible.

**5. Missing information that would let a competent implementer write a working version**

- No machine-readable (or even cleanly human-readable) definition of the exact 35 hexominoes. The visual catalog is unusable as a spec; there is no coordinate list, no standard hexomino names/numbers, no reference implementation of canonicalization. Impossible to guarantee a tiling the server will accept.

- No example of a minimal valid full submission (correct ids, correct row strings, correct END handling) that would actually pass server validation.

- No reference Python socket boilerplate that satisfies the exact flush / line-buffering / CRLF rules.

- No local validator or test cases. Implementers cannot verify their shape extraction, connectivity checks, or output formatting before the tournament.

- No strategy constraints or expected approach for producing a valid tiling of an arbitrary guaranteed-tileable rectangle (up to 30×30) in <30 s wall-clock with stdlib only. Backtracking is hopeless at that scale; no constructive method, no precomputed tiles, no allowed inventory target is given.

The spec is not ready for one-shot LLM implementations. The catalog presentation alone guarantees divergent bots that will all fail validation.

========================================================================
# Perexp  (:7826, deep reasoning, code execution)  [48.4s]
========================================================================
Here is a structured critique of the HappyHexaminos prompt/spec, focusing on ambiguities, underspecified edge cases, protocol gotchas, inconsistencies, and missing information. I quote exact text where relevant and explain what's wrong or leaves room for misinterpretation.

Ambiguities
- “The server sends the bot a rectangle of width w and height h with w * h ≡ 0 (mod 6).” The spec says the server guarantees tileability but does not specify what constitutes a valid tiling in the input format beyond the per-row brackets. What if the tiling uses a valid set of shapes but a given shape instance is not part of the 35 free hexomino catalog due to a rotation/reflection mislabeling? The spec later defines inventory as distinct free-hexomino shapes used, but it doesn’t explicitly require that each labeled region corresponds to a valid free hexomino in the 8-orientation canonical sense. This creates ambiguity about whether a piece in the submission must be a canonical rotation/reflection of one of the 35 shapes or simply any 6-cell connected region; the invalid reason “not a hexomino” hints at a requirement, but the exact mapping/validation is unclear. “If all rows parse and every region is exactly one valid free hexomino, the submission is OK” confirms intent but not the precise pre-validation checks for each placement beyond 6 cells and connectivity. This ambiguity could lead to divergent implementations across frontier models. 

- “The rectangle is server-generated and guaranteed tileable by some subset of the 35 free hexominoes (the server constructs a witness tiling before sending the round, so a valid full tiling always exists, though the server does not reveal it).” It’s unclear whether the server’s witness tiling can include hexomino pieces that require rotations or reflections beyond what the client is allowed to produce, or if the server’s tiling uses only a canonical orientation mapping that the client must reproduce via rotations/reflections. The absence of a formal constraint tying the server’s witness to the client’s permissible output shapes invites divergent interpretations of the allowed transformations. 

Underspecified edge cases
- “A row line doesn't parse as [<int>] × w (wrong width, malformed bracket, non-integer id, leading/trailing whitespace) → not specified: is a line with extra spaces inside brackets allowed (e.g., [ 7 ]), or must there be no spaces inside brackets? The invalid token list mentions “malformed_row_<r>” but not the exact character-level rules for spaces inside the brackets. 

- “Globally unique ids. Each <id> in the submission corresponds to exactly one piece-instance and may not appear in more than one connected region.” It’s ambiguous whether reusing the same id for multiple regions is always forbidden, or allowed if the multiple regions belong to the same piece type/shape (i.e., same id but disjoint regions). The text says “Reusing an id, even for two regions of the same shape, is duplicate_id_<id>” which clarifies that reuse is forbidden, but it doesn’t explicitly handle multiple disjoint cells with the same id due to server-side validation timing. The spec later states this as a hard rule; edge-case clarity is okay but could be more explicit about the intention that each id must form exactly one connected region of size 6. 

- “The bot’s submission is exactly h + 1 lines: <row 0> … <row h-1> END.” It’s underspecified what happens if END appears on a line that also contains cell data (e.g., trailing spaces) or if END is not present. The validation table lists malformed_rows for wrong number of rows or END placement; but the exact boundary conditions during parsing (e.g., whether END must be the last line and whether there can be trailing whitespace after END) are unclear. 

- “The server replies with OK <inventory> or INVALID <reason>.” The inventory is defined as the count of distinct free-hexomino shapes used. However, there is no explicit description of whether the server may treat a tiling that uses 1 piece of each of 6 shapes as inventory 6; yes that’s implied, but there’s no explicit tie-in between inventory value and allowed tile configurations in terms of what constitutes “distinct shapes used” when multiple orientations of the same shape are present. The text implies this, but an implementer would benefit from a precise enumeration mapping from all 35 shapes to a 0..34 index. 

- “Lines have no leading or trailing whitespace beyond the single terminating \n. A trailing space, leading space, double space, or any non-conforming whitespace makes the line malformed.” This is clear, but what about tabs or other control characters? The spec says ASCII text; tabs are ASCII as well but are not mentioned in allowed whitespace. It would be safer to specify that only spaces are disallowed or allowed inside brackets, not other ASCII whitespace characters. 

Protocol / interface gotchas
- Time budget: 30 seconds per round including transmission time. It does not specify whether partial transmissions (e.g., stalling while computing) counts against the 30-second budget. It likely does, but the boundary between computation and network latency is not formalized. Implementers would benefit from a strict model of how to measure elapsed wall-clock time. 

- Round sequencing: “The server announces each round to all registered bots simultaneously.” The spec does not define how to handle late or out-of-sync submissions. It mentions invalid or missing submission yields 0 points, but there’s no explicit timeout behavior beyond the per-round 30-second budget. If a bot finishes after the 30s window, is the server allowed to consider it invalid even if the submission arrives in the same wall-clock? It’s implied but not formal. 

- Encoding and line endings: “ASCII text, lines terminated by a single LF.” The spec is explicit but does not define behavior if the client uses a library that normalizes line endings or if intermediate buffering causes a line to be read with Windows-style endings. Implementers must ensure exact line endings; otherwise devices may misinterpret. 

- Inventory and tie-breaking: Tiebreak by arrival time is described, but the exact protocol for submission timestamp precision and clock synchronization across machines is not specified. If two bots submit in the same millisecond, which one arrives first? This ambiguity could affect edge-case outcomes. 

Inconsistencies
- The 35-hexomino catalog is presented with shapes labeled #0 through #34, but the inventory is described as “the count of distinct free-hexomino shapes in the bot's tiling.” There is no explicit mapping or requirement that the server’s accepted tilings align with these label numbers; the server only returns a numeric inventory. This is consistent if the 35-shape taxonomy is fixed, but the spec could be clearer about the server’s expectation that any tiling uses one of those 35 shapes in any orientation. The inconsistency is subtle but worth clarifying to prevent shape-label confusion. 

- The sample wire transcript discusses an example where “Id 0..7” appear and notes a potential mismatch between number of pieces and distinct ids. The earlier formal rules require exactly w*h/6 pieces with unique ids per piece; the sample note acknowledges possible inconsistencies but doesn’t resolve them. The contradiction is only in illustrative prose, not in formal rules, but it creates confusion for readers about acceptable tiling encodings. 

Missing information
- Precise, machine-readable mapping from a submitted [id] layout to a canonical hexomino type (one of 35) including allowed rotations/reflections, and how to validate that a given 6-cell region matches exactly one of the 35 shapes. The spec mentions “regions are valid free hexominoes” but does not provide a formal algorithm or reference for canonicalization. 

- Deterministic tie-break timing details: exact clock source, granularity, and how to handle clock skew across machines. The rule says “earlier wall-clock arrival wins” but not how arrival times are measured or synchronized. Without a precise model, identical behavior across frontiers is uncertain. 

- Handling of end-of-round scheduling: What happens if a server delays END_ROUND or if a bot doesn’t read END_ROUND due to network hiccups? The protocol implies the server sends END_ROUND after OK/INVALID, but no explicit retry or timeout is described. 

- Validation failure ordering: It lists a sequence of INVALID reasons with a first failure principle but doesn’t specify how to communicate if multiple issues exist (e.g., wrong size and disconnected region). It says the first failure determines INVALID; that’s clear, but the exact order of checks (though implied by the table) could be stated explicitly to prevent divergence. 

- Non-blocking/idle behavior: The “do not set socket read timeouts; idle reads should block.” This is clear for the server side, but what about the client’s internal timers if computation is long? The 30-second budget is stated, but there’s no explicit guidance on what happens if the client attempts to read a round header while blocked in computation. A precise FSM would help implementers. 

- Escalation path for malformed submissions: The spec says “Invalid or missing submission → 0 points.” It doesn’t specify whether a bot can retry within the same round or must abandon after a single submission. A defined retry policy would help avoid accidental 0-point penalties due to transient issues. 

Illustrative quote references (exact text pulled)
- Ambiguity example: “The server generates a witness tiling before sending the round, so a valid full tiling always exists, though the server does not reveal it.” This raises questions about the allowed transformations and consistency with the 35-shape catalog. 
- Parsing rule: “A row line doesn't parse as [<int>] × w (wrong width, malformed bracket, non-integer id, leading/trailing whitespace) → `malformed_row_<r>`” This describes the error but not the exact allowed whitespace inside brackets. 
- Inventory/tile validation: “Not a hexomino” and “duplicate_id_<id>” indicate validation steps but do not specify the canonicalization procedure for 8 rotations/reflections. 
- Global uniqueness: “Globally unique ids. Each <id> in the submission corresponds to exactly one piece-instance and may not appear in more than one connected region.” This is explicit but could be reinforced with an example to prevent misinterpretation. 

Recommendation: If you intend to use this spec across multiple frontier LLMs without changes, provide a formal, machine-readable appendix
- Exact data model: a formal grammar for each input line, including exact whitespace rules inside and between tokens.
- Canonicalization algorithm: a precise description (or reference implementation) for mapping any 6-cell region to one of the 35 free hexominoes, including allowed transformations.
- Timing model: precise clock semantics, tie-break timing granularity, and synchronization guarantees.
- Round-state machine: a complete finite-state diagram with transitions for ROUND, submission, OK/INVALID, END_ROUND, and TOURNAMENT_END, including timeouts and retries.

If you’d like, I can produce:
- A concrete, unambiguous formalization of the parsing and validation rules.
- A reference implementation sketch for tiling validation against the 35 hexominoes.
- A stricter protocol FSM with explicit timers and retry semantics.

Would you like me to draft a formal Appendix (grammar, validation spec, and FSM) to accompany this prompt?

========================================================================
# Perexp2  (:7827, second independent opinion)  [28.5s]
========================================================================
Here is a structured critique of the HappyHexaminos tournament prompt, focusing on ambiguities, edge cases, protocol gotchas, inconsistencies, and missing information. I quote the exact text and explain what’s wrong.

Ambiguities
- “The rectangle is server-generated and guaranteed tileable by some subset of the 35 free hexominoes.” What exactly constitutes a valid subset? If the server tiles with fewer than 6-cell regions of one hexomino due to repeats, is that allowed as long as each region is a valid hexomino? The spec later clarifies inventory counting, but the initial guarantee leaves room for interpretation about allowed tilings versus server-provided witness. Not explicit [Prompt: The server-generated tiling witnesses exist, but which tilings are acceptable beyond validity of regions].
- “The bot must respond with a full tiling of the rectangle: a partition of all w*h cells into k = w*h/6 connected 6-cell regions, each of which is one of the 35 free hexominoes.” Does the server require that the tiling exactly matches a known witness tiling, or just any valid tiling with valid hexomino shapes? It later says server constructs a witness tiling, but ambiguity remains whether the bot’s tiling must match that witness or just be any valid tiling. Also, are mirrored/rotated variants considered the same region? It says tiles can be rotated/reflected, but inventory counts distinct shapes; need explicit acceptance criteria if the server’s witness uses a particular orientation.
- “Inventory is the number of distinct free-hexomino shapes used” — Is inventory computed by the server with respect to 35-shape catalog, counting only shapes actually present in the tiling, regardless of orientation and duplicates? The text implies yes, but not crystal clear about whether two regions of the same free hexomino but different orientation count as a single shape for inventory. Clarity is needed: inventory counts distinct shapes, not instances [Prompt text supports this but could be misread].

Underspecified edge cases
- Handling of invalid submissions: “Invalid or missing submission (timeout, malformed grid, region that isn't a 6-cell hexomino, duplicate piece-instance label, partial coverage, out-of-bounds, etc.) → 0 points.” If a single region is invalid, is the entire submission invalid, or can partial credit be awarded? The text says first failure determines INVALID, so entire round is 0 for invalid, but this is an edge case if there are multiple issues maybe worth partial handling. Explicitly state that any single violation yields 0.
- Duplicate IDs: “Globally unique ids. Each <id> in the submission corresponds to exactly one piece-instance and may not appear in more than one connected region.” What about two separate regions sharing the same id but not connected (explicitly illegal) vs. two separate regions with same id accidentally but connected? The rule says duplicates are disallowed; edge case of mislabeling should be clearly handled as invalid.
- ROUND timing: “30 seconds wall-clock from the instant the server sends ROUND to the instant the server has read the bot's complete submission.” What constitutes “complete submission” if the bot stalls after END and begins transmitting late due to network issue? It mentions 30s budget including transmission; but no explicit handling if network hiccups cause partial submissions. Clarify whether slow networks are allowed to overrun the budget or cause timeouts.
- Encoding constraints: “ASCII text, lines terminated by a single LF.” What about non-ASCII botnames or id strings? They ensure only [A-Za-z0-9_-] allowed for BOTNAME, but what about IDs in the brackets? They restrict to decimal non-negative integers with no leading zeros. Clear, but edge-case about very large IDs or malformed ones is covered by malformed_row_<r>.
- END line placement: If END line is missing or extra lines are sent after END before ROUND, how is that handled? The spec says malformed_rows if END not in the right place; but exact behavior for extra lines after END is not explicit.
- Round progression: “Areas grow monotonically across the 10 rounds.” Are bots allowed to exploit by returning invalid tilings on early rounds to influence later rounds? The spec is silent on adaptive strategies across rounds beyond scoring. It might be fine, but unspoken constraints could be clarified.

Protocol / interface gotchas
- Timing discipline: The per-round budget includes compute and time to transmit; implementers must ensure no blocking I/O or slow operations before submission. This is okay but could lead to flaky behavior if the environment has jitter. Recommend explicit guidance that the bot should flush after each line and avoid buffering delays.
- Line format strictness: Any extra whitespace or trailing spaces invalidates a row. This is robust but stringent; ensure robust line generation to avoid subtle parse errors.
- Coordination with END_ROUND: After OK/INVALID, the server sends END_ROUND <n>. If a bot misparses or crashes, it could desynchronize. The protocol should include explicit recovery guidance, but it’s implicit in continuity.
- Inventory reporting: The server reports OK <inventory> but the protocol does not specify how inventory is validated if there are multiple ways to tile (e.g., two tilings using the same set of shapes but different counts). Clarify whether the server validates per-shape usage only, not the exact counts per shape beyond coverage.

Inconsistencies
- There is no explicit constraint that the tiling must be tileable by the server’s witness tiling. The initial guarantee mentions tileable by some subset, but not that the bot’s tiling must align with the server’s witness tiling. The validation table assumes that as long as all regions are valid hexomino shapes and cover the board, it passes; this is consistent, but the text could be clearer about whether the server’s witness tiling is a constraint or just a helpful guarantee.
- The sample transcript notes “Id 0..7 together form 6 connected 6-cell regions” which implies 8 IDs but 6 pieces; this is inconsistent with “exactly k pieces” and “distinct ids” rule. The example acknowledges potential confusion. The spec should enforce that exactly k distinct ids appear, each 6 cells, no duplicates, to be unambiguous.
- The “Catalog of the 35 free hexominoes” enumerates 35 shapes; the spec later uses inventory as count of distinct shapes. It would be clearer to specify whether two shapes that are rotations/reflections of the same hexomino count as one or potentially more for inventory. It says “distinct free-hexomino shapes” which resolves this but the potential for ambiguity in implementers remains if not read carefully.

Missing information
- Exact format and handling of the END line if a submission is malformed. They mention END_ROUND and then next ROUND, but no explicit retry/backoff semantics for transient errors.
- How to handle multiple valid tilings that use the same set of shapes but different shapes counts — does server validate counts or just that all cells are covered by valid hexomino shapes? It’s implied but not explicit.
- Timeout behavior in detail if the server stops reading input early or late; what if the submission is exactly at 30 seconds due to network jitter? They don’t specify grace or failure mode for boundary timing.
- Clarify whether a bot may reuse the same id across multiple disjoint regions as long as they are not adjacent (the table says duplicate_id_<id> triggers if the same id appears in two non-adjacent cells; but that wording could be read strictly that any repetition invalidates, yet it also defines “globally unique ids.” A combined clarification would help implementers.

Quote-level references to the prompts (as requested)
- “The rectangle is server-generated and guaranteed tileable by some subset of the 35 free hexominoes (the server constructs a witness tiling before sending the round, so a valid full tiling always exists, though the server does not reveal it).” This leaves ambiguity about whether the tiling must match the witness or simply be valid [Prompt §1].
- “The bot must respond with a full tiling of the rectangle: a partition of all w * h cells into k = w * h / 6 connected 6-cell regions, each of which is one of the 35 free hexominoes (in some rotation/reflection).” It doesn’t state whether tilings must align with the witness tiling or are any valid tiling [Prompt §1].
- “The bot's submission is exactly h + 1 lines: <row 0> … <row h-1> END” This is explicit, but edge margins around END are not described beyond malformed_rows [Prompt §5].
- “<inventory> is the count of distinct free-hexomino shapes in the bot's tiling.” This defines inventory but not explicit tie-break interactions when inventories are equal beyond arrival time [Prompt §2].

Recommendation
- Clarify whether the tiling must match the server’s witness tiling or any valid tiling is acceptable.
- Define exactly how inventories are computed when shapes appear in multiple rotations/reflections (the use of “distinct free-hexomino shapes” suggests rotations/reflections are considered the same, which is fine but should be explicit for implementation).
- Explicitly describe handling of edge timing boundaries (exact 30-second boundary, network jitter, and partial submissions).
- Add an unambiguous constraint that exactly k distinct ids must appear, each with exactly 6 cells, and that all ids must be used (no extra, no missing), to avoid the illustrated confusion in the sample.

If you want, I can draft a tighter, unambiguous revision of the prompt incorporating these clarifications.
