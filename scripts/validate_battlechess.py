"""Reproduce a live Stockfish/Battle Chess game from a manually reset 2D board.

This investigation runner does not claim viewer connector/reset support. Inputs
are gated on the guest cursor, selected-square border and vacated source square;
replies must be unique legal successors. No engine-completion delays are used.
"""
import argparse
import base64
from datetime import date
from io import BytesIO
import json
from pathlib import Path
from time import monotonic
from typing import Callable

import chess
import chess.engine
import chess.pgn
import numpy as np
from PIL import Image

from emulation.client import RuntimeClient
from emulation.play import successors
from recognition.runtime import create_reader
from recognition.board import RecognitionError

ROOT=Path('debug-frames/battlechess-validation')
client=RuntimeClient()
reader=create_reader('battlechess')
with Image.open(Path(__file__).resolve().parents[1] / 'src/games/Battle_Chess/checkmate.png') as reference:
    CHECKMATE=np.asarray(reference.convert('RGB').crop((16,216,446,232)),dtype=np.int16)


def checkmate_dialog(image: Image.Image) -> bool:
    actual=np.asarray(image.crop((16,216,446,232)),dtype=np.int16)
    return float(np.mean(np.abs(actual-CHECKMATE)))<2

def frame() -> Image.Image:
    raw=base64.b64decode(client.snapshot()['png'])
    (ROOT/'current.png').write_bytes(raw)
    return Image.open(BytesIO(raw)).convert('RGB')

def wait_for(predicate: Callable[[Image.Image],bool], timeout: float=20) -> Image.Image:
    end=monotonic()+timeout
    while monotonic()<end:
        image=frame()
        if predicate(image):
            return image
    raise TimeoutError('UI acknowledgement missing')

def cursor(image: Image.Image) -> tuple[int,int] | None:
    a=np.asarray(image,dtype=np.int16)
    skin=np.all(a==(238,170,136),axis=2)
    y,x=np.where(skin)
    if len(x)<20:
        return None
    return int(x.min())+4,int(y.min())+4

def pointer(x: int,y: int) -> None:
    client.send('pointer',{'x':x,'y':y})
    wait_for(lambda image: (p:=cursor(image)) is not None and abs(p[0]-x)<=4 and abs(p[1]-y)<=4)

def button(pressed: bool) -> None:
    client.send('mouse-button',{'button':1,'pressed':pressed})

def square_center(square: int) -> tuple[int,int]:
    return 126+56*chess.square_file(square),72+48*(7-chess.square_rank(square))

def selected(image: Image.Image,square: int) -> bool:
    x,y=square_center(square)
    a=np.asarray(image)[y-24:y+24,x-28:x+28]
    return bool(np.count_nonzero((a[:,:,2]>150)&(a[:,:,0]<120)&(a[:,:,1]<120))>150)

def send(move: chess.Move, board: chess.Board) -> None:
    if move.promotion:
        raise ValueError('Promotion dialog input has not been validated by this runner')
    x,y=square_center(move.from_square)
    pointer(x,y)
    button(True)
    # The selected-square border is an explicit acknowledgement by the game.
    wait_for(lambda image:selected(image,move.from_square))
    button(False)
    x,y=square_center(move.to_square)
    pointer(x,y)
    wait_for(lambda image:selected(image,move.from_square))
    button(True)
    x,y=square_center(move.from_square)
    # White's moved sprite must disappear from the source square.
    def vacated(image: Image.Image) -> bool:
        a=np.asarray(image,dtype=np.int16)[y-20:y+20,x-24:x+24]
        return np.count_nonzero((a[:,:,0]>a[:,:,1]+40)&(a[:,:,0]>a[:,:,2]+40))<5
    try:
        wait_for(vacated)
    finally:
        button(False)
    pending=board.copy()
    pending.push(move)
    if pending.is_checkmate():
        wait_for(checkmate_dialog).save(ROOT/'checkmate-dialog.png')
    else:
        pointer(600,420)

def observed_successor(board: chess.Board, timeout: float=180) -> chess.Board:
    end=monotonic()+timeout
    previous=None
    while monotonic()<end:
        image=frame()
        try:
            placement=reader.read(image).placement
        except RecognitionError:
            previous=None
            continue
        if previous!=placement:
            previous=placement
            continue
        matches=successors(board,placement)
        if len(matches)==1:
            candidate=matches[0]
            image.save(ROOT/f'{len(candidate.move_stack):03d}-{candidate.peek().uci()}.png')
            return candidate
    raise TimeoutError('No unique legal successor observed')

def save(board: chess.Board) -> None:
    game=chess.pgn.Game.from_board(board)
    game.headers.update({'Event':'Live Atari ST Battle Chess validation','White':'Stockfish via Accent Chess',
                         'Black':'Battle Chess 1989 Atari ST','Result':board.result(),
                         'Date':date.today().strftime('%Y.%m.%d')})
    (ROOT/'game.pgn').write_text(str(game)+'\n',encoding='utf-8')
    (ROOT/'position.json').write_text(json.dumps({'fen':board.fen(),'moves':[m.uci() for m in board.move_stack]},indent=2))

def main() -> None:
    global ROOT, client
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',default='http://127.0.0.1:8765')
    parser.add_argument('--stockfish',default='stockfish')
    parser.add_argument('--output',type=Path,default=ROOT)
    args=parser.parse_args()
    ROOT=args.output
    ROOT.mkdir(parents=True,exist_ok=True)
    client=RuntimeClient(args.runtime)
    if (ROOT/'position.json').exists():
        raise ValueError('Use a fresh output directory; automatic resume is not supported')
    board=chess.Board()
    # Keep the pointer inside the window; crossing its boundary desynchronizes
    # Hatari's relative guest cursor. Initial alignment is an operator precondition.
    pointer(600,420)
    for _ in range(2):
        if reader.read(frame()).placement!=chess.STARTING_BOARD_FEN:
            raise ValueError('Reset Battle Chess to a fresh 2D game before validation')
    save(board)
    with chess.engine.SimpleEngine.popen_uci(args.stockfish) as engine:
        while not board.is_game_over():
            if board.turn==chess.WHITE:
                result=engine.play(board,chess.engine.Limit(time=0.3))
                assert result.move is not None
                print(f'Sending {board.fullmove_number}. {board.san(result.move)} ({result.move.uci()})',flush=True)
                pending=board.copy()
                pending.push(result.move)
                send(result.move,board)
                if pending.is_checkmate():
                    board=pending
                    save(board)
                    break
                # Fast engine replies can replace the submitted board before capture.
                current=frame()
                try:
                    placement=reader.read(current).placement
                except RecognitionError:
                    placement=None
                if placement==pending.board_fen():
                    board=pending
                    current.save(ROOT/f'{len(board.move_stack):03d}-{result.move.uci()}.png')
                else:
                    board=observed_successor(pending)
                save(board)
                print('Observed '+board.fen(),flush=True)
            else:
                board=observed_successor(board)
                save(board)
                print('Reply '+board.peek().uci()+' '+board.fen(),flush=True)
        print('GAME OVER '+board.result(),flush=True)

if __name__=='__main__':
    main()
