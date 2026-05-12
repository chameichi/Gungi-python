"""スタブ AI エンジン (`engine_stub.py`).

`UGIHandler` を継承し、合法手からランダムに 1 手選んで返す最小エンジン。
GUI から `python engine_stub.py` のようにサブプロセスとして起動し、
stdin/stdout 越しに UGI プロトコルで通信する想定。

将来本物の AI を実装する際は、本ファイルをひな形として `engine_*.py` を
追加し、`search()` を読み筋付き探索に置き換える。
"""
from __future__ import annotations

import random
import sys
from typing import Iterable

from game import GamePhase
from protocol import DONE, RESIGN, UGIHandler, encode_move


class StubEngine(UGIHandler):
    NAME = "GungiStubEngine"
    AUTHOR = "stub"

    def search(self, params: dict[str, str]) -> str:
        # 布陣段階: 帥未配置なら帥を、なければ手駒からランダムに配置
        if self.game.phase is GamePhase.PLACEMENT:
            return self._search_placement()
        legal = self.game.legal_actions()
        if not legal:
            return RESIGN
        return encode_move(random.choice(legal), self.game)

    def _search_placement(self) -> str:
        from pieces import PieceType, Side
        side = self.game.turn
        # 帥が未配置ならまず帥を置く
        if self.game.board.find_sui(side) is None:
            return self._drop_in_own_territory(PieceType.SUI)
        # 手駒に何も無ければ配置完了
        if not self.game.hand[side]:
            return DONE
        # 帥以外の手駒からランダムに 1 種選んで自陣に置く
        non_sui = [
            p for p in self.game.hand[side]
            if p.piece_type is not PieceType.SUI
        ]
        if not non_sui:
            return DONE
        piece = random.choice(non_sui)
        return self._drop_in_own_territory(piece.piece_type)

    def _drop_in_own_territory(self, piece_type) -> str:
        """自陣 3 行のランダムな空きマスに drop 文字列を作る。"""
        from protocol import PIECE_CODE
        side = self.game.turn
        ys = list(self.game._own_territory_y(side, self.game.board.height))
        candidates: list[tuple[int, int]] = []
        for y in ys:
            for x in range(self.game.board.width):
                if self.game.board.height_at(x, y) == 0:
                    candidates.append((x, y))
        if not candidates:
            # 自陣が埋まっているなら配置完了するしかない
            return DONE
        x, y = random.choice(candidates)
        return f"{PIECE_CODE[piece_type]}*{x}{y}"


def main() -> int:
    StubEngine().run_repl()
    return 0


if __name__ == "__main__":
    sys.exit(main())
