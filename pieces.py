# This program is about pieces
from dataclasses import dataclass, field
from enum import Enum, auto
import uuid

class Side(Enum):
    White = 1
    Black = 2

class PieceType(Enum):
    SUI = auto()
    TAISHO = auto()
    CHUJO = auto()
    SHOUSHO = auto()
    SAMURAI = auto()
    YARI = auto()
    KIBA = auto()
    SHINOBI = auto()
    TORIDE = auto()
    HYOU = auto()
    YUMI = auto()
    TSUTSU = auto()
    OHDSUTSU = auto()
    BOUSHO = auto()

PIECES_NAME: dict[PieceType, str] = {
    PieceType.SUI: "帥",
    PieceType.TAISHO: "大",
    PieceType.CHUJO: "中",
    PieceType.SHOUSHO: "小",
    PieceType.SAMURAI: "侍",
    PieceType.YARI: "槍",
    PieceType.KIBA: "馬",
    PieceType.SHINOBI: "忍",
    PieceType.TORIDE: "砦",
    PieceType.HYOU: "兵",
    PieceType.YUMI: "弓",
    PieceType.TSUTSU: "筒",
    PieceType.OHDSUTSU: "砲",
    PieceType.BOUSHO: "謀"
}

PIECE_COUNTS: dict[PieceType, int] = {
    PieceType.SUI: 1,
    PieceType.TAISHO: 1,
    PieceType.CHUJO: 1,
    PieceType.SHOUSHO: 2,
    PieceType.SAMURAI: 2,
    PieceType.YARI: 3,
    PieceType.KIBA: 2,
    PieceType.SHINOBI: 2,
    PieceType.TORIDE: 2,
    PieceType.HYOU: 4,
    PieceType.YUMI: 2,
    PieceType.TSUTSU: 1,
    PieceType.OHDSUTSU: 1,
    PieceType.BOUSHO: 1
}

class Loc(Enum):
    IN_HAND = auto()
    ON_BOARD = auto()
    CAPTURED = auto()
    DEAD = auto()

class MoveType(Enum):
    LINE = auto()
    JUMP = auto()
    STEP = auto()

@dataclass
class MovePattern:
    move_type: MoveType
    dx: int
    dy: int
    limit: int = None  # Noneなら無制限、整数ならその数まで

@dataclass
class Piece:
    piece_type: PieceType
    color: Side
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def movement(self) -> list[MovePattern]:
        t = self.piece_type
        pats: list[MovePattern] = []
        if t == PieceType.SUI:
            pats += [MovePattern(MoveType.STEP, dx, dy)
                    for dx,dy in [(-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(-1,1),(0,1),(1,1)]]
        elif t == PieceType.TAISHO:
            pats += [MovePattern(MoveType.LINE, dx, dy)   # 縦横は無制限
                    for dx,dy in [(1,0),(0,-1),(-1,0),(0,1)]]
            pats += [MovePattern(MoveType.STEP, dx, dy)   # 斜めは1歩
                    for dx,dy in [(-1,-1),(1,-1),(-1,1),(1,1)]]
        elif t == PieceType.CHUJO:
            pats += [MovePattern(MoveType.LINE, dx, dy)   # 斜めは無制限
                    for dx,dy in [(-1,-1),(1,-1),(-1,1),(1,1)]]
            pats += [MovePattern(MoveType.STEP, dx, dy)   # 縦横は1歩
                    for dx,dy in [(0,-1),(-1,0),(1,0),(0,1)]]
        elif t == PieceType.SHOUSHO:
            pats += [MovePattern(MoveType.STEP, dx, dy)
                    for dx,dy in [(-1,-1),(0,-1),(1,-1),(-1,0),(1,0),(0,1)]]
        elif t == PieceType.SAMURAI:
            pats += [MovePattern(MoveType.STEP, dx, dy)
                    for dx,dy in [(-1,-1),(0,-1),(1,-1),(0,1)]]
        elif t == PieceType.YARI:
            # 最大2歩まで”前進（中間マス遮断を効かせるためLINE+limit=2）
            pats += [MovePattern(MoveType.LINE, 0, 1, limit=2)]
            # 後ろ1、斜め前1は通常のSTEP
            pats += [MovePattern(MoveType.STEP, dx, dy) 
                    for dx,dy in [(-1,-1),(1,-1),(0,-1)]]
        elif t == PieceType.KIBA:
            pats += [MovePattern(MoveType.LINE, dx, dy, limit=2)
                    for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]]
        elif t == PieceType.SHINOBI:
            pats += [MovePattern(MoveType.LINE, dx, dy, limit=2)
                    for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]]
        elif t == PieceType.TORIDE:
            pats += [MovePattern(MoveType.STEP, dx, dy)
                    for dx, dy in [(0, -1), (-1, 0), (1, 0), (-1, 1), (1, 1)]]
        elif t == PieceType.HYOU:
            pats += [MovePattern(MoveType.STEP, dx, dy) for dx, dy in [(0, -1), (0, 1)]]
        elif t == PieceType.YUMI:
            pats += [MovePattern(MoveType.JUMP, dx, dy) for dx, dy in [(-1, -2), (0, -2), (1, -2)]]
            pats += [MovePattern(MoveType.STEP, dx, dy) for dx, dy in [(0, 1)]]
        elif t == PieceType.TSUTSU:
            pats += [MovePattern(MoveType.JUMP, dx, dy) for dx, dy in [(0, -2)]]
            pats += [MovePattern(MoveType.STEP, dx, dy) for dx, dy in [(-1, 1), (1, 1)]]
        elif t == PieceType.OHDSUTSU:
            pats += [MovePattern(MoveType.JUMP, dx, dy) for dx, dy in [(-0, -2)]]
            pats += [MovePattern(MoveType.STEP, dx, dy) for dx, dy in [(-1, 0), (1, 0), (0, 1)]]
        elif t == PieceType.BOUSHO:
            pats += [MovePattern(MoveType.STEP, dx, dy) for dx, dy in [(-1, -1), (1, -1), (0, 1)]]
        if self.color == Side.Black:
            pats = [MovePattern(p.move_type, -p.dx, -p.dy, p.limit) for p in pats]
        return pats
