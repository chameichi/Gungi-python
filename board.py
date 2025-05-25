# This is a program about the board

class Board:
    def __init__(self, size=9):
        """
        盤面に関するクラス
        
        盤面を8x8に初期化
        """
        self.size = size
        self.grid = [[None for _ in range(size)] for _ in range(size)]
    
    def is_with_in_bounds(self, x, y) -> bool:
        """
        xyが盤面内の座標であるか判定

        :param x: x座標（0-8）
        :param y: y座標（0-8）
        :return: 座標が盤面内であればTrue、そうでなければFalse
        """
        return 0 <= x < self.size and 0 <= y < self.size

    def place_piece(self, piece, x, y):
        """
        指定された座標に駒を配置
        
        :param piece: 配置する駒（Piecesのインスタンス）
        :param x: x座標（0-8）
        :param y: y座標（0-8）
        :return: 駒が配置された場合はTrue、位置が無効な場合はFalse
        """
        if self.is_with_in_bounds(x, y):
            self.grid[y][x] = piece
            return True
        else:
            print("Position is out of bounds. Please provide valid coordinates.")
            return False
    
    def get_piece(self, x, y):
        """
        指定された座標の駒を取得
        
        :param x: x座標（0-8）
        :param y: y座標（0-8）
        :return: その位置の駒、もしくは駒が存在しない場合はNone
        """
        if self.is_with_in_bounds(x, y):
            return self.grid[y][x]
        else:
            print("Position is out of bounds. Please provide valid coordinates.")
            return None