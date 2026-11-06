# Battle Chess: Atari ST levels

Investigated the exact 1989 Atari ST release selected by `setup.py`, in Hatari
2.4.1 with EmuTOS 1.3, on 2026-11-06. This is not the DOS, NES, or Apple IIGS
version; level counts documented for those ports must not be copied here.

Hold the right mouse button, move to **Level**, then release over the desired
entry. The actual menu contains ten finite named presets:

| Profile | Native label |
| --- | --- |
| `novice` | Novice |
| `level-1` through `level-9` | Level 1 through Level 9 |

The menu also contains **Set Time**, an arbitrary custom thinking-time control.
It is excluded from engine identities. The named presets are included even
when their strength is implemented through native thinking budgets. Accent
Chess must let the original engine finish that native search; it must not send
**Force Move** or add an external search deadline.

The actual menu's plus sign marks the active level; the default was Level 1.
`difficulty-level-menu.png` captures the native menu with Level 2 selected.
The setting module reads that plus sign and checks the black highlight behind
the target row before releasing the button. Readback also requires the bottom
Set Time label: a partially unfolding scroll can temporarily put a marker or
black background at another row's coordinates. This matters because an HTTP
pointer acknowledgement precedes Hatari's animated guest cursor: releasing
immediately can choose an adjacent row or no entry. The menu is reopened for
readback, then dismissed over its heading. Failure never silently certifies a
requested level. The setter does not patch memory or use fixed move delays.

All ten settings were verified in the running ST game, including Novice,
Levels 1–9, and a return from Level 9 to Level 1. Investigation found and fixed
missed selection caused by cursor lag, relative-pointer offset, and reading a
partially unfolding menu. Native hover and reopened selection are separate
acknowledgements; neither is inferred from a host mouse command.

The runtime must already be through the crack intro and title, showing an idle
game. The setter does not create a game or switch 3D/2D view. It can be used
independently of automatic play. Battle Chess's general reset/play connector
remains unsupported, so discovering levels does not make its preset engines
eligible for unattended rankings until that connector is implemented.

An exact ST-specific advertised seconds-per-level table has not been verified.
The module selects native named presets without assuming other ports' timings.

Source media: [Archive.org Atari ST release](https://archive.org/details/Battle_Chess_1989_Interplay_cr_MCA_m_EMT),
SHA-1 `b8260f86f75ce9419d28c77c39b5886852e688f6`.
