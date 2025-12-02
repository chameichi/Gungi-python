# This is a program about the board
from dataclasses import dataclass, field
from pieces import Piece, PieceType, Side, MovePattern, MoveType


@dataclass
class Board:
    width: int = 9
    height: int = 9
    grid: dict[]