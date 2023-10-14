# from chess import COLORS, WHITE, BLACK
# from PIL import Image
# import pathlib

# from games.Chess_19xx.Chess_19xx import Chess_19xx

# pieces = [
#     ('bishop.png', WHITE),
#     ('king.png', BLACK),
#     ('knight.png', WHITE),
#     ('pawn.png', BLACK),
#     ('queen.png', WHITE),
#     ('rook.png', BLACK),
# ]

# def test_getColor():

#     game = Chess_19xx()

#     for piece, expectedColor in pieces:
#         path = pathlib.Path(__file__).parent.resolve() / '..' / 'pieces' / piece
#         image = Image.open(path)

        
#         color = game.getColor(image)

#         print('piece', piece, 'expectedColor: ', expectedColor, 'got: ', color)
#         assert color == expectedColor
