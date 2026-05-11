"""棋譜フォーマットの共通インターフェースと実装。

GUI 側からは `FORMATS` を QFileDialog のフィルタに渡し、選択された
フィルタ (またはファイル拡張子) から具体的な `KifuFormat` を解決して
`save()` / `load()` を呼ぶ。

実装済:
    GungiTextKifuFormat  : .gungi (PSN/KIF 風のテキスト形式、UTF-8)
    GungiSjisKifuFormat  : .gungi (PSN/KIF 風のテキスト形式、Shift-JIS)
    GsaKifuFormat        : .gsa   (CSA 流の手表記を Gungi 向けに設計)
    JsonKifuFormat       : .json  (既存 protocol.save_game/load_game 形式)
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from game import Game
from pieces import Side
from protocol import (
    KIFU_VERSION,
    PIECE_CODE,
    ParsedMove,
    decode_gfen,
    initial_gfen_of,
    load_game as _json_load_game,
    parse_move,
    save_game as _json_save_game,
)


class KifuFormat(ABC):
    """棋譜 save/load の共通インターフェース。

    サブクラスは extension / description / encoding をクラス属性で宣言し、
    save / load を実装する。
    """

    extension: str = ""        # 先頭の "." は含めない (例: "gungi")
    description: str = ""      # QFileDialog 用説明
    encoding: str = "utf-8"

    @property
    def filter_string(self) -> str:
        return f"{self.description} (*.{self.extension})"

    @abstractmethod
    def save(self, game: Game, path: Path) -> None: ...

    @abstractmethod
    def load(self, path: Path) -> Game: ...


# ---------------------------------------------------------------------------
# Gungi テキスト形式 (PSN/KIF 風)
#
# 例:
#   [Format "Gungi"]
#   [Version "1"]
#   [Date "2026.05.11 20:42:31"]
#   [Difficulty "INTRODUCTORY"]
#   [Result "*"]
#   [InitialGFEN "..."]
#
#   1. Su*40
#   2. Su*48
#   3. done
#   ...
# ---------------------------------------------------------------------------


class GungiTextKifuFormat(KifuFormat):
    extension = "gungi"
    description = "Gungi 棋譜"

    _HEADER_RE = re.compile(r'^\[(\w+)\s+"([^"]*)"\]\s*$')
    _MOVE_RE = re.compile(r'^\s*\d+\.\s*(\S+)\s*$')

    def save(self, game: Game, path: Path) -> None:
        initial_gfen = initial_gfen_of(game)
        difficulty = game.config.difficulty.name
        date = datetime.now().strftime("%Y.%m.%d %H:%M:%S")
        result = self._encode_result(game)

        lines: list[str] = [
            '[Format "Gungi"]',
            f'[Version "{KIFU_VERSION}"]',
            f'[Date "{date}"]',
            f'[Difficulty "{difficulty}"]',
            f'[Result "{result}"]',
            f'[InitialGFEN "{initial_gfen}"]',
            '',
        ]
        for i, mv in enumerate(game.action_log, start=1):
            lines.append(f'{i}. {mv}')
        path.write_text('\n'.join(lines) + '\n', encoding=self.encoding)

    def load(self, path: Path) -> Game:
        raw = self._read_with_encoding_fallback(path)
        headers: dict[str, str] = {}
        moves: list[str] = []
        for raw_line in raw.splitlines():
            line = raw_line.rstrip()
            if not line or line.startswith('#'):
                continue
            m = self._HEADER_RE.match(line)
            if m:
                headers[m.group(1)] = m.group(2)
                continue
            m = self._MOVE_RE.match(line)
            if m:
                moves.append(m.group(1))
                continue
            # 知らない行は寛容に無視

        version = int(headers.get("Version", "1"))
        if version != KIFU_VERSION:
            raise ValueError(f"unsupported kifu version: {version}")
        initial_gfen = headers.get("InitialGFEN")
        if not initial_gfen:
            raise ValueError("missing InitialGFEN header")
        game = decode_gfen(initial_gfen)
        for tok in moves:
            parse_move(tok).apply(game)
        return game

    def _read_with_encoding_fallback(self, path: Path) -> str:
        """self.encoding を最初に試し、UnicodeDecodeError なら UTF-8/SJIS 間で
        もう一方の encoding にフォールバックする。

        .gungi 拡張子が UTF-8 / SJIS で共有されている都合上、ダイアログでの
        フィルタ選択を間違えても読込めるようにするためのお助け処理。
        """
        primary = self.encoding
        fallback = "shift_jis" if primary == "utf-8" else "utf-8"
        try:
            return path.read_text(encoding=primary)
        except UnicodeDecodeError:
            return path.read_text(encoding=fallback)

    @staticmethod
    def _encode_result(game: Game) -> str:
        if game.winner is None:
            return "*"
        return "1-0" if game.winner is Side.White else "0-1"


# ---------------------------------------------------------------------------
# Gungi テキスト (Shift-JIS 版)
#
# 中身は GungiTextKifuFormat と同一仕様。encoding のみ shift_jis。
# 拡張子は同じ "gungi" を共有するため、読込時はダイアログでフィルタを
# 明示的に SJIS 側で選ぶ必要がある (拡張子だけからは UTF-8 と区別不能)。
# ---------------------------------------------------------------------------


class GungiSjisKifuFormat(GungiTextKifuFormat):
    description = "Gungi 棋譜 (SJIS)"
    encoding = "shift_jis"


# ---------------------------------------------------------------------------
# GSA 形式 (Gungi Standard Action) — CSA 流の手表記を Gungi 向けに本格設計
#
# 例:
#   V Gungi-1
#   $EVENT:対局
#   $DATE:2026/05/11 20:42:31
#   $DIFFICULTY:INTRODUCTORY
#   $INITIAL_GFEN:...
#   $RESULT:*
#   %MOVES
#   +0051SU            ← 先手 (4,0) に Su を打つ (from=00 が打ち、1-based)
#   -0059SU            ← 後手 (4,8) に Su を打つ
#   +%DONE
#   -%DONE
#   +4243SH            ← 先手 (3,1) → (3,2) に Sh を移動
#   -4647SH^           ← 後手 (3,5) → (3,6) に Sh をツケ (末尾 ^)
#   +%TORYO
#   %END
#
# 区切りなし密記法 (CSA 流)。座標は 1-based 2 桁。
# Level (スタック高) は明示せず、盤面状態から復元する。
# ---------------------------------------------------------------------------


class GsaKifuFormat(KifuFormat):
    extension = "gsa"
    description = "GSA (Gungi CSA 流)"

    _GSA_VERSION = "Gungi-1"

    # ±AABBPP^?
    _MOVE_RE = re.compile(r'^([+-])(\d{2})(\d{2})([A-Z]{2})(\^?)$')
    # ±%COMMAND
    _CMD_RE = re.compile(r'^([+-])?%([A-Z]+)$')

    _PIECE_TO_UPPER = {pt: code.upper() for pt, code in PIECE_CODE.items()}
    _UPPER_TO_PIECE = {code.upper(): pt for pt, code in PIECE_CODE.items()}

    def save(self, game: Game, path: Path) -> None:
        initial_gfen = initial_gfen_of(game)
        # action_log を 1 手ずつ tracker に適用しながら手番・盤面情報を取り、
        # GSA トークンを生成する (move/stack は src の駒種が必要なため)。
        tracker = decode_gfen(initial_gfen)
        gsa_moves: list[str] = []
        for tok in game.action_log:
            gsa_moves.append(self._encode_token(tok, tracker))
            parse_move(tok).apply(tracker)

        date = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        lines: list[str] = [
            f"V {self._GSA_VERSION}",
            "$EVENT:対局",
            f"$DATE:{date}",
            f"$DIFFICULTY:{game.config.difficulty.name}",
            f"$INITIAL_GFEN:{initial_gfen}",
            f"$RESULT:{self._encode_result(game)}",
            "%MOVES",
        ]
        lines.extend(gsa_moves)
        lines.append("%END")
        path.write_text("\n".join(lines) + "\n", encoding=self.encoding)

    def load(self, path: Path) -> Game:
        raw = path.read_text(encoding=self.encoding)
        headers: dict[str, str] = {}
        gsa_moves: list[str] = []
        in_moves = False
        for raw_line in raw.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("'"):
                continue
            if line == "%MOVES":
                in_moves = True
                continue
            if line == "%END":
                break
            if in_moves:
                gsa_moves.append(line)
                continue
            if line.startswith("V "):
                headers["Version"] = line[2:].strip()
                continue
            if line.startswith("$") and ":" in line:
                k, _, v = line[1:].partition(":")
                headers[k.strip()] = v.strip()
            # N+/N- 等の頭情報は今のところ未使用 (将来用)

        initial_gfen = headers.get("INITIAL_GFEN")
        if not initial_gfen:
            raise ValueError("missing $INITIAL_GFEN header")
        game = decode_gfen(initial_gfen)
        for gsa_tok in gsa_moves:
            self._decode_to_parsedmove(gsa_tok, game).apply(game)
        return game

    # --- helpers ---------------------------------------------------------

    def _encode_token(self, internal_tok: str, tracker: Game) -> str:
        side = tracker.turn
        sign = "+" if side is Side.White else "-"
        parsed = parse_move(internal_tok)
        if parsed.kind == "done":
            return f"{sign}%DONE"
        if parsed.kind == "resign":
            return f"{sign}%TORYO"
        if parsed.kind in ("move", "stack"):
            assert parsed.src is not None and parsed.dst is not None
            sx, sy = parsed.src
            dx, dy = parsed.dst
            stack = tracker.board.grid.get((sx, sy), [])
            if not stack:
                raise ValueError(f"GSA encode: empty source at {parsed.src}")
            pcode = self._PIECE_TO_UPPER[stack[-1].piece_type]
            suffix = "^" if parsed.kind == "stack" else ""
            return f"{sign}{sx+1}{sy+1}{dx+1}{dy+1}{pcode}{suffix}"
        if parsed.kind == "drop":
            assert parsed.dst is not None and parsed.piece_type is not None
            dx, dy = parsed.dst
            pcode = self._PIECE_TO_UPPER[parsed.piece_type]
            return f"{sign}00{dx+1}{dy+1}{pcode}"
        raise ValueError(f"GSA encode: unsupported kind {parsed.kind}")

    def _decode_to_parsedmove(self, gsa_tok: str, game: Game) -> ParsedMove:
        # 特殊コマンド (+%DONE / -%TORYO 等)
        m = self._CMD_RE.match(gsa_tok)
        if m:
            cmd = m.group(2)
            if cmd == "DONE":
                return ParsedMove(kind="done")
            if cmd == "TORYO":
                return ParsedMove(kind="resign")
            raise ValueError(f"unknown GSA command: %{cmd}")
        # 通常手
        m = self._MOVE_RE.match(gsa_tok)
        if not m:
            raise ValueError(f"invalid GSA token: {gsa_tok!r}")
        sign, src_raw, dst_raw, pcode, suffix = m.groups()
        if pcode not in self._UPPER_TO_PIECE:
            raise ValueError(f"unknown piece code: {pcode}")
        piece_type = self._UPPER_TO_PIECE[pcode]
        dx, dy = int(dst_raw[0]) - 1, int(dst_raw[1]) - 1
        if src_raw == "00":
            return ParsedMove(
                kind="drop", piece_type=piece_type, dst=(dx, dy),
            )
        sx, sy = int(src_raw[0]) - 1, int(src_raw[1]) - 1
        kind = "stack" if suffix == "^" else "move"
        return ParsedMove(kind=kind, src=(sx, sy), dst=(dx, dy))

    @staticmethod
    def _encode_result(game: Game) -> str:
        if game.winner is None:
            return "*"
        return "1-0" if game.winner is Side.White else "0-1"


# ---------------------------------------------------------------------------
# JSON 形式 (既存 protocol.save_game/load_game の薄いラッパー)
# ---------------------------------------------------------------------------


class JsonKifuFormat(KifuFormat):
    extension = "json"
    description = "JSON"

    def save(self, game: Game, path: Path) -> None:
        _json_save_game(game, path)

    def load(self, path: Path) -> Game:
        return _json_load_game(path)


# ---------------------------------------------------------------------------
# レジストリ
# ---------------------------------------------------------------------------


FORMATS: list[KifuFormat] = [
    GungiTextKifuFormat(),
    GungiSjisKifuFormat(),
    GsaKifuFormat(),
    JsonKifuFormat(),
]


def filter_strings() -> str:
    """QFileDialog の filter 引数用文字列 (`;;` 区切り)。"""
    return ";;".join(f.filter_string for f in FORMATS)


def format_from_filter(filter_str: str) -> KifuFormat | None:
    for f in FORMATS:
        if f.filter_string == filter_str:
            return f
    return None


def format_from_extension(path: Path) -> KifuFormat | None:
    ext = path.suffix.lstrip(".").lower()
    for f in FORMATS:
        if f.extension == ext:
            return f
    return None


def resolve_save_format(path: Path, selected_filter: str) -> tuple[Path, KifuFormat]:
    """save 時のフォーマット解決。拡張子が一致するフォーマット優先、
    無ければ選択フィルタを使い、必要なら path に拡張子を補う。
    """
    fmt = format_from_extension(path)
    if fmt is None:
        fmt = format_from_filter(selected_filter) or FORMATS[0]
        path = path.with_suffix(f".{fmt.extension}")
    return path, fmt


def resolve_load_format(path: Path, selected_filter: str) -> KifuFormat:
    """load 時のフォーマット解決。拡張子優先 → フィルタ → デフォルト。"""
    return (
        format_from_extension(path)
        or format_from_filter(selected_filter)
        or FORMATS[0]
    )
