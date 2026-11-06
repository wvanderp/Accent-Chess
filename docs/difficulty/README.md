# Native difficulty profiles

The investigation covers the four programs currently in `games.catalog`, using
their exact distributed releases. The long wishlist in the project README is
not an inventory of installed or supported programs.

Native difficulty presets become separate ranking entrants, including presets
implemented with thinking budgets. A freely entered/custom time value does not
create a difficulty. Infinite analysis is not a playable preset because it
requires an external interruption. Style, sound, animation, and board appearance
are not difficulty variants. Chessmaster's Coffeehouse mode deliberately changes
move consistency and therefore has separate profiles at each finite level;
its pondering toggle is held at the stronger setting.

Per-program findings, input protocol, release-specific limits, and evidence:

- [Grandmaster Chess (DOS)](grandmaster.md): five named strengths.
- [Chessmaster 2000 (C64)](chessmaster2000.md): levels 00–18, each with normal
  and Coffeehouse play (38 profiles). Infinite level 19 is excluded.
- [Chess 19xx (C64)](chess19xx.md): levels 1–9.
- [Battle Chess (Atari ST)](battlechess.md): Novice and levels 1–9. Custom Set
  Time is excluded; unattended play remains unsupported.

That is 62 vintage profiles plus the single Stockfish benchmark when available.

All profiles were selected and read back in the actual programs. The
[validation record](validation.json) links the 145-test regression run and a
[two-runtime Grandmaster smoke test](integration/grandmaster-strengths/validation.json).
It does not claim complete games or measured strength at every preset.

## List and select settings

Use the same registry as the tournament:

```powershell
python -m emulation.difficulty list
python -m emulation.difficulty list --game grandmaster
python -m emulation.difficulty set --game grandmaster --profile expert --url http://127.0.0.1:8765
```

The `set` script targets an already initialized, idle game, before its first
move. It checks the runtime's game identity before sending input, navigates the
native controls, and reads back the selected setting. An unknown profile, an
unrecognized menu, or a missing acknowledgement fails instead of silently
continuing. `--timeout` bounds menu navigation only. See each program's document
for exact preconditions; do not run this concurrently with a connector or viewer
that is sending input.

Each game's `difficulty.py` owns its native presets and setting protocol;
`emulation.difficulty` only validates, dispatches, and presents them. Add a new
verified preset there once its selection and readback have been investigated.
No fixed sleep is used as evidence that the program accepted a selection.

## Tournament behavior

```powershell
python -m emulation.tournament ranking --data tournament-data/difficulties
python -m emulation.tournament run --count 6 --data tournament-data/difficulties
```

The default catalog registers every verified preset as `game:profile`. Matches
initialize a fresh runtime per participant, reset the game, set and verify the
difficulty, and only then change the computer's color or submit moves. Presets
of the same program can play one another in separate runtimes. Existing color
and connector capability gates still apply; registering a difficulty does not
claim that an unsupported connector can play unattended.

Vintage searches have **no external thinking deadline by default**, in the
tournament and the shared play session. `--timeout` bounds startup/menu/input
readiness. An optional `--thinking-timeout` is an explicit diagnostic watchdog,
not a default search restriction. A failed watchdog never awards points. A hung
search without a watchdog needs operator cancellation; elapsed time alone cannot
distinguish it from a legitimate long search. The existing ply safeguard remains
a failure safeguard rather than an adjudicated game result.

Stockfish is one full-strength benchmark entrant. The UCI adapter explicitly
sets maximum Skill Level and disables UCI_LimitStrength. The existing
`--move-time` budget applies only to this benchmark, never to vintage programs.
There are no weakened Stockfish entries.

An old unprofiled ledger entry is retained with its original results and marked
`retired` when verified presets replace it. It is no longer scheduled. Its
results are never reassigned to a guessed difficulty. New profile rows start
unplayed. Attempt manifests copy exact engine definitions so the selected
difficulty remains recorded alongside the PGN and move log. These changes do
not rerun historical tournaments or manufacture new rankings.

Managed runtime logs are stored under each attempt's `white/` and `black/`
directories so two levels of the same program cannot overwrite one another's
evidence. For `--external-runtimes`, assign distinct URLs to the two participants;
the runner rejects sharing one runtime between them.
