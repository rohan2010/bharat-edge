# phone/

Termux build notes and a timing script for the 4 GB Android feasibility run (Milestone 8).
Protocol: airplane mode, battery > 50%, 3 warm-up runs, 5 timed runs per configuration;
record load success, time to first token, decode tok/s, peak memory, and whether the OS killed
the process. llama.cpp is built on-device from the same commit as `third_party/llama.cpp`.
