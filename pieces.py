# This program is about pieces
from enum import Enum

class Side(Enum):
    White = 1
    Black = 2

    
class PieceType(Enum):
    """
    駒表示用の列挙型
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
    def __init__(self, color, name, x, y) -> None:
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

    def __str__(self) -> str:
        """
        駒の情報を文字列で表現（デバッグ用）
        """
        return f"{self.color} {self.name} at ({self.x}, {self.y})"

