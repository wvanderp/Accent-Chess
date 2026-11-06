The most important thing is architecture is more important than getting things done quickly. Plan your changes carefully before implementing them. Make sure that the architecture remains clean and extendable as the choices you make now will affect the future development of the project.

I hate venvs. Do not use them. Install all dependencies globally using pip and manage versions using requirements.txt.

Use python type hints for all functions and methods. This will help with code readability and maintainability.

When implementing new Engine connectors, dont use sleep statements to wait for the engine to make a move. Instead, implement proper waiting mechanisms that check the ui of the vintage game to see when it has made its move. This will make the connectors more reliable and efficient.

Document the code with the findings during investigations. This will help future developers understand the reasoning behind certain decisions and make it easier to maintain the codebase.

Please remember that image recognition is not the only way to Rome. You may also read the memory of the game or use other ways of determining the state of the game.

Stockfish is a special case: it is the measuring stick for the vintage programs, not a collection of difficulty entrants. Keep its Skill Level at the maximum and UCI_LimitStrength disabled. Do not create weakened Stockfish ranking entries.

Each verified native difficulty of a vintage program is a separate tournament engine with a stable identity. Record the exact setting and verify it in the program before playing; never mix results from different difficulties. Do not impose an external thinking deadline on vintage engines by default. Startup and menu/input failures may still have bounded diagnostic waits; engine completion must be observed rather than inferred from elapsed time.
