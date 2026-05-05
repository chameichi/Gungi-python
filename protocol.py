"""UGI - Universal Gungi Interface (v2)

将棋の USI に相当する、Gungi のエンジン-GUI 通信プロトコル。

================================================================
レイヤ構造
================================================================
    coreロジック   : pieces.py / board.py / game.py
        Game 状態とルール検証 (アタリ判定・帥配置・段差比較など)
    プロトコル変換 : protocol.py  ← このファイル
        UGI 文字列 ⇄ Game 状態
    AI エンジン    : 将来別ファイル (engine_*.py 等)
        UGI を介して GUI と通信する思考モジュール

================================================================
1. 駒コード
================================================================
    Su 帥   Ta 大   Cj 中   Sh 小   Sm 侍   Ya 槍   Ki 馬
    Sn 忍   To 砦   Hy 兵   Ym 弓   Tt 筒   Od 砲   Bo 謀

    色プレフィクス: 'w' (先手・白) / 'b' (後手・黒)
    例: wSu = 先手の帥, bTa = 後手の大

================================================================
2. 座標
================================================================
    x, y は 0..8 の 1 桁。連結して `xy` で 1 マスを表す。
    例: '42' = (col 4, row 2)

================================================================
3. アクション記法 (USI 準拠)
================================================================
    移動 (MOVE)         : <sx><sy><dx><dy>      例: 4243
    ツケ (STACK)        : <sx><sy><dx><dy>+     例: 4243+
    打ち (ARATA/置)     : <駒>*<dx><dy>          例: Hy*43
    配置完了 (済み)     : done
    投了                : resign
    無手 (debug)        : null

    USI の "成り (+)" を Gungi では「ツケ」choice に流用。
    打ち (`*`) は phase で意味が決まる:
      PLACEMENT 中 → 布陣として手駒を盤に置く
      PLAY 中     → 新 (アラタ) として手駒/捕獲駒を打つ
    どちらも "手駒から盤上へ" の意味なので USI 流に同記法。

================================================================
4. GFEN (Gungi Forsyth-Edwards Notation)
================================================================
    <board> <turn> <phase> <hand_w> <hand_b> <cap_w> <cap_b> <done_w> <done_b> <ply>

    board: 9 段 (y=8 から y=0) を '/' で区切る。各段は 9 マスを '|' 区切り。
        マスが空: 連続空きマス数 (1..9)
        マスに駒: <col><type> (3 字)、スタックは '+' で連結 (下から上へ)
        例: 4|wTa|wSu|wCj|3
            → 空き4・大・帥・中・空き3 で計 9 マス

    turn: w | b
    phase: pl (placement) | pa (play) | fi (finished)
    hand_w/hand_b: 駒種コード ',' 区切り、空は '-'
    cap_w/cap_b : 同上
    done_w/done_b: 0 | 1
    ply: 整数

    特殊形:
      startpos:intro          入門編 (初期配置①)
      startpos:beginner       初級編 (初期配置②)
      startpos:intermediate   中級編 (空盤 PLACEMENT)
      startpos:advanced       上級編 (空盤 PLACEMENT)
      startpos                = startpos:intro

================================================================
5. UGI コマンド
================================================================
    GUI → エンジン:
      ugi                     プロトコル開始
      isready                 準備確認
      uginewgame              新規対局通知
      position <spec> [moves <m1> <m2> ...]
                              spec = startpos[:diff] | gfen <gfen10fields>
      go [movetime <ms>] [depth <n>] [nodes <n>] [infinite]
      stop                    思考停止 (現時点の最善手を返す)
      setoption name <k> value <v>
      ponderhit
      quit

    エンジン → GUI:
      id name <name>
      id author <author>
      ugiok
      readyok
      option name <k> type <t> default <v> [min <m>] [max <M>] [var <v1> ...]
      info depth <n> score cp <eval> nodes <n> time <ms> pv <m1> <m2> ...
      bestmove <move> [ponder <move>]

================================================================
6. セッション例
================================================================
    GUI:    ugi
    Engine: id name SampleEngine
            id author Someone
            ugiok
    GUI:    isready
    Engine: readyok
    GUI:    uginewgame
    GUI:    position startpos:intro moves 4243 4645
    GUI:    go movetime 1000
    Engine: info depth 3 score cp 12 pv 3424
            bestmove 3424

================================================================
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from board import Board, MAX_STACK_HEIGHT
from game import Action, ActionType, Game, GameConfig, GamePhase
from pieces import (
    DifficultyLevel,
    Loc,
    PIECE_COUNTS,
    Piece,
    PieceType,
    Side,
)


# ---------------------------------------------------------------------------
# コードテーブル
# ---------------------------------------------------------------------------

PIECE_CODE: dict[PieceType, str] = {
    PieceType.SUI: "Su",
    PieceType.TAISHO: "Ta",
    PieceType.CHUJO: "Cj",
    PieceType.SHOUSHO: "Sh",
    PieceType.SAMURAI: "Sm",
    PieceType.YARI: "Ya",
    PieceType.KIBA: "Ki",
    PieceType.SHINOBI: "Sn",
    PieceType.TORIDE: "To",
    PieceType.HYOU: "Hy",
    PieceType.YUMI: "Ym",
    PieceType.TSUTSU: "Tt",
    PieceType.OHDSUTSU: "Od",
    PieceType.BOUSHO: "Bo",
}
CODE_PIECE: dict[str, PieceType] = {v: k for k, v in PIECE_CODE.items()}

SIDE_CODE: dict[Side, str] = {Side.White: "w", Side.Black: "b"}
CODE_SIDE: dict[str, Side] = {v: k for k, v in SIDE_CODE.items()}

PHASE_CODE: dict[GamePhase, str] = {
    GamePhase.PLACEMENT: "pl",
    GamePhase.PLAY: "pa",
    GamePhase.FINISHED: "fi",
}
CODE_PHASE: dict[str, GamePhase] = {v: k for k, v in PHASE_CODE.items()}

DIFFICULTY_CODE: dict[str, DifficultyLevel] = {
    "intro": DifficultyLevel.INTRODUCTORY,
    "beginner": DifficultyLevel.BEGINNER,
    "intermediate": DifficultyLevel.INTERMEDIATE,
    "advanced": DifficultyLevel.ADVANCED,
}


# ---------------------------------------------------------------------------
# Piece serialization
# ---------------------------------------------------------------------------

def piece_code(piece: Piece) -> str:
    """Piece -> 'wSu' のような 3 字コード。"""
    return SIDE_CODE[piece.color] + PIECE_CODE[piece.piece_type]


def parse_piece(code: str) -> Piece:
    """'wSu' -> Piece (level=0, location=ON_BOARD)。"""
    if len(code) != 3:
        raise ValueError(f"piece code must be 3 chars, got {code!r}")
    return Piece(
        piece_type=CODE_PIECE[code[1:]],
        color=CODE_SIDE[code[0]],
    )


# ---------------------------------------------------------------------------
# GFEN: position serialization
# ---------------------------------------------------------------------------

_RANK_SEP = "/"
_CELL_SEP = "|"
_STACK_SEP = "+"


def encode_board(board: Board) -> str:
    """Board → GFEN board セクション。"""
    ranks: list[str] = []
    for y in range(board.height - 1, -1, -1):
        cells: list[str] = []
        empty_run = 0
        for x in range(board.width):
            stack = board.stack_at(x, y)
            if not stack:
                empty_run += 1
                continue
            if empty_run > 0:
                cells.append(str(empty_run))
                empty_run = 0
            cells.append(_STACK_SEP.join(piece_code(p) for p in stack))
        if empty_run > 0:
            cells.append(str(empty_run))
        ranks.append(_CELL_SEP.join(cells))
    return _RANK_SEP.join(ranks)


def decode_board(s: str, board: Board) -> None:
    """GFEN board を board に書き戻す (board は事前にクリアされていること)。"""
    rank_strs = s.split(_RANK_SEP)
    if len(rank_strs) != board.height:
        raise ValueError(f"expected {board.height} ranks, got {len(rank_strs)}")
    for screen_row, rank in enumerate(rank_strs):
        y = board.height - 1 - screen_row
        x = 0
        for token in rank.split(_CELL_SEP):
            if token.isdigit():
                x += int(token)
                continue
            for code in token.split(_STACK_SEP):
                board.place_initial(parse_piece(code), x, y)
            x += 1
        if x != board.width:
            raise ValueError(
                f"rank y={y} has {x} cells, expected {board.width}"
            )


def _piece_list_str(pieces: list[Piece]) -> str:
    if not pieces:
        return "-"
    return ",".join(PIECE_CODE[p.piece_type] for p in pieces)


def _parse_piece_list(
    s: str, side: Side, location: Loc
) -> list[Piece]:
    if s == "-" or s == "":
        return []
    out: list[Piece] = []
    for code in s.split(","):
        if not code:
            continue
        out.append(Piece(
            piece_type=CODE_PIECE[code], color=side, location=location,
        ))
    return out


def encode_gfen(game: Game) -> str:
    """Game の現状態を GFEN 文字列に。"""
    parts = [
        encode_board(game.board),
        SIDE_CODE[game.turn],
        PHASE_CODE[game.phase],
        _piece_list_str(game.hand[Side.White]),
        _piece_list_str(game.hand[Side.Black]),
        _piece_list_str(game.captured_by[Side.White]),
        _piece_list_str(game.captured_by[Side.Black]),
        "1" if game._placement_done[Side.White] else "0",
        "1" if game._placement_done[Side.Black] else "0",
        str(game.move_count),
    ]
    return " ".join(parts)


def decode_gfen(gfen: str, config: GameConfig | None = None) -> Game:
    """GFEN 文字列から Game を構築。

    'startpos' / 'startpos:<diff>' は規定の開始局面を返す。
    """
    if gfen.startswith("startpos"):
        diff = "intro"
        if ":" in gfen:
            diff = gfen.split(":", 1)[1]
        if diff not in DIFFICULTY_CODE:
            raise ValueError(f"unknown difficulty: {diff!r}")
        return Game(config=GameConfig(difficulty=DIFFICULTY_CODE[diff]))

    parts = gfen.split(" ")
    if len(parts) != 10:
        raise ValueError(
            f"GFEN must have 10 fields, got {len(parts)}: {gfen!r}"
        )
    board_s, turn_s, phase_s, hw, hb, cw, cb, dw, db, ply_s = parts

    game = Game(config=config or GameConfig())
    # 既定の初期化を上書きして空状態に
    game.board = Board()
    game.hand = {Side.White: [], Side.Black: []}
    game.captured_by = {Side.White: [], Side.Black: []}
    game.history = []
    game._snapshots = []
    game._snap_labels = []
    game._cursor = 0
    game.winner = None

    decode_board(board_s, game.board)
    game.turn = CODE_SIDE[turn_s]
    game.phase = CODE_PHASE[phase_s]
    game.hand[Side.White] = _parse_piece_list(hw, Side.White, Loc.IN_HAND)
    game.hand[Side.Black] = _parse_piece_list(hb, Side.Black, Loc.IN_HAND)
    game.captured_by[Side.White] = _parse_piece_list(
        cw, Side.White, Loc.CAPTURED
    )
    game.captured_by[Side.Black] = _parse_piece_list(
        cb, Side.Black, Loc.CAPTURED
    )
    game._placement_done = {
        Side.White: dw == "1",
        Side.Black: db == "1",
    }
    game.move_count = int(ply_s)

    # スナップショット履歴を初期化
    game._record_snapshot()
    game._snapshot_full_state(label="from-gfen")
    return game


# ---------------------------------------------------------------------------
# Action serialization
# ---------------------------------------------------------------------------

DONE = "done"
RESIGN = "resign"
NULL = "null"

# USI 流儀: 盤上手は座標、ツケ choice は + 接尾辞、打ちは *
_BOARD_RE = re.compile(r"^([0-8])([0-8])([0-8])([0-8])(\+?)$")
_DROP_RE = re.compile(r"^([A-Z][a-z])\*([0-8])([0-8])$")


@dataclass(frozen=True)
class ParsedMove:
    """UGI 文字列を分解した中間表現。Game に適用するメソッド付き。

    kind: 'move' / 'stack' / 'drop' / 'done' / 'resign' / 'null'
    'drop' は phase で PLACEMENT (布陣) / ARATA (新) を判別。
    """

    kind: str
    src: tuple[int, int] | None = None
    dst: tuple[int, int] | None = None
    piece_type: PieceType | None = None

    def apply(self, game: Game) -> None:
        if self.kind == "done":
            game.finish_placement()
            return
        if self.kind == "resign":
            game.winner = game.turn.opponent()
            game.phase = GamePhase.FINISHED
            return
        if self.kind == "null":
            return

        if self.kind == "move":
            assert self.src is not None and self.dst is not None
            game.apply(Action(ActionType.MOVE, src=self.src, dst=self.dst))
            return
        if self.kind == "stack":
            assert self.src is not None and self.dst is not None
            game.apply(Action(ActionType.STACK, src=self.src, dst=self.dst))
            return
        if self.kind == "drop":
            assert self.piece_type is not None and self.dst is not None
            if game.phase is GamePhase.PLACEMENT:
                target = next(
                    (p for p in game.hand[game.turn]
                     if p.piece_type is self.piece_type),
                    None,
                )
                if target is None:
                    raise ValueError(f"no {self.piece_type.name} in hand")
                game.apply_placement(target.id, *self.dst)
            elif game.phase is GamePhase.PLAY:
                pool = game.hand[game.turn] + game.captured_by[game.turn]
                target = next(
                    (p for p in pool if p.piece_type is self.piece_type),
                    None,
                )
                if target is None:
                    raise ValueError(
                        f"no {self.piece_type.name} in hand/captured"
                    )
                game.apply(Action(
                    ActionType.ARATA, dst=self.dst, hand_piece_id=target.id,
                ))
            else:
                raise ValueError("drop not allowed in this phase")
            return

        raise ValueError(f"unknown move kind: {self.kind}")


def encode_move(action: Action, game: Game | None = None) -> str:
    """Action を UGI 文字列に変換。

    ARATA の場合は Game を渡す必要がある (piece_id から駒種を引くため)。
    """
    if action.type is ActionType.MOVE:
        sx, sy = action.src or (0, 0)
        dx, dy = action.dst
        return f"{sx}{sy}{dx}{dy}"
    if action.type is ActionType.STACK:
        sx, sy = action.src or (0, 0)
        dx, dy = action.dst
        return f"{sx}{sy}{dx}{dy}+"
    if action.type is ActionType.ARATA:
        if game is None:
            raise ValueError("encode_move(ARATA, ...) requires game arg")
        pool = game.hand[game.turn] + game.captured_by[game.turn]
        target = next(
            (p for p in pool if p.id == action.hand_piece_id), None
        )
        if target is None:
            raise ValueError("piece id not in hand/captured")
        dx, dy = action.dst
        return f"{PIECE_CODE[target.piece_type]}*{dx}{dy}"
    raise ValueError(f"unsupported action type: {action.type}")


def encode_drop(piece_type: PieceType, dst: tuple[int, int]) -> str:
    """打ち (PLACEMENT/ARATA 共通) を UGI 文字列に。phase は受け手が判別。"""
    return f"{PIECE_CODE[piece_type]}*{dst[0]}{dst[1]}"


def parse_move(s: str) -> ParsedMove:
    """UGI 文字列を ParsedMove に。"""
    s = s.strip()
    if s == DONE:
        return ParsedMove(kind="done")
    if s == RESIGN:
        return ParsedMove(kind="resign")
    if s in (NULL, "nullmove"):
        return ParsedMove(kind="null")

    m = _BOARD_RE.match(s)
    if m:
        sx, sy, dx, dy = (int(g) for g in m.groups()[:4])
        is_stack = m.group(5) == "+"
        return ParsedMove(
            kind="stack" if is_stack else "move",
            src=(sx, sy), dst=(dx, dy),
        )
    m = _DROP_RE.match(s)
    if m:
        code, dx, dy = m.group(1), int(m.group(2)), int(m.group(3))
        if code not in CODE_PIECE:
            raise ValueError(f"unknown piece code: {code}")
        return ParsedMove(
            kind="drop", piece_type=CODE_PIECE[code], dst=(dx, dy),
        )
    raise ValueError(f"unrecognized move: {s!r}")


# ---------------------------------------------------------------------------
# UGI ハンドラの参考実装 (本物のエンジンはこれを継承して search を実装)
# ---------------------------------------------------------------------------


class UGIHandler:
    """`ugi`/`position`/`go` などを処理するエンジン側ハンドラ。

    実 AI エンジンはこれを継承して `search()` を実装する想定。
    本クラスのデフォルト search は単に最初の合法手を返す。
    """

    NAME = "GungiBaseEngine"
    AUTHOR = "unknown"

    def __init__(self) -> None:
        self.game: Game = Game()

    # 派生クラスがオーバーライドする思考メソッド ----------------------

    def search(self, params: dict[str, str]) -> str:
        """次手 (UGI 文字列) を返す。デフォルトは最初の合法手 or done。"""
        if self.game.phase is GamePhase.PLACEMENT:
            return DONE
        legal = self.game.legal_actions()
        if not legal:
            return RESIGN
        return encode_move(legal[0], self.game)

    # コマンドハンドラ ------------------------------------------------

    def cmd_ugi(self, args: list[str]) -> Iterable[str]:
        yield f"id name {self.NAME}"
        yield f"id author {self.AUTHOR}"
        yield "ugiok"

    def cmd_isready(self, args: list[str]) -> Iterable[str]:
        yield "readyok"

    def cmd_uginewgame(self, args: list[str]) -> Iterable[str]:
        self.game = Game()
        return []

    def cmd_position(self, args: list[str]) -> Iterable[str]:
        if not args:
            raise ValueError("position: missing args")
        if args[0].startswith("startpos"):
            self.game = decode_gfen(args[0])
            rest = args[1:]
        elif args[0] == "gfen":
            if len(args) < 11:
                raise ValueError("position gfen: needs 10 fields")
            self.game = decode_gfen(" ".join(args[1:11]))
            rest = args[11:]
        else:
            raise ValueError(f"position: unknown spec {args[0]!r}")
        if rest:
            if rest[0] != "moves":
                raise ValueError("position: expected 'moves' after spec")
            for tok in rest[1:]:
                parse_move(tok).apply(self.game)
        return []

    def cmd_go(self, args: list[str]) -> Iterable[str]:
        params = _kv_pairs(args)
        move = self.search(params)
        yield f"info depth 1 score cp 0 pv {move}"
        yield f"bestmove {move}"

    def cmd_stop(self, args: list[str]) -> Iterable[str]:
        return []

    def cmd_setoption(self, args: list[str]) -> Iterable[str]:
        # 派生クラスで処理する想定。デフォルトは無視。
        return []

    def cmd_quit(self, args: list[str]) -> Iterable[str]:
        return []

    # ディスパッチ ----------------------------------------------------

    def handle(self, line: str) -> Iterable[str]:
        tokens = line.strip().split()
        if not tokens:
            return []
        cmd, *args = tokens
        method = getattr(self, f"cmd_{cmd}", None)
        if method is None:
            return [f"info string unknown command: {cmd}"]
        try:
            return list(method(args))
        except Exception as e:
            return [f"info string error: {e}"]

    def run_repl(self) -> None:
        """stdin/stdout で簡易ループ (デモ用)。"""
        import sys
        for line in sys.stdin:
            for out in self.handle(line):
                print(out, flush=True)
            if line.strip() == "quit":
                break


def _kv_pairs(tokens: list[str]) -> dict[str, str]:
    """`movetime 1000 depth 5` -> {'movetime': '1000', 'depth': '5'}"""
    result = {}
    i = 0
    while i + 1 < len(tokens):
        key, val = tokens[i], tokens[i + 1]
        result[key] = val
        i += 2
    return result


if __name__ == "__main__":
    UGIHandler().run_repl()
