# Grandmaster Chess (DOS, 1993): difficulty investigation

Investigated 2026-11-06 against the actual Archive media used by
`games.Grandmaster_Chess.setup`, running in the project's DOSBox/Xvfb runtime.
The setup downloads [Grandmaster Chess 1993](https://archive.org/details/msdos_Grandmaster_Chess_1993)
and verifies ZIP SHA-1 `30a361e0b3db038f8c53146942bd07f4411d203b`.
These findings apply to that release, not similarly named chess programs.

## Ranked difficulty presets

**Game > Playing Strength** has five discrete choices, independent of time
controls. Each is a separate engine identity in the default rankings:

| Profile | Native label |
| --- | --- |
| `beginner` | BEGINNER |
| `novice` | NOVICE |
| `intermediate` | INTERMEDIATE |
| `expert` | EXPERT |
| `grandmaster` | GRANDMASTER |

The distributed configuration starts at Intermediate. These are verified native
labels; no Elo estimate, search depth, or artificial thinking budget is inferred
from them. See [the live strength dialog](grandmaster-strength.png).

## Other settings

**Game > Time Control** is a separate dialog, titled Select Level, with:

- 60 Moves in 5 Minutes
- 60 Moves in 15 Minutes (distributed default)
- 60 Moves in 30 Minutes
- 60 Moves in 60 Minutes
- ? Moves in ? Minutes
- Game in ? Minutes
- 1 Move in ? Seconds
- Fixed Depth
- Infinite

See [the actual time-control dialog](grandmaster-time-control.png). The first four
are native clock presets, while the following finite choices request values from
the user. This connector varies the explicit Playing Strength difficulty axis
and preserves the native clock setting, rather than creating a cross product of
strength and every clock setting. Arbitrary entered thinking times are not new
difficulty identities. Infinite is an analysis mode without a naturally completed
turn and is unsuitable for an automatic match. No external thinking cutoff is
introduced by the difficulty setter.

**Game > Playing Style** contains Balanced, Active, Passive. **Set Pondering**
contains Disabled, Enabled. These are orthogonal behavior settings, not additional
strength presets. They are preserved. Labels were corroborated in the actual
`GMCHESS.EXE` resources; the strength and clock choices were also inspected live.

## Setting and verification

`games.Grandmaster_Chess.difficulty.set_difficulty(client, profile, timeout=90)`
is called on an initialized idle board, before switching the computer to White.
It opens Game with F2, verifies that menu's pixels, chooses its fourth entry,
and verifies the Playing Strength dialog. Tab navigates from OK through Cancel
to the requested individual radio control; Return activates the radio. Space
does not activate this DOS control. Tab then returns to OK and Return commits.
The setter reopens the dialog and checks the selected radio before returning.

Input and acknowledgements use the actual 640x480 VGA menu pixels. Hashes cover
only static menu/title rectangles; selected-radio pixels establish the value.
An unrelated modal, unexpected runtime, invalid profile, or missing readback
fails closed. Poll pacing is independent of successful UI acknowledgement.
The setup timeout only bounds configuring the menu; it is not a move limit.

Rapid X11 mouse clicks were missed by the vintage game's mouse scanner during
investigation. Keyboard navigation plus radio readback succeeded for every
strength, so the setter does not rely on those clicks.

All five profiles were set and verified by reopening the live dialog; board
screenshots `grandmaster-<profile>.png` record the resulting computer label.
[Validation record](grandmaster-validation.json) also records rejection of an
unknown profile and failure to proceed while a different modal is open. This
validates selecting the level, not a complete game at every difficulty.
