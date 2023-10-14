
from chess import COLORS, WHITE, BLACK, Move, Board, PIECE_TYPES, PAWN

nums = {1: "a", 2: "b", 3: "c", 4: "d", 5: "e", 6: "f", 7: "g", 8: "h"}


def moveFromFens(before: Board, after: Board) -> Move:
    # find the move made to get from board1 to board2
    # get the difference between the two boards

    differences = []

    for square in range(64):
        if before.piece_at(square) != after.piece_at(square):
            differences.append(square)

    if len(differences) > 4:
        raise "too many differences"

    possibleMoves = []

    # iterate over all the possible moves
    for difference in differences:
        for otherDifference in differences:
            if difference != otherDifference:
                move = Move(difference, otherDifference)
                if not (move in possibleMoves):
                    possibleMoves.append(move)

    # add all the promotions possibilities
    for symbol in PIECE_TYPES:
        if symbol == None:
            continue

        # can not promote to a pawn
        if symbol == PAWN:
            continue

        if before.piece_at(differences[0]) is not None:
            possibleMoves.append(Move(differences[0], differences[1], symbol))
        
        if before.piece_at(differences[1]) is not None:
            possibleMoves.append(Move(differences[1], differences[0], symbol))

    # check if the possible moves are valid
    # and result in the correct board
    for move in possibleMoves:
        if move in before.pseudo_legal_moves:

            alteredBoard = before.copy()
            alteredBoard.push(move)

            if(alteredBoard.fen()[:-5] == after.fen()[:-5]):
                
                return move

    print(before.fen())
    print(after.fen())

    raise Exception("no valid move found")
