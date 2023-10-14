# from chess import PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING, COLORS, WHITE, BLACK
# from PIL import Image
# import pathlib

# from games.Chess_19xx.Chess_19xx import Chess_19xx

# pieces = [
#     ('bishop.png', BISHOP),
#     ('king.png', KING),
#     ('knight.png', KNIGHT),
#     ('pawn.png', PAWN),
#     ('queen.png', QUEEN),
#     ('rook.png', ROOK),
# ]

# def test_getPiece():

#     game = Chess_19xx()

#     for piece, expectedPiece in pieces:
#         path = pathlib.Path(__file__).parent.resolve() / '..' / 'pieces' / piece
#         image = Image.open(path)

        
#         gotten = game.getPiece(image)

#         print('piece', piece, 'expected: ', expectedPiece, 'got: ', gotten)
#         assert gotten == expectedPiece
