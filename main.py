"""動作確認用のエントリポイント。

初期配置からいくつか手を進めて盤面を表示するデモ。
"""
from __future__ import annotations

from game import Action, ActionType, Game, GameConfig
from pieces import DifficultyLevel


def show(game: Game, header: str) -> None:
    print(f"\n=== {header} (turn={game.turn.name}, moves={game.move_count}) ===")
    print(game.board.render())
    if game.winner is not None:
        print(f"*** WINNER: {game.winner.name} ***")


def try_move(game: Game, src: tuple[int, int], dst: tuple[int, int]) -> bool:
    try:
        game.apply(Action(ActionType.MOVE, src=src, dst=dst))
        return True
    except ValueError as e:
        print(f"  illegal: {src}->{dst} ({e})")
        return False


def main() -> None:
    # 入門 = 既定の初期配置 (初期配置①)。中級/上級は空盤なので CLI デモには不向き。
    game = Game(config=GameConfig(difficulty=DifficultyLevel.INTRODUCTORY))
    show(game, "initial")

    # 白の 兵 (4,2) を前進
    try_move(game, (4, 2), (4, 3))
    show(game, "after white HYOU advance")

    # 黒の 兵 (4,6) を前進
    try_move(game, (4, 6), (4, 5))
    show(game, "after black HYOU advance")

    # 砦 (1,2) を前へ、黒も砦を出す
    try_move(game, (1, 2), (1, 3))
    try_move(game, (1, 6), (1, 5))
    show(game, "after both TORIDE moves")

    legal = game.legal_actions()
    print(f"\nlegal actions for {game.turn.name}: {len(legal)}")
    print(f"sennichite? {game.is_sennichite()}")


if __name__ == "__main__":
    main()
