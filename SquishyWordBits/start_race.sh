#!/bin/bash

echo "Starting bots..."

BOTNAME=claude_squishy_word_bits_bot   python3.10 claude.py   & PID1=$!
BOTNAME=gemini_squishy_word_bits_bot   python3.10 gemini.py   & PID2=$!
BOTNAME=grok_squishy_word_bits_bot     python3.10 grok.py     & PID3=$!
BOTNAME=chatgpt_squishy_word_bits_bot  python3.10 chatgpt.py  & PID4=$!
BOTNAME=mimo_squishy_word_bits_bot     python3.10 mimo.py     & PID5=$!
BOTNAME=nemo_squishy_word_bits_bot     python3.10 nemo.py     & PID6=$!
BOTNAME=glm_squishy_word_bits_bot      python3.10 glm.py      & PID7=$!
BOTNAME=kimi_squishy_word_bits_bot     python3.10 kimi.py     & PID8=$!
BOTNAME=muse_squishy_word_bits_bot     python3.10 muse.py     & PID9=$!
BOTNAME=deepseek_squishy_word_bits_bot python3.10 deepseek.py & PID10=$!

trap "echo 'Stopping all bots.'; kill $PID1 $PID2 $PID3 $PID4 $PID5 $PID6 $PID7 $PID8 $PID9 $PID10 2>/dev/null; exit" SIGINT

echo "All bots launched (10 of them). Press Ctrl+C to stop."

wait
