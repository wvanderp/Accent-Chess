from chess import PIECE_TYPES, COLORS, WHITE, BLACK, KING, QUEEN, ROOK, BISHOP, KNIGHT, PAWN

# dict of piece names to piece types
pieceNames = {
    # king
    'king': KING,

    # queen
    'queen': QUEEN,

    # rook
    'rook': ROOK,

    # bishop
    'bishop': BISHOP,

    # knight
    'knight': KNIGHT,

    # pawn
    'pawn': PAWN
}

# translates a name to a piece
def nameToPiece(name: str) -> PIECE_TYPES:
    name = name.lower()

    # check if the name is in the dict
    if name in pieceNames:
        return pieceNames[name]
    else:
        raise ValueError('Invalid piece name:' + name)

# a dict of names and there corresponding colors
colorNames = {
    # white
    'white': WHITE,

    # black
    'black': BLACK
}   

# translates a name to a color
def nameToColor(name: str) -> COLORS:
    name = name.lower()

    # check if the name is in the dict
    if name in colorNames:
        return colorNames[name]
    else:
        raise ValueError('Invalid color name:' + name)