# This program is about pieces
from enum import Enum

class Side(Enum):
    White = 1
    Black = 2

    
class PieceType:
    """
    駒の種類を定義するクラス
    """
    Sui = "帥"
    Boushou = "謀"
    Ohdsutsu = "砲"
    Tsutsu = "筒"
    Taishou = "大"
    Chujou = "中"
    Shoushou = "小"
    Shinobi = "忍"
    Samurai = "侍"
    Kiba = "馬"
    Yumi = "弓"
    Toride = "砦"
    Yari = "槍"
    Hyou = "兵"


class Pieces:
    def __init__(self, color, name, x=-1, y=-1) -> None:
        """
         駒の基本情報を管理するクラス
        :param color: 駒の色（例: Side.White または Side.Black）
        :param name: 駒の名前（例: "King", "Queen", "Bishop" など）
        :param x: 駒のx座標（0から8の整数）
        :param y: 駒のy座標（0から8の整数）
        """
        self.color = color
        self.name = name
        self.x = x
        self.y = y
        self.rank = 0  # 駒のランク（初期値は0）
        self.movelist = []

    def get_movelist(self) -> list:
        """
        駒の移動方法を定義
        :param color: 駒の色（例: Side.White または Side.Black）
        :return: 移動可能な座標のリスト
        """
        raise NotImplementedError("This method should be overridden by subclasses")

    def __str__(self) -> str:
        """
        駒の情報を文字列で表現（デバッグ用）
        """
        return f"{self.color} {self.name} at ({self.x}, {self.y})"
    

class Sui(Pieces):
    def __init__(self, color, name):
        super().__init__(color, name, x=-1, y=-1)
        self.name = PieceType.Sui
        if self.color == Side.White:
            self.movelist = [
                (dy, dx) for dx in range(-1, 2) for dy in range(-1, 2)
                if not (dx == 0 and dy == 0)
            ]
        else:
            self.movelist = [
                (-dy, -dx) for dx in range(-1, 2) for dy in range(-1, 2)
                if not (dx == 0 and dy == 0)
            ]

    def __str__(self) -> str:
        return f"{self.color} {self.name} at ({self.x}, {self.y})"
    
    def get_movelist(self) -> list:
        """
        帥の移動方法を定義
        :return: 移動可能な座標のリスト
        """
        move = self.movelist
        if self.rank == 1:
            # ツケ1のときは移動範囲を元のmoveからまわり8マスを拡大
            move.extend([
                (dy, dx) for dx in range(-2, 3, 2)
                for dy in range(-2, 3, 2)
                if (dx != 0 or dy != 0) \
                    and (0 <= self.x + dx < 9) \
                    and (0 <= self.y + dy < 9)
            ])
        elif self.rank == 2:
            # ツケ2のときは移動範囲をツケ1のmoveからまわり8マスを拡大
            move.extend([
                (dy, dx) for dx in range(-3, 4, 3)
                for dy in range(-3, 4, 3)
                if (dx != 0 or dy != 0) \
                    and (0 <= self.x + dx < 9) \
                    and (0 <= self.y + dy < 9)
            ])
        else:
            # ツケ3以上は違法
            raise ValueError("Invalid rank for Sui piece")
        # 黒番のときは移動方向を反転
        if self.color == Side.Black:
            move = [(-y, -x) for y, x in move]
        return move
    
    def update_movelist(self) -> None:
        """
        get_movelistを呼び出し、駒の移動可能方向を更新
        """
        self.movelist += self.get_movelist()


class Hyou(Pieces):
    def __init__(self, color, name):
        super().__init__(color, name, x=-1, y=-1)
        self.name = PieceType.Hyou
        if self.color == Side.White:
            self.movelist = [
                (dy, 0) for dy in range(-1, 2)
                if dy != 0
            ]
        else:
            self.movelist = [
                (-dy, 0) for dy in range(-1, 2)
                if dy != 0
            ]

    def __str__(self) -> str:
        return f"{self.color} {self.name} at ({self.x}, {self.y})"
    
    def get_movelist(self) -> list:
        """
        帥の移動方法を定義
        :return: 移動可能な座標のリスト
        """
        move = self.movelist
        if self.rank == 1:
            # ツケ1のときは移動範囲を元のmoveから前後2マスを拡大
            move.extend([
                (dy, 0) for dy in range(-2, 3, 2)
                if (0 <= self.y + dy < 9) \
                    and (0 <= self.x < 9) \
                    and dy != 0
            ])
        elif self.rank == 2:
            # ツケ2のときは移動範囲をツケ1のmoveから更に前後2マスを拡大
            move.extend([
                (dy, 0) for dy in range(-3, 4, 3)
                if (0 <= self.y + dy < 9) \
                    and (0 <= self.x < 9) \
                    and dy != 0
            ])
        else:
            # ツケ3以上は違法
            raise ValueError("Invalid rank for Sui piece")
        # 黒番のときは移動方向を反転
        if self.color == Side.Black:
            move = [(-y, -x) for y, x in move]
        return move
    
    def update_movelist(self) -> None:
        """
        get_movelistを呼び出し、駒の移動可能方向を更新
        """
        self.movelist += self.get_movelist()


if __name__ == "__main__":
    # Example usage
    sui = Sui(Side.White, PieceType.Sui)
    print(sui)  # Output: Side.White PieceType.Sui at (0, 0)
    
    piece2 = Pieces(Side.Black, PieceType.Boushou)
    print(piece2)  # Output: Side.Black PieceType.Boushou at (1, 1)
