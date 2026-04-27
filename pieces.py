"""軍議 (Gungi) の駒定義。

座標規約:
    盤面は (x, y) で表す。x は列 0..8、y は行 0..8。
    白の陣は y = 0,1,2、黒の陣は y = 6,7,8。
    白視点で +y 方向が相手陣 (= 前進方向)。
    本モジュール内の全可動パターンは白視点 "+y = 前進" で定義し、
    Piece.movement() の末尾で黒駒なら (dx, dy) -> (-dx, -dy) に反転する。

ツケ (段積み) の表現:
    Piece.level は 0..2。level=0 が 1段目 (地上)、level=2 が 3段目。
    段が上がると可動域が変わるため _MOVE_TABLE[(piece_type, level)] で管理する。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto


class Side(Enum):
    White = 1
    Black = 2

    def opponent(self) -> "Side":
        return Side.Black if self is Side.White else Side.White


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
    PieceType.BOUSHO: "謀",
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
    PieceType.BOUSHO: 1,
}


class DifficultyLevel(Enum):
    BEGINNER = auto()      # 入門: ツケ2段まで, 特殊駒 (弓/筒/砲/謀) なし
    INTERMEDIATE = auto()  # 中級: ツケ3段, 特殊駒あり, 新あり
    ADVANCED = auto()      # 上級: フルルール


class Loc(Enum):
    IN_HAND = auto()   # 手駒 (初期配置で未使用の予備)
    ON_BOARD = auto()  # 盤上
    CAPTURED = auto()  # 相手に取られ、取った側の「新」用プールへ
    DEAD = auto()      # 死に駒 (再使用不可)


class MoveType(Enum):
    LINE = auto()  # 走り: 途中に駒があれば遮断
    JUMP = auto()  # 跳び: 途中に駒があっても飛び越える
    STEP = auto()  # 1歩: 指定マスに直接移動


@dataclass(frozen=True)
class MovePattern:
    move_type: MoveType
    dx: int
    dy: int
    limit: int | None = None  # None なら無制限 (LINE のみ意味を持つ)


MAX_LEVEL = 2  # ツケは最大 3段 (level 0,1,2)


# ---------------------------------------------------------------------------
# 駒種 × 段数 の可動パターン表
# ---------------------------------------------------------------------------
# 全て白視点 +y = 前進。黒は Piece.movement() で反転する。
# level 1,2 (2段目,3段目) の正確なパターンはルールブック page 8「駒の動き方早見表」
# に全駒分のグリッドがある。以下では level 0 を正確に実装し、
# level 1,2 は level 0 に追加移動を差分で与える形を採る。
# 差分の中身は早見表から順次埋める前提で _LEVEL_DELTA に集約している。
# ---------------------------------------------------------------------------

_MOVE_TABLE: dict[tuple[PieceType, int], list[MovePattern]] = {}


def _step(deltas: list[tuple[int, int]]) -> list[MovePattern]:
    return [MovePattern(MoveType.STEP, dx, dy) for dx, dy in deltas]


def _line(deltas: list[tuple[int, int]], limit: int | None = None) -> list[MovePattern]:
    return [MovePattern(MoveType.LINE, dx, dy, limit) for dx, dy in deltas]


def _jump(deltas: list[tuple[int, int]]) -> list[MovePattern]:
    return [MovePattern(MoveType.JUMP, dx, dy) for dx, dy in deltas]


# 帥 (SUI): 周囲8方向 1歩。帥はツケ不可につき level 1,2 は参照されない想定だが安全に同値。
_SUI = _step([(-1, -1), (0, -1), (1, -1),
              (-1, 0),           (1, 0),
              (-1, 1),  (0, 1),  (1, 1)])

# 大 (TAISHO): 前後左右 無制限 + 斜め 1歩
_TAISHO = _line([(1, 0), (-1, 0), (0, 1), (0, -1)]) + \
          _step([(-1, -1), (1, -1), (-1, 1), (1, 1)])

# 中 (CHUJO): 斜め 無制限 + 縦横 1歩
_CHUJO = _line([(-1, -1), (1, -1), (-1, 1), (1, 1)]) + \
         _step([(0, -1), (0, 1), (-1, 0), (1, 0)])

# 小 (SHOUSHO): 前3斜 + 左右 + 後1
_SHOUSHO = _step([(-1, 1), (0, 1), (1, 1),
                  (-1, 0),         (1, 0),
                           (0, -1)])

# 侍 (SAMURAI): 前3斜 + 後1
_SAMURAI = _step([(-1, 1), (0, 1), (1, 1), (0, -1)])

# 槍 (YARI): 前2走り + 斜前1 + 後1
_YARI = _line([(0, 1)], limit=2) + _step([(-1, 1), (1, 1), (0, -1)])

# 馬 (KIBA): 縦横 2歩走り。要検証 (page 8)。
_KIBA = _line([(0, 1), (0, -1), (1, 0), (-1, 0)], limit=2)

# 忍 (SHINOBI): 斜め 2歩走り
_SHINOBI = _line([(-1, -1), (1, -1), (-1, 1), (1, 1)], limit=2)

# 砦 (TORIDE): 前 + 斜前 + 左右
_TORIDE = _step([(0, 1), (-1, 1), (1, 1), (-1, 0), (1, 0)])

# 兵 (HYOU): 前1 のみ
_HYOU = _step([(0, 1)])

# 弓 (YUMI): 前2跳び3方向 + 後1
_YUMI = _jump([(-1, 2), (0, 2), (1, 2)]) + _step([(0, -1)])

# 筒 (TSUTSU): 前2跳び + 斜後2方向
_TSUTSU = _jump([(0, 2)]) + _step([(-1, -1), (1, -1)])

# 砲 (OHDSUTSU): 前2跳び + 左右 + 後1
_OHDSUTSU = _jump([(0, 2)]) + _step([(-1, 0), (1, 0), (0, -1)])

# 謀 (BOUSHO): ベースは 斜前2 + 後1。Piece.transform_as が設定されていればその駒種の動きも加算。
_BOUSHO = _step([(-1, 1), (1, 1), (0, -1)])


_BASE_PATTERNS: dict[PieceType, list[MovePattern]] = {
    PieceType.SUI: _SUI,
    PieceType.TAISHO: _TAISHO,
    PieceType.CHUJO: _CHUJO,
    PieceType.SHOUSHO: _SHOUSHO,
    PieceType.SAMURAI: _SAMURAI,
    PieceType.YARI: _YARI,
    PieceType.KIBA: _KIBA,
    PieceType.SHINOBI: _SHINOBI,
    PieceType.TORIDE: _TORIDE,
    PieceType.HYOU: _HYOU,
    PieceType.YUMI: _YUMI,
    PieceType.TSUTSU: _TSUTSU,
    PieceType.OHDSUTSU: _OHDSUTSU,
    PieceType.BOUSHO: _BOUSHO,
}

# level 1,2 での追加パターン。空なら level 0 と同じ動き。
# ルールブック page 8 の早見表から順次埋める想定 (TODO)。
_LEVEL_DELTA: dict[tuple[PieceType, int], list[MovePattern]] = {
    # 例: (PieceType.HYOU, 1): _step([(-1, 1), (1, 1)]),  # ツケ1で斜前が加わる等
}


def _build_move_table() -> None:
    for pt, base in _BASE_PATTERNS.items():
        for level in range(MAX_LEVEL + 1):
            delta = _LEVEL_DELTA.get((pt, level), [])
            _MOVE_TABLE[(pt, level)] = list(base) + list(delta)


_build_move_table()


def _mirror(pats: list[MovePattern]) -> list[MovePattern]:
    return [MovePattern(p.move_type, -p.dx, -p.dy, p.limit) for p in pats]


# ---------------------------------------------------------------------------
# Piece
# ---------------------------------------------------------------------------


@dataclass
class Piece:
    piece_type: PieceType
    color: Side
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    location: Loc = Loc.IN_HAND
    level: int = 0
    transform_as: PieceType | None = None  # 謀の変身対象 (相手に取られた駒の種類)

    @property
    def kanji(self) -> str:
        return PIECES_NAME[self.piece_type]

    def movement(self) -> list[MovePattern]:
        if not 0 <= self.level <= MAX_LEVEL:
            raise ValueError(f"invalid level: {self.level}")
        pats = list(_MOVE_TABLE[(self.piece_type, self.level)])
        if self.piece_type is PieceType.BOUSHO and self.transform_as is not None:
            pats.extend(_MOVE_TABLE[(self.transform_as, self.level)])
        if self.color is Side.Black:
            pats = _mirror(pats)
        return pats

    def can_be_stacked(self) -> bool:
        """この駒の上にツケ (stack) できるか。帥の上には置けない。"""
        return self.piece_type is not PieceType.SUI

    def can_stack_self(self) -> bool:
        """この駒自身をツケる (= 段を上げる) ことが許されるか。帥はツケ不可。"""
        return self.piece_type is not PieceType.SUI

    def __repr__(self) -> str:
        tag = self.color.name[0] + self.kanji
        return f"{tag}(L{self.level})"
