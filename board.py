"""軍議の盤面とツケ管理。

盤面は (x, y) -> 駒スタック (下から上への list) という sparse dict で表現する。
stack[0] が 1段目 (地上)、stack[-1] が最上段。
移動やツケの対象となるのは常に最上段の駒。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pieces import (
    MAX_LEVEL,
    Loc,
    MovePattern,
    MoveType,
    Piece,
    PieceType,
    Side,
)

MAX_STACK_HEIGHT = MAX_LEVEL + 1  # ツケ 3段 = level 0,1,2


@dataclass
class Board:
    width: int = 9
    height: int = 9
    grid: dict[tuple[int, int], list[Piece]] = field(default_factory=dict)

    # ---------------- クエリ ----------------

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def stack_at(self, x: int, y: int) -> list[Piece]:
        return self.grid.get((x, y), [])

    def height_at(self, x: int, y: int) -> int:
        return len(self.stack_at(x, y))

    def top_piece(self, x: int, y: int) -> Piece | None:
        stack = self.stack_at(x, y)
        return stack[-1] if stack else None

    def find_piece(self, piece: Piece) -> tuple[int, int] | None:
        for coord, stack in self.grid.items():
            if piece in stack:
                return coord
        return None

    def iter_squares(self) -> list[tuple[int, int, list[Piece]]]:
        return [(x, y, stack) for (x, y), stack in self.grid.items() if stack]

    def find_sui(self, side: Side) -> tuple[int, int] | None:
        for (x, y), stack in self.grid.items():
            for p in stack:
                if p.piece_type is PieceType.SUI and p.color is side:
                    return (x, y)
        return None

    # ---------------- 可動先の計算 ----------------

    def destinations_from(self, x: int, y: int) -> list[tuple[int, int]]:
        """(x,y) の最上段駒が移動可能な全マス。"""
        piece = self.top_piece(x, y)
        if piece is None:
            return []
        out: list[tuple[int, int]] = []
        for pat in piece.movement():
            out.extend(self._walk(x, y, pat, piece))
        return out

    def _walk(
        self, x: int, y: int, pat: MovePattern, piece: Piece
    ) -> list[tuple[int, int]]:
        if pat.move_type is MoveType.STEP:
            nx, ny = x + pat.dx, y + pat.dy
            return [(nx, ny)] if self._can_land_on(nx, ny, piece) else []

        if pat.move_type is MoveType.JUMP:
            nx, ny = x + pat.dx, y + pat.dy
            return [(nx, ny)] if self._can_land_on(nx, ny, piece) else []

        # LINE: 途中に駒があれば遮断
        results: list[tuple[int, int]] = []
        limit = pat.limit if pat.limit is not None else max(self.width, self.height)
        nx, ny = x, y
        for _ in range(limit):
            nx += pat.dx
            ny += pat.dy
            if not self.in_bounds(nx, ny):
                break
            top = self.top_piece(nx, ny)
            if top is None:
                results.append((nx, ny))
                continue
            # 何かある → ここまでが走れる終点。敵駒なら着地可、自駒なら止まるだけ。
            if top.color is not piece.color:
                results.append((nx, ny))
            break
        return results

    def _can_land_on(self, x: int, y: int, piece: Piece) -> bool:
        if not self.in_bounds(x, y):
            return False
        top = self.top_piece(x, y)
        if top is None:
            return True
        return top.color is not piece.color

    # ---------------- 操作 (低レベル) ----------------

    def place_initial(self, piece: Piece, x: int, y: int) -> None:
        """初期配置専用。バリデーション最小。"""
        if not self.in_bounds(x, y):
            raise ValueError(f"out of bounds: ({x},{y})")
        stack = self.grid.setdefault((x, y), [])
        piece.level = len(stack)
        piece.location = Loc.ON_BOARD
        stack.append(piece)

    def move_top(
        self, src: tuple[int, int], dst: tuple[int, int]
    ) -> Piece | None:
        """src の最上段駒を dst へ動かす。

        dst が空なら新しいスタックを level=0 で作る。
        dst に敵駒の最上段があれば捕獲し、自駒はその位置 (= 敵駒の level) に入る。
        dst に自駒の最上段があれば ValueError (move では不可; stack_on_top を使う)。

        :return: 捕獲した敵駒 (なければ None)
        """
        sx, sy = src
        dx, dy = dst
        src_stack = self.stack_at(sx, sy)
        if not src_stack:
            raise ValueError(f"source empty: {src}")
        if not self.in_bounds(dx, dy):
            raise ValueError(f"dest out of bounds: {dst}")

        mover = src_stack[-1]
        dst_stack = self.grid.setdefault((dx, dy), [])
        captured: Piece | None = None
        if dst_stack:
            top = dst_stack[-1]
            if top.color is mover.color:
                raise ValueError("cannot move onto own piece (use stack_on_top)")
            captured = dst_stack.pop()
            captured.location = Loc.CAPTURED

        src_stack.pop()
        if not src_stack:
            del self.grid[(sx, sy)]
        mover.level = len(dst_stack)
        dst_stack.append(mover)
        return captured

    def stack_on_top(
        self, src: tuple[int, int], dst: tuple[int, int]
    ) -> None:
        """src の最上段駒を dst の最上段に「ツケ」として乗せる。

        dst のスタックが 3段 未満で、最上段が帥でなく、自駒でも敵駒でも可。
        mover 自身が 帥 の場合は不可。
        """
        sx, sy = src
        dx, dy = dst
        src_stack = self.stack_at(sx, sy)
        if not src_stack:
            raise ValueError(f"source empty: {src}")
        if not self.in_bounds(dx, dy):
            raise ValueError(f"dest out of bounds: {dst}")

        mover = src_stack[-1]
        if not mover.can_stack_self():
            raise ValueError("帥は自らツケられない")

        dst_stack = self.stack_at(dx, dy)
        if not dst_stack:
            raise ValueError("cannot stack on empty square (use move_top)")
        if len(dst_stack) >= MAX_STACK_HEIGHT:
            raise ValueError("stack already at max height (3)")
        if not dst_stack[-1].can_be_stacked():
            raise ValueError("帥の上にはツケできない")

        src_stack.pop()
        if not src_stack:
            del self.grid[(sx, sy)]
        mover.level = len(dst_stack)
        self.grid.setdefault((dx, dy), dst_stack).append(mover)

    def drop_from_hand(self, piece: Piece, dst: tuple[int, int]) -> None:
        """手駒または捕獲駒を盤上に「新 (あらた)」として打つ。

        制約 (ルールブック p.5):
          - 3段目 (level=2) への新ツケ不可
          - 帥の上に新ツケ不可
          - 自駒の上に新ツケ不可
          - 帥そのものは新で打てない
        """
        dx, dy = dst
        if not self.in_bounds(dx, dy):
            raise ValueError(f"dest out of bounds: {dst}")
        if piece.piece_type is PieceType.SUI:
            raise ValueError("帥は新で打てない")

        dst_stack = self.grid.setdefault((dx, dy), [])
        resulting_level = len(dst_stack)
        if resulting_level >= 2:
            raise ValueError("新で3段目には置けない")
        if dst_stack:
            top = dst_stack[-1]
            if top.color is piece.color:
                raise ValueError("自駒の上に新は置けない")
            if not top.can_be_stacked():
                raise ValueError("帥の上に新は置けない")

        piece.level = resulting_level
        piece.location = Loc.ON_BOARD
        dst_stack.append(piece)

    # ---------------- 可読化 ----------------

    def render(self) -> str:
        lines = ["   " + " ".join(f"{x:<2}" for x in range(self.width))]
        for y in range(self.height - 1, -1, -1):
            cells: list[str] = []
            for x in range(self.width):
                top = self.top_piece(x, y)
                if top is None:
                    cells.append("・ ")
                else:
                    mark = top.kanji + ("*" if top.color is Side.Black else " ")
                    cells.append(mark)
            lines.append(f"{y}: " + " ".join(cells))
        return "\n".join(lines)
