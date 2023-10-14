# Accent Chess

We want to bring old chess computers back to life in this project. It will do this by having a UCI interface to emulators of old chess computers. This way, you can play against the old chess computers with modern chess engines.

## architecture

The architecture consists of two major parts. First, we have classes that know how to work with the emulators. Secondly, with a UCI interface. And the special sauce is that we have a class that knows how to connect the two.

### Emulator classes

The important part here is that these classes need to know the following things:

- how to start the emulator
- how to get into the game
- what the current game state is
- how to make a move
- how to create an arbitrary game state

And it also needs to know which UCI commands it can handle. Some engines cannot start from an arbitrary game state.

### UCI interface

The UCI interface will handle the communication with the outside world. It will parse the commands and send them to the correct emulator. It will also need to know how to handle the responses from the emulators.

The UCI interface needs to soften the edges of the emulators. It can talk to the emulator classes to get things done. But it also needs to know what counts as thinking time and what counts as setup time. It can take some time to set up a game state. And it can take some time to make a move. But the UCI interface needs to know what is what.

## TODO

- [] Create the UCI interface
  - [] understand the UCI protocol
  - [] Create a UCI parser
  - [] create a base class for the emulators that can handle the UCI protocol
  - [] Create an IO interface for the UCI interface
- [] emulators
  - [] create a framework for setting up emulators
    - [] the internet archive equality
    - [] DOSBox
    - [] gameboy emulator
    - [] mame
  - [] create a prototype for one game
  - [] create utilities
    - [] image chessboard reader
    - [] game state checker
    - [] checking for valid moves

## Potential games

- Battle Chess
- Chessmaster 3000 (and the other Chessmaster games)
- 1K ZX Chess
- Bobby Fischer Teaches Chess
- Chess 7.0
- Chess Champion 2175
- Chess Simulator
- Chess Titans
- Chess Wars
- Colossus Chess
- Combat Chess
- Cyber Chess
- Fritz
- Grandmaster Chess
- How About A Nice Game of Chess?
- Kasparov Chessmate
- Kasparov's Gambit
- Kotok-McCarthy
- Lego Chess
- Mac Hack
- MChess Pro
- Microchess
- Paul Whitehead Teaches Chess
- Pocket Fritz
- Power Chess
- Sargon
- Sargon II
- Sega Chess
- Silver Star Chess
- Socrates II
- Star Wars Chess
- Toledo Nanochess
- Ultimate Brain Game
- Video Chess
- Virtua Chess
- Virtual Chess 64
- Virtual Kasparov
- Wii Chess
- Zillions of Games

And while this is an impressive list of games. It is currently just a list of games. And we need to figure out which games we can emulate. And which of these games we can actually play against?

## Thoughts

To make this project a success, it needs to be accessed easily. Controlling with UCI is the most straightforward way to do this.

The thing with the UCI protocol is that it is that the game state is very fragile and that UCI can ask an engine to start from any game state.

To ensure that we can accommodate, we need to make a more narrow implementation of the UCI protocol. And just error out when we can't handle the request.
