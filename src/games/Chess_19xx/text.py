"""Coordinate-field completeness for Chess 19xx, which has no block cursor.

Only this connector supplies input. Each sent key must occupy its expected
character cell before another key is sent. Unlike total ink growth, cell count
cannot mistake a delayed previous character for the next character. The legal
board observer separately confirms the exact submitted move and engine reply.
Thin glyph shapes vary between the board legend and entry field, so character
identity is deliberately not inferred from a mismatched font template.
"""
import numpy as np
from PIL import Image


def prefix_complete(frame: Image.Image, length: int) -> bool:
    if not 0 <= length <= 5:
        return False
    pixels = np.asarray(frame.convert('RGB'))[323:332, :, 1] > 140
    for left in range(428, 431):
        complete = True
        for index in range(length):
            cell = pixels[:, round(left + index * 7.6):round(left + (index + 1) * 7.6)]
            rows = int(np.count_nonzero(np.any(cell, axis=1)))
            columns = int(np.count_nonzero(np.any(cell, axis=0)))
            if index == 2:
                # The explicitly typed separator is horizontal. A vertical
                # edge from the prior digit cannot acknowledge this cell.
                present = 1 <= rows <= 3 and columns >= 3
            else:
                # Letters/ranks span several rows; leaked hyphen pixels do not.
                present = rows >= 4 and columns >= 2
            if not present:
                complete = False
                break
        tail = pixels[:, round(left + length * 7.6):478]
        if complete and np.count_nonzero(tail) < 3:
            return True
    return False
