# This is a program about the board

class Board:
    def __init__(self, size=9):
        """
        盤面に関するクラス
        
        盤面を8x8に初期化
        """
        self.size = size
        self.grid = [[[] for _ in range(size)] for _ in range(size)]
    
    def is_with_in_bounds(self, x, y) -> bool:
        """
        xyが盤面内の座標であるか判定

        :param x: x座標（0-8）
        :param y: y座標（0-8）
        :return: 座標が盤面内であればTrue、そうでなければFalse
        """
        return 0 <= x < self.size and 0 <= y < self.size
    
    def is_rank_lower_than(self, piece, x, y) -> bool:
        """
        移動先の座標に駒があった場合、その駒のランクが自身(移動対象)のランク以下かつ0以上4未満か判定
        :param piece: 移動対象の駒（Piecesのインスタンス）
        :param x: x座標（0-8）
        :param y: y座標（0-8）
        :return: 移動先の駒のランクが自身のランク以下かつ0以上4未満であればTrue、そうでなければFalse
        """
        target_rank = len(self.grid[y][x])
        if target_rank != 0:
            if target_rank <= piece.rank and 0 <= target_rank < 4:
                return True
    
    def is_able_to_move(self, piece, x, y) -> bool:
        """
        駒が指定された座標に移動可能なのか判定
        :param piece: 移動対象の駒（Piecesのインスタンス）
        :param x: x座標（0-8）
        :param y: y座標（0-8）
        :return: 移動可能であればTrue、そうでなければFalse
        """
        if (x,y) in piece.movement:
            if self.is_with_in_bounds(x, y):
                target_piece_rank = len(self.grid[y][x])
                # 移動先に駒がない場合
                if target_piece_rank == 0:
                    return True
                else:
                    # 移動先に駒がある場合、ランクが自身のランク以下かつ0以上4未満であれば移動可能
                    return self.is_rank_lower_than(piece, x, y)
        return False

    def place_piece(self, piece, x, y, action: str) -> bool:
        """
        指定された座標に駒を配置
        
        :param piece: 配置する駒（Piecesのインスタンス）
        :param x: x座標（0-8）
        :param y: y座標（0-8）
        :param action: 駒を取るかツケるかの選択 ("capture", "stack", または "move")
        :return: 駒が配置された場合はTrue、位置が無効な場合はFalse
        """
        if not self.is_with_in_bounds(x, y):
            print("Position is out of bounds. Please provide valid coordinates.")
            return False

        if not self.is_able_to_move(piece, x, y):
            print("Invalid move for the piece. Please check the movement rules.")
            return False

        if len(self.grid[y][x]) == 0:
            # 移動先に駒がない場合の処理
            if action == "move":
                self.grid[y][x].append(piece)
                piece.x, piece.y = x, y


    def get_piece(self, x, y, z=-1):
        """
        指定された座標の駒を取得
        
        :param x: x座標（0-8）
        :param y: y座標（0-8）
        :param z: ツケの状態（例: 0, 1, 2）
        :return: その位置の駒、もしくは駒が存在しない場合はNone
        """
        if self.is_with_in_bounds(x, y):
            return self.grid[z][y][x]
        else:
            print("Position is out of bounds. Please provide valid coordinates.")
            return None