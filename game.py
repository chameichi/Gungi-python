"""軍議のゲーム層。

Board は局面の物理状態だけを持つ。Game はターン管理・手駒・勝敗判定・
千日手検出・難易度設定などのルール層を担う。
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any

from board import MAX_STACK_HEIGHT, Board
from pieces import (
    DifficultyLevel,
    Loc,
    PIECE_COUNTS,
    Piece,
    PieceType,
    Side,
)


class ActionType(Enum):
    MOVE = auto()    # 盤上の駒を移動 (空マスへ、または敵駒を取る)
    STACK = auto()   # 盤上の駒を別スタックの上にツケる
    ARATA = auto()   # 手駒 or 捕獲駒を盤上に打つ (新)


class GamePhase(Enum):
    PLACEMENT = auto()  # 布陣段階 (中級/上級のみ; 自陣に自駒を交互配置)
    PLAY = auto()        # 対局段階
    FINISHED = auto()    # 対局終了 (帥捕獲)


@dataclass(frozen=True)
class Action:
    type: ActionType
    src: tuple[int, int] | None = None   # MOVE / STACK で指定
    dst: tuple[int, int] = (0, 0)
    hand_piece_id: str | None = None     # ARATA で指定 (手駒の id)


@dataclass
class GameConfig:
    difficulty: DifficultyLevel = DifficultyLevel.ADVANCED

    @property
    def max_level(self) -> int:
        # 入門: ツケ2段まで → level 0,1 のみ。中級/上級: level 0,1,2
        return 1 if self.difficulty is DifficultyLevel.BEGINNER else 2

    @property
    def allow_arata(self) -> bool:
        return self.difficulty is not DifficultyLevel.BEGINNER

    @property
    def allowed_pieces(self) -> set[PieceType]:
        if self.difficulty is DifficultyLevel.BEGINNER:
            return {pt for pt in PIECE_COUNTS if pt not in {
                PieceType.YUMI, PieceType.TSUTSU,
                PieceType.OHDSUTSU, PieceType.BOUSHO,
            }}
        return set(PIECE_COUNTS)

    @property
    def allow_transform(self) -> bool:
        return self.difficulty is DifficultyLevel.ADVANCED


# ---------------------------------------------------------------------------
# 初期配置
# ---------------------------------------------------------------------------
# 白側 (y=0..2) の盤上配置。黒側は (x, 8-y) に鏡写し。
# ルール準拠: 盤上 13駒 + 手駒 12駒 で計 25駒。
# 盤上配置はユーザ提供の写真から起こしたもので、ルールブック page 10 の例と
# 一致するかは要再確認。
_WHITE_INITIAL_BOARD: list[tuple[PieceType, int, int]] = [
    # y=0 (自陣最後列): 大 帥 中
    (PieceType.TAISHO, 3, 0),
    (PieceType.SUI, 4, 0),
    (PieceType.CHUJO, 5, 0),

    # y=1: 忍 弓 槍 弓 馬
    (PieceType.SHINOBI, 2, 1),
    (PieceType.YUMI, 3, 1),
    (PieceType.YARI, 4, 1),
    (PieceType.YUMI, 5, 1),
    (PieceType.KIBA, 6, 1),

    # y=2 (自陣最前列): 砦 侍 兵 侍 砦
    (PieceType.TORIDE, 1, 2),
    (PieceType.SAMURAI, 2, 2),
    (PieceType.HYOU, 4, 2),
    (PieceType.SAMURAI, 6, 2),
    (PieceType.TORIDE, 7, 2),
]

# 残り 12駒は手駒として開始 (新で打てる)
_WHITE_INITIAL_HAND: list[PieceType] = [
    PieceType.SHOUSHO, PieceType.SHOUSHO,
    PieceType.YARI, PieceType.YARI,
    PieceType.SHINOBI,
    PieceType.HYOU, PieceType.HYOU, PieceType.HYOU,
    PieceType.KIBA,
    PieceType.TSUTSU,
    PieceType.OHDSUTSU,
    PieceType.BOUSHO,
]


def _validate_initial() -> None:
    from collections import Counter
    counts = Counter(pt for pt, _, _ in _WHITE_INITIAL_BOARD)
    for pt in _WHITE_INITIAL_HAND:
        counts[pt] += 1
    for pt, expected in PIECE_COUNTS.items():
        if counts[pt] != expected:
            raise AssertionError(
                f"initial layout has {counts[pt]} {pt.name}, expected {expected}"
            )


_validate_initial()


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------


@dataclass
class Game:
    config: GameConfig = field(default_factory=GameConfig)
    board: Board = field(default_factory=Board)
    turn: Side = Side.White
    captured_by: dict[Side, list[Piece]] = field(default_factory=lambda: {Side.White: [], Side.Black: []})
    hand: dict[Side, list[Piece]] = field(default_factory=lambda: {Side.White: [], Side.Black: []})
    history: list[str] = field(default_factory=list)  # 千日手検出用 局面ハッシュ
    winner: Side | None = None
    move_count: int = 0
    phase: GamePhase = GamePhase.PLAY  # _setup_initial で必要に応じて PLACEMENT に上書き

    # 棋譜ナビゲーション用 (deepcopy したフルステートのリスト)
    _snapshots: list[dict[str, Any]] = field(default_factory=list, repr=False)
    _snap_labels: list[str] = field(default_factory=list, repr=False)
    _cursor: int = 0  # _snapshots 上の現在位置

    def __post_init__(self) -> None:
        if not self.board.grid:
            self._setup_initial()
        self._record_snapshot()
        self._snapshot_full_state(label="開始")

    # ---------------- 棋譜ナビ: undo / redo / 先頭 / 末尾 ----------------

    def _snapshot_full_state(self, label: str = "") -> None:
        """現在の Game 状態を deepcopy で履歴に積む。
        cursor が末尾でなければ未来側を切り捨てた上で append する。"""
        if self._snapshots:
            self._snapshots = self._snapshots[: self._cursor + 1]
            self._snap_labels = self._snap_labels[: self._cursor + 1]
        snap = {
            "board": copy.deepcopy(self.board),
            "captured_by": copy.deepcopy(self.captured_by),
            "hand": copy.deepcopy(self.hand),
            "turn": self.turn,
            "winner": self.winner,
            "move_count": self.move_count,
            "history": list(self.history),
            "phase": self.phase,
        }
        self._snapshots.append(snap)
        self._snap_labels.append(label)
        self._cursor = len(self._snapshots) - 1

    def _restore_snapshot(self, idx: int) -> None:
        snap = self._snapshots[idx]
        self.board = copy.deepcopy(snap["board"])
        self.captured_by = copy.deepcopy(snap["captured_by"])
        self.hand = copy.deepcopy(snap["hand"])
        self.turn = snap["turn"]
        self.winner = snap["winner"]
        self.move_count = snap["move_count"]
        self.history = list(snap["history"])
        self.phase = snap.get("phase", GamePhase.PLAY)
        self._cursor = idx

    def reset(self, config: GameConfig | None = None) -> None:
        """対局を初期局面に戻す。config を渡せば難易度を切替。

        現在の盤面・手駒・捕獲駒・履歴・スナップショットを全て破棄して
        新しい Game と同じ状態に再構築する。
        """
        if config is not None:
            self.config = config
        self.board = Board()
        self.captured_by = {Side.White: [], Side.Black: []}
        self.hand = {Side.White: [], Side.Black: []}
        self.history = []
        self.winner = None
        self.move_count = 0
        self.turn = Side.White
        self.phase = GamePhase.PLAY
        self._snapshots = []
        self._snap_labels = []
        self._cursor = 0
        self._setup_initial()
        self._record_snapshot()
        diff_label = {
            DifficultyLevel.BEGINNER: "初級",
            DifficultyLevel.INTERMEDIATE: "中級",
            DifficultyLevel.ADVANCED: "上級",
        }.get(self.config.difficulty, "")
        phase_label = "布陣" if self.phase is GamePhase.PLACEMENT else "対局"
        head = f"開始 ({diff_label} {phase_label})" if diff_label else "開始"
        self._snapshot_full_state(label=head)

    # ---------------- 布陣段階 (PLACEMENT) ----------------

    @staticmethod
    def _own_territory_y(side: Side, height: int) -> range:
        if side is Side.White:
            return range(0, 3)
        return range(height - 3, height)

    def in_own_territory(self, side: Side, y: int) -> bool:
        return y in self._own_territory_y(side, self.board.height)

    def _count_own_pieces_on_board(self, side: Side) -> int:
        n = 0
        for stack in self.board.grid.values():
            for p in stack:
                if p.color is side:
                    n += 1
        return n

    def apply_placement(self, piece_id: str, x: int, y: int) -> None:
        """布陣段階の駒配置。

        ルール:
        - 自陣のみ、自駒のみ
        - 各プレイヤーの最初の駒は **帥** でなければならない
        - 自駒の上に積むのは可、帥の上には積めない、帥は1段目のみ
        - 配置後も手番は同じ側のまま (好きなだけ置ける)。
          手番交代は finish_placement() で明示的に行う。
        """
        if self.phase is not GamePhase.PLACEMENT:
            raise ValueError("布陣段階ではありません")
        piece = next((p for p in self.hand[self.turn] if p.id == piece_id), None)
        if piece is None:
            raise ValueError("自分の手駒に該当する駒がありません")
        if not self.board.in_bounds(x, y):
            raise ValueError(f"盤外: ({x},{y})")
        if not self.in_own_territory(self.turn, y):
            raise ValueError("自陣にしか置けません")

        # 帥から配置するルール
        if (
            self._count_own_pieces_on_board(self.turn) == 0
            and piece.piece_type is not PieceType.SUI
        ):
            raise ValueError("最初の配置は帥から行ってください")

        h = self.board.height_at(x, y)
        if h >= MAX_STACK_HEIGHT:
            raise ValueError("段数上限に達しています")
        if h > self.config.max_level:
            raise ValueError("難易度の段数上限を超えます")
        top = self.board.top_piece(x, y)
        if top is not None and top.color is not self.turn:
            raise ValueError("自駒の上にしか積めません")
        if top is not None and not top.can_be_stacked():
            raise ValueError("帥の上には積めません")
        if piece.piece_type is PieceType.SUI and h > 0:
            raise ValueError("帥は1段目にのみ置けます")

        self.hand[self.turn].remove(piece)
        self.board.place_initial(piece, x, y)
        side_mark = "▲" if self.turn is Side.White else "△"
        label = f"{side_mark}{piece.kanji} 布陣→({x},{y})"
        # 手番は交代しない (同じプレイヤーが好きなだけ置く)
        self._snapshot_full_state(label=label)

    def finish_placement(self) -> None:
        """配置完了ボタン処理。

        - 先手 (白) の手番中に押された場合 → 白の帥が置かれていれば
          後手 (黒) の配置フェーズに移行 (PLACEMENT のまま、turn を黒に)
        - 後手 (黒) の手番中に押された場合 → 黒の帥が置かれていて、
          かつ両陣の帥がアタリでなければ、対局段階 (PLAY) に移行し
          turn を白 (先手) に戻す
        """
        if self.phase is not GamePhase.PLACEMENT:
            raise ValueError("既に対局段階です")
        side = self.turn
        side_label = "白 (先手)" if side is Side.White else "黒 (後手)"
        if self.board.find_sui(side) is None:
            raise ValueError(f"{side_label}の帥が未配置です")

        if side is Side.White:
            # 先手の配置が完了 → 後手の配置フェーズへ
            self.turn = Side.Black
            self._snapshot_full_state(label="先手 配置完了 / 後手の配置")
            return

        # 後手の配置完了 → 両陣帥アタリ確認 → 対局開始
        if self.is_sui_attacked(Side.White):
            raise ValueError(
                "白の帥にアタリが掛かっています。配置を見直してください"
            )
        if self.is_sui_attacked(Side.Black):
            raise ValueError(
                "黒の帥にアタリが掛かっています。配置を見直してください"
            )
        self.phase = GamePhase.PLAY
        self.turn = Side.White
        self._snapshot_full_state(label="後手 配置完了 / 対局開始")

    def is_sui_attacked(self, side: Side) -> bool:
        """side の帥が、相手駒の最上段から取られる位置にあるか。"""
        sui_coord = self.board.find_sui(side)
        if sui_coord is None:
            return False
        opponent = side.opponent()
        for (x, y), stack in self.board.grid.items():
            if not stack:
                continue
            top = stack[-1]
            if top.color is not opponent:
                continue
            if sui_coord in self.board.destinations_from(x, y):
                return True
        return False

    def can_undo(self) -> bool:
        return self._cursor > 0

    def can_redo(self) -> bool:
        return self._cursor < len(self._snapshots) - 1

    def undo(self) -> bool:
        if not self.can_undo():
            return False
        self._restore_snapshot(self._cursor - 1)
        return True

    def redo(self) -> bool:
        if not self.can_redo():
            return False
        self._restore_snapshot(self._cursor + 1)
        return True

    def goto_start(self) -> None:
        if self._snapshots:
            self._restore_snapshot(0)

    def goto_end(self) -> None:
        if self._snapshots:
            self._restore_snapshot(len(self._snapshots) - 1)

    # ---------------- 局面編集 ----------------

    def edit_place(
        self, piece_type: PieceType, color: Side, x: int, y: int
    ) -> None:
        """指定マスのスタックの上に駒を 1 枚配置 (バリデーション最小)。"""
        if not self.board.in_bounds(x, y):
            raise ValueError(f"out of bounds: ({x},{y})")
        if self.board.height_at(x, y) >= MAX_STACK_HEIGHT:
            raise ValueError("stack already at max height")
        piece = Piece(piece_type=piece_type, color=color)
        self.board.place_initial(piece, x, y)
        self.winner = None
        self._snapshot_full_state(label="編集")

    def edit_remove_top(self, x: int, y: int) -> None:
        stack = self.board.stack_at(x, y)
        if not stack:
            raise ValueError("empty square")
        stack.pop()
        if not stack:
            del self.board.grid[(x, y)]
        self.winner = None
        self._snapshot_full_state(label="編集")

    def edit_clear_board(self) -> None:
        self.board.grid.clear()
        self.captured_by[Side.White].clear()
        self.captured_by[Side.Black].clear()
        self.winner = None
        self._snapshot_full_state(label="編集")

    def edit_set_turn(self, side: Side) -> None:
        self.turn = side
        self._snapshot_full_state(label="編集")

    def edit_add_to_hand(self, piece_type: PieceType, side: Side) -> None:
        self.hand[side].append(
            Piece(piece_type=piece_type, color=side, location=Loc.IN_HAND)
        )
        self._snapshot_full_state(label="編集")

    def edit_remove_from_hand(self, piece_id: str, side: Side) -> None:
        for p in self.hand[side]:
            if p.id == piece_id:
                self.hand[side].remove(p)
                self._snapshot_full_state(label="編集")
                return
        raise ValueError(f"hand piece not found: {piece_id}")

    def _setup_initial(self) -> None:
        """難易度に応じた初期化。

        - BEGINNER (初級): 既定の初期配置 (盤上11駒 + 手駒9駒)、対局段階で開始。
        - INTERMEDIATE / ADVANCED: 全 25駒 (許容駒種) を手駒に持って布陣段階で開始。
        """
        if self.config.difficulty is DifficultyLevel.BEGINNER:
            self.phase = GamePhase.PLAY
            allowed = self.config.allowed_pieces
            h = self.board.height
            for pt, x, y in _WHITE_INITIAL_BOARD:
                if pt not in allowed:
                    continue
                self.board.place_initial(Piece(piece_type=pt, color=Side.White), x, y)
                self.board.place_initial(
                    Piece(piece_type=pt, color=Side.Black), x, h - 1 - y
                )
            for pt in _WHITE_INITIAL_HAND:
                if pt not in allowed:
                    continue
                self.hand[Side.White].append(
                    Piece(piece_type=pt, color=Side.White, location=Loc.IN_HAND)
                )
                self.hand[Side.Black].append(
                    Piece(piece_type=pt, color=Side.Black, location=Loc.IN_HAND)
                )
            return

        # 中級/上級: 全駒種を手駒に持って布陣からスタート
        self.phase = GamePhase.PLACEMENT
        for pt, count in PIECE_COUNTS.items():
            if pt not in self.config.allowed_pieces:
                continue
            for _ in range(count):
                self.hand[Side.White].append(
                    Piece(piece_type=pt, color=Side.White, location=Loc.IN_HAND)
                )
                self.hand[Side.Black].append(
                    Piece(piece_type=pt, color=Side.Black, location=Loc.IN_HAND)
                )

    # ---------------- スナップショット & 千日手 ----------------

    def snapshot(self) -> str:
        parts: list[str] = [f"t{self.turn.name}"]
        for y in range(self.board.height):
            for x in range(self.board.width):
                stack = self.board.stack_at(x, y)
                if not stack:
                    continue
                cell = ",".join(f"{p.color.name[0]}{p.piece_type.name}" for p in stack)
                parts.append(f"{x}{y}:{cell}")
        for side in (Side.White, Side.Black):
            hand_tally = sorted(p.piece_type.name for p in self.hand[side])
            captured_tally = sorted(p.piece_type.name for p in self.captured_by[side])
            parts.append(f"{side.name}H:{','.join(hand_tally)}")
            parts.append(f"{side.name}C:{','.join(captured_tally)}")
        return "|".join(parts)

    def _record_snapshot(self) -> None:
        self.history.append(self.snapshot())

    def is_sennichite(self) -> bool:
        """同一局面が 4回出現したら千日手。"""
        if not self.history:
            return False
        latest = self.history[-1]
        return self.history.count(latest) >= 4

    # ---------------- アクション適用 ----------------

    def apply(self, action: Action) -> None:
        if self.phase is not GamePhase.PLAY:
            raise ValueError("対局段階ではありません (布陣中の可能性)")
        if self.winner is not None:
            raise ValueError("game already over")

        # 手の説明用に駒情報をスナップ前にキャプチャ
        kanji = self._lookup_kanji(action)
        side_mark = "▲" if self.turn is Side.White else "△"

        if action.type is ActionType.MOVE:
            self._apply_move(action)
        elif action.type is ActionType.STACK:
            self._apply_stack(action)
        elif action.type is ActionType.ARATA:
            self._apply_arata(action)
        else:
            raise ValueError(f"unknown action: {action.type}")

        self.move_count += 1
        self._check_win()
        if self.winner is None:
            self.turn = self.turn.opponent()
            self._record_snapshot()
        self._snapshot_full_state(label=self._describe_action(action, kanji, side_mark))

    def _lookup_kanji(self, action: Action) -> str:
        from pieces import PIECES_NAME
        if action.src is not None:
            top = self.board.top_piece(*action.src)
            return top.kanji if top is not None else "?"
        if action.hand_piece_id is not None:
            for p in self.hand[self.turn] + self.captured_by[self.turn]:
                if p.id == action.hand_piece_id:
                    return p.kanji
        return "?"

    @staticmethod
    def _describe_action(action: Action, kanji: str, side_mark: str) -> str:
        if action.type is ActionType.MOVE and action.src is not None:
            return f"{side_mark}{kanji} ({action.src[0]},{action.src[1]})→({action.dst[0]},{action.dst[1]})"
        if action.type is ActionType.STACK and action.src is not None:
            return f"{side_mark}{kanji} ({action.src[0]},{action.src[1]})ツケ→({action.dst[0]},{action.dst[1]})"
        if action.type is ActionType.ARATA:
            return f"{side_mark}{kanji} 新→({action.dst[0]},{action.dst[1]})"
        return "?"

    def _require_own_top(self, coord: tuple[int, int]) -> Piece:
        piece = self.board.top_piece(*coord)
        if piece is None:
            raise ValueError(f"no piece at {coord}")
        if piece.color is not self.turn:
            raise ValueError(f"not your piece at {coord}")
        return piece

    def _apply_move(self, action: Action) -> None:
        if action.src is None:
            raise ValueError("MOVE requires src")
        piece = self._require_own_top(action.src)
        legal = self.board.destinations_from(*action.src)
        if action.dst not in legal:
            raise ValueError(f"illegal move: {action.src} -> {action.dst}")

        # 移動先に敵駒がいれば捕獲が発生
        captured = self.board.move_top(action.src, action.dst)
        if captured is not None:
            self._bank_captured(captured)

    def _apply_stack(self, action: Action) -> None:
        if action.src is None:
            raise ValueError("STACK requires src")
        piece = self._require_own_top(action.src)
        # stack_on_top は「src の最上段駒を dst の最上段に乗せる」。
        # 移動可能マスに制限はあるか? → 公式は「ツケは1歩の範囲で」という解釈もあれば
        # 「可動範囲内なら任意」という解釈もある。ここでは後者を採り、
        # destinations_from() で通常移動可動なマスを集合として利用する。
        # ただし destinations_from は自駒最上段を除外するので、
        # 自駒/敵駒いずれの最上段にもツケるために「ベクトル同一で top が自駒」も許容する。
        _ = piece
        dests = set(self.board.destinations_from(*action.src))
        # 自駒最上段でツケたいマスを補う
        for d in self._reachable_allowing_own(action.src):
            dests.add(d)
        if action.dst not in dests:
            raise ValueError(f"illegal stack dest: {action.dst}")

        current_level_max = self.config.max_level
        target_after = self.board.height_at(*action.dst)  # 積んだ後の新しい level
        if target_after > current_level_max:
            raise ValueError(f"stack would exceed difficulty max level ({current_level_max})")

        self.board.stack_on_top(action.src, action.dst)

    def _reachable_allowing_own(self, src: tuple[int, int]) -> list[tuple[int, int]]:
        """STACK 用: 自駒最上段マスも含めた可動先。"""
        from pieces import MoveType
        piece = self.board.top_piece(*src)
        if piece is None:
            return []
        sx, sy = src
        out: list[tuple[int, int]] = []
        for pat in piece.movement():
            if pat.move_type is MoveType.STEP or pat.move_type is MoveType.JUMP:
                nx, ny = sx + pat.dx, sy + pat.dy
                if self.board.in_bounds(nx, ny):
                    out.append((nx, ny))
            else:  # LINE
                limit = pat.limit if pat.limit is not None else max(self.board.width, self.board.height)
                nx, ny = sx, sy
                for _ in range(limit):
                    nx += pat.dx
                    ny += pat.dy
                    if not self.board.in_bounds(nx, ny):
                        break
                    out.append((nx, ny))
                    if self.board.top_piece(nx, ny) is not None:
                        break
        return out

    def _apply_arata(self, action: Action) -> None:
        if not self.config.allow_arata:
            raise ValueError("新は現在の難易度では使用できない")
        if action.hand_piece_id is None:
            raise ValueError("ARATA requires hand_piece_id")

        pool = self.hand[self.turn] + self.captured_by[self.turn]
        piece = next((p for p in pool if p.id == action.hand_piece_id), None)
        if piece is None:
            raise ValueError(f"hand piece not found: {action.hand_piece_id}")

        self.board.drop_from_hand(piece, action.dst)

        # 元のコレクションから除去
        for bucket in (self.hand[self.turn], self.captured_by[self.turn]):
            if piece in bucket:
                bucket.remove(piece)
                break

    def _bank_captured(self, captured: Piece) -> None:
        captured.color = self.turn              # 捕獲側の所持に切り替わる (「新」で再利用可)
        captured.location = Loc.CAPTURED
        captured.level = 0
        captured.transform_as = None
        self.captured_by[self.turn].append(captured)

    def _check_win(self) -> None:
        if any(p.piece_type is PieceType.SUI for p in self.captured_by[Side.White]):
            self.winner = Side.White
            return
        if any(p.piece_type is PieceType.SUI for p in self.captured_by[Side.Black]):
            self.winner = Side.Black

    # ---------------- 合法手列挙 (AI 向けの下ごしらえ) ----------------

    def legal_actions(self) -> list[Action]:
        if self.phase is not GamePhase.PLAY:
            return []
        acts: list[Action] = []
        for (x, y), stack in self.board.grid.items():
            if not stack or stack[-1].color is not self.turn:
                continue
            src = (x, y)
            for dst in self.board.destinations_from(x, y):
                acts.append(Action(ActionType.MOVE, src=src, dst=dst))
            for dst in self._reachable_allowing_own(src):
                if self.board.height_at(*dst) == 0:
                    continue
                if self.board.height_at(*dst) >= MAX_STACK_HEIGHT:
                    continue
                if self.board.height_at(*dst) > self.config.max_level:
                    continue
                top = self.board.top_piece(*dst)
                if top is not None and not top.can_be_stacked():
                    continue
                if not stack[-1].can_stack_self():
                    continue
                acts.append(Action(ActionType.STACK, src=src, dst=dst))
        if self.config.allow_arata:
            pool = self.hand[self.turn] + self.captured_by[self.turn]
            for piece in pool:
                if piece.piece_type is PieceType.SUI:
                    continue
                for y in range(self.board.height):
                    for x in range(self.board.width):
                        dst = (x, y)
                        try:
                            # 実 apply なしで事前検証するのは面倒なので
                            # 盤面制約だけラフに確認
                            h = self.board.height_at(*dst)
                            if h >= 2:
                                continue
                            top = self.board.top_piece(*dst)
                            if top is not None and (
                                top.color is piece.color or not top.can_be_stacked()
                            ):
                                continue
                            acts.append(Action(ActionType.ARATA, dst=dst, hand_piece_id=piece.id))
                        except ValueError:
                            continue
        return acts


# ---------------------------------------------------------------------------
# 設定ファイル読み込み
# ---------------------------------------------------------------------------


def load_config(path: str | Path | None = None) -> GameConfig:
    """JSON からゲーム設定を読み込む。path 省略時はプロジェクト直下の settings.json。"""
    if path is None:
        path = Path(__file__).parent / "settings.json"
    path = Path(path)
    if not path.exists():
        return GameConfig()
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    raw = data.get("difficulty_level") or data.get("difficulty") or "ADVANCED"
    try:
        diff = DifficultyLevel[raw.upper()]
    except KeyError as e:
        raise ValueError(f"unknown difficulty: {raw}") from e
    return GameConfig(difficulty=diff)
