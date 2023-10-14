from PIL import Image
import pyautogui
from enum import Enum
import numpy as np

squareXSize = 52
squareYSize = 39


class State(Enum):
    EMPTY = "EMPTY"

    BLACKPAWN = "BLACKPAWN"
    BLACKTOWER = "BLACKTOWER"
    BLACKKNIGHT = "BLACKKNIGHT"
    BLACKROOK = "BLACKROOK"
    BLACKBISHOP = "BLACKBISHOP"
    BLACKQUEEN = "BLACKQUEEN"
    BLACKKING = "BLACKKING"

    WHITEPAWN = "WHITEPAWN"
    WHITETOWER = "WHITETOWER"
    WHITEKNIGHT = "WHITEKNIGHT"
    WHITEROOK = "WHITEROOK"
    WHITEBISHOP = "WHITEBISHOP"
    WHITEQUEEN = "WHITEQUEEN"
    WHITEKING = "WHITEKING"

black = (0,0,0)
white = (255, 255, 255)
green = (0, 128, 0)    
oGreen = (128, 128, 0)

pawnMidLine = [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False]
towerMidLine = [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False]
knightMidLine = [False, False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False]
rookMidLine = [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, True, True, False, False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False]
queenMidLine = [False, False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False]
kingMidLine = [False, False, True, True, True, True, True, True, True, False, False, False, True, True, False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False]
def getMidLine(image: Image):
    midCord = squareXSize/2

    pixs = []

    for y in range(0, squareYSize-1):
        pixel = image.getpixel((midCord, y))
        pixs.append(pixel == black or pixel == white)

    return pixs

def findState(image: Image):
    centerPixel = image.getpixel((squareXSize/2, squareYSize/2))
    if centerPixel == green or centerPixel == oGreen:
        return State.EMPTY

    midLine = getMidLine(image)

    # pawn
    if midLine == pawnMidLine:
        if centerPixel == black:
            return State.BLACKPAWN
        else:
            return State.WHITEPAWN

    #tower
    if midLine == towerMidLine:
        if centerPixel == black:
            return State.BLACKTOWER
        else:
            return State.WHITETOWER

    #knight
    if midLine == knightMidLine:
        if centerPixel == black:
            return State.BLACKKNIGHT
        else:
            return State.WHITEKNIGHT

    #rook
    if midLine == rookMidLine:
        if centerPixel == black:
            return State.BLACKROOK
        else:
            return State.WHITEROOK

    #queen
    if midLine == queenMidLine:
        if centerPixel == black:
            return State.BLACKQUEEN
        else:
            return State.WHITEQUEEN

    #king
    if midLine == kingMidLine:
        if centerPixel == black:
            return State.BLACKKING
        else:
            return State.WHITEKING


myScreenshot = pyautogui.screenshot()
base = pyautogui.locateOnScreen('referance.png')

board = myScreenshot.crop((base.left, base.top, base.left + base.width, base.top + base.height))

# board.show()
localX = 4 * squareXSize
localY = 0 * squareYSize
square = board.crop((
    localX,
    localY,
    localX + squareXSize, 
    localY + squareYSize 
))

for i in range(0, 8):
    for j in range(0, 8):
        localX = i * squareXSize
        localY = j * squareYSize

        square = board.crop((
            localX,
            localY,
            localX + squareXSize, 
            localY + squareYSize 
        ))

        square.save('./{}-{}.png'.format(i,j))
        print(findState(square))

