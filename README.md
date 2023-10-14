# Accent Chess

In this project we want to bring old chess computers back to live. It will do this by having a UCI interface to emulators of old chess computers. this way you can play against the old chess computers with modern chess engines.

## architecture

the architecture consists of two major parts. first we have clases that know how to work with the emulators. and secondly with have a UCI interface. and the special sauce is that we have a class that knows how to connect the two.

### Emulator classes

the important parts here is that these classes need to know the following things:

- how to start the emulator
- how to get into the game
- what the current game state is
- how to make a move
- how to create a arbitrary game state

and it also needs to know which of the UCI commands it can handle. there are some engines that cannot start from a arbitrary game state.

### UCI interface

the UCI interface will handel the communication with the outside world. it will parse the commands and send them to the correct emulator. it will also need to know how to handle the responses from the emulators.

the UCI interface needs to soften the edges of the emulators. It can talk to the emulator classes to get things done. but it also needs to know what counts as thinking time and what counts as setup time. It can take some time to setup a game state. and it can take some time to make a move. but the UCI interface needs to know what is what.

## TODO

- [] create the UCI interface
  - [] understand the UCI protocol
  - [] create a UCI parser
  - [] create a base class for the emulators that can handle the UCI protocol
  - [] create IO interface for the UCI interface
- [] emulators
  - [] create a framework for setting up emulators
    - [] the internet archive equality
    - [] dosbox
    - [] gameboy emulator
  - [] create a prototype for one game
  - [] create utilities
    - [] image chessboard reader
    - [] game state checker
    - [] checking for valid moves

## Potential games

- Battle Chess
- Chessmaster 3000 (and the other chessmaster games)
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

and while this is an impressive list of games. it is currently just a list of games. and we need to figure out which of these games we can actually emulate. and which of these games we can actually play against.

## Thoughts

to make this project a success it needs to be able to be accessed in a easy way. controlling with UCI is the most straight forward way to do this.

the thing with the uci protocol is that it is that the game state is very fragile and that UCI can ask a engine to start from any game state.

so to make sure that we can accommodate we need to make a more narrow implementation of the UCI protocol. and just error out when we cant handle the request.
