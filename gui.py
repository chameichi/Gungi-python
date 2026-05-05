"""PySide6 GUI。

レイアウト:
    +----------------------------------------------------------+
    | [Toolbar: 開始 戻す 進める 最新 | 編集 手番 クリア]            |
    +----------------+--------------------------+--------------+
    |                | (上: 後手バー 名前/手番)   |              |
    | 黒 持駒/捕獲駒  | (中央: BoardWidget)       | 棋譜リスト    |
    |                | (下: 先手バー 名前/手番)   |              |
    | 白 持駒/捕獲駒  +--------------------------+              |
    +----------------+--------------------------+--------------+
    | StatusBar                                                |
    +----------------------------------------------------------+

主要部品:
    BoardWidget  : QPainter で盤 (木目) と駒 (五角形+漢字) を描画。
    HandPanel    : 手駒/捕獲駒の一覧 (QListWidget)。
    PlayerHeader : 手番ハイライト付きの「先手 / 後手」バー。
    MoveListPanel: 棋譜 (QListWidget)。クリックでその局面にジャンプ。
    ChoiceDialog : 取る/ツケる/新 の選択ポップアップ。
    EditDialog   : 局面編集 (駒種+色を選択して配置 or 最上段削除)。
"""
from __future__ import annotations

import signal
import sys
from dataclasses import dataclass
from enum import Enum, auto

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QPainter,
    QPalette,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QStatusBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from game import Action, ActionType, Game, GameConfig, GamePhase
from pieces import PIECES_NAME, DifficultyLevel, Piece, PieceType, Side


# ---------------------------------------------------------------------------
# 定数 / テーマ
# ---------------------------------------------------------------------------

BOARD_W = 9
BOARD_H = 9

# 盤面・駒・直前手ハイライトはシステムテーマに依らず固定
# (実物の軍議盤を模した暖色)
COL_BOARD_BG = "#f0d091"
COL_BOARD_GRID = "#5a3d10"
COL_LABEL_FG = "#5a3d10"
COL_HL_SRC = "#1976d2"
COL_HL_DST = "#2e7d32"
COL_HL_LASTMV = "#ffd166"

# 手番表示・ツールバー・選択中駒ハイライト (テーマ非依存の意図色)
COL_HEADER_BG_ACTIVE = "#2e7d32"
COL_HEADER_BG_IDLE = "#5a5a5a"
COL_HEADER_FG = "#ffffff"
COL_TOOLBAR_BG = "#1f6f3f"
COL_TOOLBAR_FG = "#ffffff"


@dataclass
class Theme:
    """UI 全体に適用するテーマカラー (システム判定で切替)。"""
    is_dark: bool
    bg: str          # メイン背景
    fg: str          # メイン文字色
    panel_bg: str    # パネル背景 (持駒一覧・棋譜)
    panel_fg: str
    input_bg: str    # 入力系 (combo/list) の背景
    input_fg: str
    border: str
    selected_bg: str  # リスト選択の強調

    @classmethod
    def light(cls) -> "Theme":
        return cls(
            is_dark=False,
            bg="#fafafa", fg="#222222",
            panel_bg="#f6f1e6", panel_fg="#222222",
            input_bg="#ffffff", input_fg="#111111",
            border="#bbbbbb",
            selected_bg="#bbdefb",
        )

    @classmethod
    def dark(cls) -> "Theme":
        return cls(
            is_dark=True,
            bg="#1f1f1f", fg="#e8e8e8",
            panel_bg="#2c2924", panel_fg="#eeeeee",
            input_bg="#333333", input_fg="#eeeeee",
            border="#555555",
            selected_bg="#1565c0",
        )

    @classmethod
    def detect(cls, app: QApplication) -> "Theme":
        # PySide6 6.5+ の colorScheme を優先、失敗時は palette から判定
        try:
            from PySide6.QtCore import Qt as _Qt
            scheme = app.styleHints().colorScheme()
            if scheme == _Qt.ColorScheme.Dark:
                return cls.dark()
            return cls.light()
        except (AttributeError, Exception):
            pal = app.palette()
            window = pal.color(QPalette.ColorRole.Window)
            return cls.dark() if window.lightnessF() < 0.5 else cls.light()


# 起動時に main() で差し替える
THEME: "Theme" = Theme.light()


def apply_global_stylesheet(app: QApplication) -> None:
    t = THEME
    app.setStyleSheet(
        f"""
        QMainWindow, QDialog {{ background:{t.bg}; color:{t.fg}; }}
        QWidget {{ color:{t.fg}; }}
        QLabel {{ color:{t.fg}; background:transparent; }}
        QStatusBar {{ background:{t.panel_bg}; color:{t.fg}; }}
        HandPanel, MoveListPanel {{
            background:{t.panel_bg};
            border:1px solid {t.border};
            border-radius:4px;
        }}
        QListWidget {{
            background:{t.input_bg}; color:{t.input_fg};
            border:1px solid {t.border}; border-radius:4px;
        }}
        QListWidget::item {{ color:{t.input_fg}; }}
        QListWidget::item:selected {{
            background:{t.selected_bg}; color:{t.fg};
        }}
        QComboBox {{
            background:{t.input_bg}; color:{t.input_fg};
            border:1px solid {t.border}; padding:4px 8px; border-radius:4px;
        }}
        QComboBox::drop-down {{ width:24px; border-left:1px solid {t.border}; }}
        QComboBox QAbstractItemView {{
            background:{t.input_bg}; color:{t.input_fg};
            selection-background-color:{t.selected_bg};
            selection-color:{t.fg};
        }}
        QRadioButton {{ color:{t.fg}; background:transparent; padding:2px; }}
        QRadioButton::indicator {{ width:14px; height:14px; }}
        QToolTip {{ background:{t.panel_bg}; color:{t.fg}; border:1px solid {t.border}; }}
        QMenu {{
            background:{t.input_bg}; color:{t.input_fg};
            border:1px solid {t.border}; padding:4px;
        }}
        QMenu::item {{
            background:transparent; color:{t.input_fg};
            padding:6px 24px 6px 16px; border-radius:3px;
        }}
        QMenu::item:selected {{
            background:{t.selected_bg}; color:{t.fg};
        }}
        QMenu::separator {{
            height:1px; background:{t.border}; margin:4px 0;
        }}
        """
    )


# ---------------------------------------------------------------------------
# Choice / Edit ダイアログ (既存)
# ---------------------------------------------------------------------------


class Choice(Enum):
    MOVE = auto()
    CAPTURE = auto()
    STACK = auto()
    ARATA = auto()


_CHOICE_LABEL: dict[Choice, str] = {
    Choice.MOVE: "移動",
    Choice.CAPTURE: "取る",
    Choice.STACK: "ツケる",
    Choice.ARATA: "新 (あらた)",
}


_DIALOG_BTN_QSS = (
    "QPushButton {"
    "  background:#2e7d32; color:#ffffff; border:1px solid #1b5e20;"
    "  border-radius:6px; padding:8px 16px; font-size:14px; font-weight:bold;"
    "}"
    "QPushButton:hover { background:#43a047; }"
    "QPushButton:pressed { background:#1b5e20; }"
)
_DIALOG_CANCEL_QSS = (
    "QPushButton {"
    "  background:#eeeeee; color:#333333; border:1px solid #999999;"
    "  border-radius:6px; padding:6px 12px; font-size:13px;"
    "}"
    "QPushButton:hover { background:#dddddd; }"
)


class ChoiceDialog(QDialog):
    def __init__(self, parent: QWidget, options: list[Choice], title: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.selected: Choice | None = None

        v = QVBoxLayout(self)
        v.setSpacing(8)
        v.setContentsMargins(16, 16, 16, 16)
        for ch in options:
            btn = QPushButton(_CHOICE_LABEL[ch])
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(220)
            btn.setStyleSheet(_DIALOG_BTN_QSS)
            btn.clicked.connect(lambda _=False, c=ch: self._pick(c))
            v.addWidget(btn)

        cancel_btn = QPushButton("キャンセル")
        cancel_btn.setStyleSheet(_DIALOG_CANCEL_QSS)
        cancel_btn.clicked.connect(self.reject)
        v.addWidget(cancel_btn)

    def _pick(self, choice: Choice) -> None:
        self.selected = choice
        self.accept()


class EditAction(Enum):
    PLACE = auto()
    REMOVE = auto()


class EditDialog(QDialog):
    def __init__(self, parent: QWidget, top: Piece | None, coord: tuple[int, int]) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"局面編集 ({coord[0]},{coord[1]})")
        self.action: EditAction | None = None
        self.piece_type: PieceType | None = None
        self.color: Side | None = None

        v = QVBoxLayout(self)
        v.setSpacing(8)
        v.setContentsMargins(16, 16, 16, 16)
        if top is not None:
            v.addWidget(QLabel(f"現在の最上段: {top.kanji} ({top.color.name})"))
        v.addWidget(QLabel("駒種:"))
        self.combo = QComboBox()
        for pt in PieceType:
            self.combo.addItem(PIECES_NAME[pt], pt)
        self.combo.setMinimumHeight(32)
        v.addWidget(self.combo)

        v.addWidget(QLabel("色:"))
        rh = QHBoxLayout()
        self.rb_white = QRadioButton("白 (先手)")
        self.rb_black = QRadioButton("黒 (後手)")
        self.rb_white.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.rb_white)
        group.addButton(self.rb_black)
        rh.addWidget(self.rb_white)
        rh.addWidget(self.rb_black)
        v.addLayout(rh)

        btn_place = QPushButton("配置")
        btn_place.setMinimumHeight(40)
        btn_place.setStyleSheet(_DIALOG_BTN_QSS)
        btn_place.clicked.connect(self._do_place)
        v.addWidget(btn_place)
        if top is not None:
            btn_remove = QPushButton("最上段を削除")
            btn_remove.setMinimumHeight(40)
            btn_remove.setStyleSheet(
                _DIALOG_BTN_QSS.replace("#2e7d32", "#c62828")
                              .replace("#1b5e20", "#8e0000")
                              .replace("#43a047", "#e53935")
            )
            btn_remove.clicked.connect(self._do_remove)
            v.addWidget(btn_remove)
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.setStyleSheet(_DIALOG_CANCEL_QSS)
        cancel_btn.clicked.connect(self.reject)
        v.addWidget(cancel_btn)

    def _do_place(self) -> None:
        self.action = EditAction.PLACE
        self.piece_type = self.combo.currentData()
        self.color = Side.White if self.rb_white.isChecked() else Side.Black
        self.accept()

    def _do_remove(self) -> None:
        self.action = EditAction.REMOVE
        self.accept()


class AddPieceDialog(QDialog):
    """編集モード: 駒を盤外コレクション (手駒/捕獲駒) に追加するダイアログ。"""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("手駒/捕獲駒に追加")
        self.piece_type: PieceType | None = None
        self.color: Side | None = None
        self.target: str | None = None  # 'hand' or 'captured'

        v = QVBoxLayout(self)
        v.setSpacing(8)
        v.setContentsMargins(16, 16, 16, 16)

        v.addWidget(QLabel("駒種:"))
        self.combo = QComboBox()
        for pt in PieceType:
            self.combo.addItem(PIECES_NAME[pt], pt)
        self.combo.setMinimumHeight(32)
        v.addWidget(self.combo)

        v.addWidget(QLabel("色:"))
        cr = QHBoxLayout()
        self.rb_white = QRadioButton("白 (先手)")
        self.rb_black = QRadioButton("黒 (後手)")
        self.rb_white.setChecked(True)
        cg = QButtonGroup(self)
        cg.addButton(self.rb_white)
        cg.addButton(self.rb_black)
        cr.addWidget(self.rb_white)
        cr.addWidget(self.rb_black)
        v.addLayout(cr)

        v.addWidget(QLabel("追加先:"))
        tr = QHBoxLayout()
        self.rb_hand = QRadioButton("手駒")
        self.rb_cap = QRadioButton("捕獲駒")
        self.rb_hand.setChecked(True)
        tg = QButtonGroup(self)
        tg.addButton(self.rb_hand)
        tg.addButton(self.rb_cap)
        tr.addWidget(self.rb_hand)
        tr.addWidget(self.rb_cap)
        v.addLayout(tr)

        ok_btn = QPushButton("追加")
        ok_btn.setMinimumHeight(40)
        ok_btn.setStyleSheet(_DIALOG_BTN_QSS)
        ok_btn.clicked.connect(self._do_ok)
        v.addWidget(ok_btn)
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.setStyleSheet(_DIALOG_CANCEL_QSS)
        cancel_btn.clicked.connect(self.reject)
        v.addWidget(cancel_btn)

    def _do_ok(self) -> None:
        self.piece_type = self.combo.currentData()
        self.color = Side.White if self.rb_white.isChecked() else Side.Black
        self.target = "hand" if self.rb_hand.isChecked() else "captured"
        self.accept()


class SimpleAddDialog(QDialog):
    """駒種だけを選ぶシンプルなダイアログ。
    どこに追加するかは呼び出し元 (パネル) が知っている前提。"""

    def __init__(self, parent: QWidget, title: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.piece_type: PieceType | None = None

        v = QVBoxLayout(self)
        v.setSpacing(8)
        v.setContentsMargins(16, 16, 16, 16)
        v.addWidget(QLabel("駒種:"))
        self.combo = QComboBox()
        for pt in PieceType:
            self.combo.addItem(PIECES_NAME[pt], pt)
        self.combo.setMinimumHeight(32)
        v.addWidget(self.combo)

        ok_btn = QPushButton("追加")
        ok_btn.setMinimumHeight(40)
        ok_btn.setStyleSheet(_DIALOG_BTN_QSS)
        ok_btn.clicked.connect(self._do_ok)
        v.addWidget(ok_btn)
        cancel_btn = QPushButton("キャンセル")
        cancel_btn.setStyleSheet(_DIALOG_CANCEL_QSS)
        cancel_btn.clicked.connect(self.reject)
        v.addWidget(cancel_btn)

    def _do_ok(self) -> None:
        self.piece_type = self.combo.currentData()
        self.accept()


# ---------------------------------------------------------------------------
# BoardWidget
# ---------------------------------------------------------------------------


class BoardWidget(QWidget):
    """QPainter ベースの盤面。マスクリックで `cellClicked(x, y)` を発火。"""

    cellClicked = Signal(int, int)

    def __init__(self, game: Game) -> None:
        super().__init__()
        self.game = game
        self.cell_size = 60
        self.margin = 26
        self.selection_src: tuple[int, int] | None = None
        self.legal_dests: set[tuple[int, int]] = set()
        self.last_move: tuple[tuple[int, int], tuple[int, int]] | None = None
        self.placement_zone_y: range | None = None  # 布陣中に強調する自陣の y 範囲
        self.setMinimumSize(self._board_pixel_w(), self._board_pixel_h())

    def _board_pixel_w(self) -> int:
        return BOARD_W * self.cell_size + 2 * self.margin

    def _board_pixel_h(self) -> int:
        return BOARD_H * self.cell_size + 2 * self.margin

    def sizeHint(self) -> QSize:
        return QSize(self._board_pixel_w(), self._board_pixel_h())

    # ---- ヘルパ: 盤座標 (x, y) → 画面の左上ピクセル ----

    def _cell_origin(self, x: int, y: int) -> tuple[int, int]:
        # 盤の y=0 は白側 = 画面下。画面 row は (H-1-y)。
        screen_col = x
        screen_row = BOARD_H - 1 - y
        return (
            self.margin + screen_col * self.cell_size,
            self.margin + screen_row * self.cell_size,
        )

    # ---- 描画 ----

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 盤面 (木目色)
        bw = BOARD_W * self.cell_size
        bh = BOARD_H * self.cell_size
        p.fillRect(QRect(self.margin, self.margin, bw, bh), QColor(COL_BOARD_BG))

        # 布陣中の自陣ハイライト (淡い緑)
        if self.placement_zone_y is not None:
            for y in self.placement_zone_y:
                for x in range(BOARD_W):
                    ox, oy = self._cell_origin(x, y)
                    p.fillRect(
                        QRect(ox, oy, self.cell_size, self.cell_size),
                        QColor(180, 230, 180, 90),
                    )

        # 直前手のハイライト
        if self.last_move is not None:
            for coord in self.last_move:
                ox, oy = self._cell_origin(*coord)
                p.fillRect(
                    QRect(ox, oy, self.cell_size, self.cell_size),
                    QColor(COL_HL_LASTMV),
                )

        # 罫線
        p.setPen(QPen(QColor(COL_BOARD_GRID), 1.4))
        for i in range(BOARD_W + 1):
            x = self.margin + i * self.cell_size
            p.drawLine(x, self.margin, x, self.margin + bh)
        for i in range(BOARD_H + 1):
            y = self.margin + i * self.cell_size
            p.drawLine(self.margin, y, self.margin + bw, y)

        # 列/行ラベル
        f = QFont()
        f.setPointSize(10)
        p.setFont(f)
        p.setPen(QColor(COL_LABEL_FG))
        for x in range(BOARD_W):
            cx = self.margin + x * self.cell_size + self.cell_size // 2
            p.drawText(QRect(cx - 10, 4, 20, self.margin - 4),
                       Qt.AlignmentFlag.AlignCenter, str(x))
            p.drawText(QRect(cx - 10, self.margin + bh, 20, self.margin),
                       Qt.AlignmentFlag.AlignCenter, str(x))
        for y in range(BOARD_H):
            cy = self.margin + (BOARD_H - 1 - y) * self.cell_size + self.cell_size // 2
            p.drawText(QRect(0, cy - 10, self.margin - 2, 20),
                       Qt.AlignmentFlag.AlignCenter, str(y))
            p.drawText(QRect(self.margin + bw + 2, cy - 10, self.margin, 20),
                       Qt.AlignmentFlag.AlignCenter, str(y))

        # 駒
        for x in range(BOARD_W):
            for y in range(BOARD_H):
                top = self.game.board.top_piece(x, y)
                stack_h = self.game.board.height_at(x, y)
                if top is not None:
                    self._draw_piece(p, x, y, top, stack_h)

        # ハイライト (枠線) - 駒の上に重ねる
        if self.selection_src is not None:
            self._draw_border(p, *self.selection_src, COL_HL_SRC, 3)
        for d in self.legal_dests:
            self._draw_border(p, *d, COL_HL_DST, 3)

    def _draw_piece(
        self, p: QPainter, x: int, y: int, piece: Piece, stack_h: int
    ) -> None:
        ox, oy = self._cell_origin(x, y)
        cx = ox + self.cell_size / 2
        cy = oy + self.cell_size / 2
        r = self.cell_size * 0.42

        # 白駒 = 白丸+黒文字、 黒駒 = 黒丸+白文字
        if piece.color is Side.White:
            face = QColor("#ffffff")
            edge = QColor("#222222")
            text = QColor("#000000")
        else:
            face = QColor("#1a1a1a")
            edge = QColor("#000000")
            text = QColor("#ffffff")

        p.setPen(QPen(edge, 1.6))
        p.setBrush(face)
        p.drawEllipse(QPointF(cx, cy), r, r)

        kf = QFont()
        kf.setBold(True)
        kf.setPixelSize(int(self.cell_size * 0.42))
        p.setFont(kf)
        p.setPen(text)
        p.drawText(
            QRectF(cx - r, cy - r, r * 2, r * 2),
            Qt.AlignmentFlag.AlignCenter,
            piece.kanji,
        )

        # スタック段数バッジ (右上に小さな赤丸+数字)
        if stack_h > 1:
            br = self.cell_size * 0.22
            bx = ox + self.cell_size - br - 2
            by = oy + 2
            p.setPen(QPen(QColor("#ffffff"), 1))
            p.setBrush(QColor("#c62828"))
            p.drawEllipse(QRectF(bx, by, br, br))
            bf = QFont()
            bf.setBold(True)
            bf.setPixelSize(int(br * 0.7))
            p.setFont(bf)
            p.setPen(QColor("#ffffff"))
            p.drawText(
                QRectF(bx, by, br, br),
                Qt.AlignmentFlag.AlignCenter,
                str(stack_h),
            )

    def _draw_border(
        self, p: QPainter, x: int, y: int, color: str, thickness: int
    ) -> None:
        ox, oy = self._cell_origin(x, y)
        p.setPen(QPen(QColor(color), thickness))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(ox + 2, oy + 2, self.cell_size - 4, self.cell_size - 4)

    # ---- マウス ----

    def mousePressEvent(self, event) -> None:
        pos = event.position()
        col = int((pos.x() - self.margin) // self.cell_size)
        row = int((pos.y() - self.margin) // self.cell_size)
        if 0 <= col < BOARD_W and 0 <= row < BOARD_H:
            board_y = BOARD_H - 1 - row
            self.cellClicked.emit(col, board_y)


# ---------------------------------------------------------------------------
# プレイヤーバー / 持駒パネル / 棋譜リスト
# ---------------------------------------------------------------------------


class PlayerHeader(QFrame):
    """プレイヤー名と手番インジケータをミニマルに表示する帯。"""

    def __init__(self, side: Side) -> None:
        super().__init__()
        self.side = side
        self.setFixedHeight(30)

        # 駒色ドット (●: 黒, ○: 白)
        self.dot = QLabel("●" if side is Side.Black else "○")
        df = QFont()
        df.setPointSize(13)
        self.dot.setFont(df)
        self.dot.setStyleSheet("color:#222;" if side is Side.Black else "color:#222;")

        self.name_label = QLabel()
        nf = QFont()
        nf.setPointSize(11)
        self.name_label.setFont(nf)

        # 手番中インジケータ (右端、アクティブ時のみ視認)
        self.turn_label = QLabel("")
        tf = QFont()
        tf.setPointSize(10)
        self.turn_label.setFont(tf)

        h = QHBoxLayout(self)
        h.setContentsMargins(10, 2, 10, 2)
        h.setSpacing(8)
        h.addWidget(self.dot)
        h.addWidget(self.name_label)
        h.addStretch(1)
        h.addWidget(self.turn_label)
        self.setActive(False)

    def setActive(self, active: bool) -> None:
        prefix = "後手" if self.side is Side.Black else "先手"
        self.name_label.setText(prefix)
        if active:
            self.turn_label.setText("● 手番")
            self.turn_label.setStyleSheet(
                "color:#2e7d32; font-weight:bold;"
            )
            self.setStyleSheet(
                "PlayerHeader { background:transparent; "
                "border-bottom:2px solid #2e7d32; }"
            )
        else:
            self.turn_label.setText("")
            self.setStyleSheet(
                "PlayerHeader { background:transparent; "
                "border-bottom:1px solid rgba(128,128,128,0.35); }"
            )


class HandPanel(QFrame):
    """手駒・捕獲駒の一覧。クリックで piece_id を、+ボタンで追加要求を通知。"""

    pieceClicked = Signal(str)   # piece_id
    addRequested = Signal()      # 編集モードの "+" ボタン

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("HandPanel")
        self.setProperty("class", "PanelFrame")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._title = QLabel(title)
        f = QFont()
        f.setPointSize(10)
        self._title.setFont(f)
        self._title.setStyleSheet(
            "color: rgba(128,128,128,0.9); letter-spacing: 1px;"
        )

        self._add_btn = QPushButton("＋")
        self._add_btn.setFixedSize(QSize(24, 20))
        self._add_btn.setToolTip("駒種を選んで追加 (編集モード時のみ)")
        self._add_btn.setStyleSheet(
            "QPushButton { background:#2e7d32; color:#ffffff; "
            "border:1px solid #1b5e20; border-radius:4px; font-weight:bold; }"
            "QPushButton:hover { background:#43a047; }"
            "QPushButton:disabled { background:#666; color:#aaa; }"
        )
        self._add_btn.setVisible(False)
        self._add_btn.clicked.connect(self.addRequested.emit)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(self._title)
        header.addStretch(1)
        header.addWidget(self._add_btn)

        self.list = QListWidget()
        self.list.setFlow(QListWidget.Flow.LeftToRight)
        self.list.setWrapping(True)
        self.list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list.setSpacing(2)
        self.list.itemClicked.connect(self._on_clicked)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 4, 6, 4)
        v.addLayout(header)
        v.addWidget(self.list)

    def set_edit_mode(self, on: bool) -> None:
        """編集モード時に "+" ボタンを表示/非表示。"""
        self._add_btn.setVisible(on)

    def setSelectedPieceId(self, pid: str | None) -> None:
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == pid:
                item.setBackground(QColor(THEME.selected_bg))
                item.setForeground(QColor(THEME.fg))
            else:
                item.setBackground(QColor("transparent"))
                item.setForeground(QColor(THEME.input_fg))

    def setPieces(self, pieces: list[Piece], selected_id: str | None = None) -> None:
        self.list.clear()
        # 同種駒を集計して表示
        for p in pieces:
            item = QListWidgetItem(p.kanji)
            f = QFont()
            f.setPointSize(14)
            f.setBold(True)
            item.setFont(f)
            item.setData(Qt.ItemDataRole.UserRole, p.id)
            item.setSizeHint(QSize(40, 40))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.list.addItem(item)
        self.setSelectedPieceId(selected_id)

    def _on_clicked(self, item: QListWidgetItem) -> None:
        pid = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(pid, str):
            self.pieceClicked.emit(pid)


class MoveListPanel(QFrame):
    rowSelected = Signal(int)  # cursor 位置 (snapshot index)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("MoveListPanel")
        self.setProperty("class", "PanelFrame")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        title = QLabel("MOVES")
        f = QFont()
        f.setPointSize(10)
        title.setFont(f)
        title.setStyleSheet(
            "color: rgba(128,128,128,0.9); letter-spacing: 1px;"
        )
        self.list = QListWidget()
        self.list.itemActivated.connect(self._on_activate)
        self.list.itemClicked.connect(self._on_activate)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 4, 6, 4)
        v.addWidget(title)
        v.addWidget(self.list)

    def setEntries(self, labels: list[str], cursor: int) -> None:
        self.list.clear()
        for i, lab in enumerate(labels):
            num = "—" if i == 0 else str(i)
            item = QListWidgetItem(f"{num:>3}: {lab}")
            self.list.addItem(item)
        if 0 <= cursor < self.list.count():
            self.list.setCurrentRow(cursor)

    def _on_activate(self, item: QListWidgetItem) -> None:
        self.rowSelected.emit(self.list.row(item))


# ---------------------------------------------------------------------------
# 選択状態
# ---------------------------------------------------------------------------


@dataclass
class Selection:
    src: tuple[int, int] | None = None
    arata_piece_id: str | None = None

    def clear(self) -> None:
        self.src = None
        self.arata_piece_id = None


# ---------------------------------------------------------------------------
# メインウィンドウ
# ---------------------------------------------------------------------------


class GungiWindow(QMainWindow):
    def __init__(self, game: Game) -> None:
        super().__init__()
        self.game = game
        self.selection = Selection()
        self.legal_dests: set[tuple[int, int]] = set()
        self.edit_mode = False

        self.setWindowTitle("軍議 - Gungi")
        self._move_labels: list[str]  # placeholder; will be populated each refresh
        self._build_toolbar()
        self._build_central()
        self._connect_signals()
        self.refresh()

    # ---- ツールバー ----

    def _build_toolbar(self) -> None:
        tb = QToolBar()
        tb.setMovable(False)
        tb.setStyleSheet(
            f"QToolBar {{ background:{COL_TOOLBAR_BG}; padding:6px; spacing:4px; }}"
            f"QToolButton {{ color:{COL_TOOLBAR_FG}; background:#2e7d32;"
            f"  border:1px solid #1b5e20; border-radius:4px; padding:6px 12px;"
            f"  font-weight:bold; }}"
            f"QToolButton:hover {{ background:#43a047; }}"
            f"QToolButton:pressed {{ background:#1b5e20; }}"
            f"QToolButton:disabled {{ color:#9c9c9c; background:#3e3e3e; }}"
            f"QToolButton::menu-indicator {{ image:none; width:0; }}"  # ▾ をテキストで出すので非表示
        )
        self.addToolBar(tb)
        # 新規対局プルダウン (初級 / 中級 / 上級)
        self.btn_new_game = QToolButton()
        self.btn_new_game.setText("新規対局 ▾")
        self.btn_new_game.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        new_menu = QMenu(self.btn_new_game)
        for diff, label in (
            (DifficultyLevel.INTRODUCTORY, "入門"),
            (DifficultyLevel.BEGINNER, "初級"),
            (DifficultyLevel.INTERMEDIATE, "中級"),
            (DifficultyLevel.ADVANCED, "上級"),
        ):
            act = new_menu.addAction(label)
            act.triggered.connect(
                lambda _checked=False, d=diff: self.on_new_game(d)
            )
        self.btn_new_game.setMenu(new_menu)
        tb.addWidget(self.btn_new_game)
        tb.addSeparator()
        self.act_first = tb.addAction("◀◀ 開始")
        self.act_first.triggered.connect(self.on_goto_start)
        self.act_back = tb.addAction("◀ 戻す")
        self.act_back.triggered.connect(self.on_undo)
        self.act_forward = tb.addAction("進める ▶")
        self.act_forward.triggered.connect(self.on_redo)
        self.act_last = tb.addAction("最新 ▶▶")
        self.act_last.triggered.connect(self.on_goto_end)
        tb.addSeparator()
        self.act_edit = tb.addAction("編集モード")
        self.act_edit.setCheckable(True)
        self.act_edit.toggled.connect(self.on_toggle_edit)
        self.act_turn = tb.addAction("手番切替")
        self.act_turn.triggered.connect(self.on_toggle_turn)
        self.act_clear = tb.addAction("盤面クリア")
        self.act_clear.triggered.connect(self.on_clear_board)
        self.act_add_piece = tb.addAction("駒追加")
        self.act_add_piece.triggered.connect(self.on_add_piece)
        self.act_phase = tb.addAction("段階切替")
        self.act_phase.triggered.connect(self.on_toggle_phase)
        tb.addSeparator()
        # 布陣段階 (中級/上級) 専用
        self.act_finish = tb.addAction("配置完了")
        self.act_finish.triggered.connect(self.on_finish_placement)

    # ---- 中央レイアウト ----

    def _build_central(self) -> None:
        self.board = BoardWidget(self.game)

        self.header_top = PlayerHeader(Side.Black)
        self.header_bot = PlayerHeader(Side.White)

        # 中央列: 後手バー / 盤 / 先手バー
        center = QWidget()
        cv = QVBoxLayout(center)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(6)
        cv.addWidget(self.header_top)
        cv.addWidget(self.board, 1)
        cv.addWidget(self.header_bot)

        # 左列: 黒手駒 / 黒捕獲駒
        self.black_hand = HandPanel("HAND")
        self.black_cap = HandPanel("CAPTURED")
        left = QWidget()
        left.setFixedWidth(190)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(6)
        lv.addWidget(self.black_hand)
        lv.addWidget(self.black_cap)

        # 右列: 棋譜 / 白手駒 / 白捕獲駒
        self.white_hand = HandPanel("HAND")
        self.white_cap = HandPanel("CAPTURED")
        self.move_list = MoveListPanel()
        right = QWidget()
        right.setFixedWidth(260)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(6)
        rv.addWidget(self.move_list, 1)
        rv.addWidget(self.white_hand)
        rv.addWidget(self.white_cap)

        # ルート
        root = QWidget()
        rh = QHBoxLayout(root)
        rh.setContentsMargins(8, 8, 8, 8)
        rh.setSpacing(8)
        rh.addWidget(left)
        rh.addWidget(center, 1)
        rh.addWidget(right)
        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar(self))

    def _connect_signals(self) -> None:
        self.board.cellClicked.connect(self.on_cell_clicked)
        self.black_hand.pieceClicked.connect(
            lambda pid: self.on_hand_clicked(Side.Black, pid, "hand")
        )
        self.black_cap.pieceClicked.connect(
            lambda pid: self.on_hand_clicked(Side.Black, pid, "captured")
        )
        self.white_hand.pieceClicked.connect(
            lambda pid: self.on_hand_clicked(Side.White, pid, "hand")
        )
        self.white_cap.pieceClicked.connect(
            lambda pid: self.on_hand_clicked(Side.White, pid, "captured")
        )
        # 各パネル + ボタン経由の追加
        self.black_hand.addRequested.connect(
            lambda: self.on_panel_add(Side.Black, "hand")
        )
        self.black_cap.addRequested.connect(
            lambda: self.on_panel_add(Side.Black, "captured")
        )
        self.white_hand.addRequested.connect(
            lambda: self.on_panel_add(Side.White, "hand")
        )
        self.white_cap.addRequested.connect(
            lambda: self.on_panel_add(Side.White, "captured")
        )
        self.move_list.rowSelected.connect(self.on_move_list_clicked)

    # ---- 描画更新 ----

    def refresh(self) -> None:
        self.board.selection_src = self.selection.src
        self.board.legal_dests = set(self.legal_dests)
        self.board.last_move = self._last_move_coords()
        # 布陣中で手駒選択中なら、自陣ゾーンを強調
        if (
            self.game.phase is GamePhase.PLACEMENT
            and self.selection.arata_piece_id is not None
        ):
            self.board.placement_zone_y = self.game._own_territory_y(
                self.game.turn, self.game.board.height
            )
        else:
            self.board.placement_zone_y = None
        self.board.update()

        self.header_top.setActive(self.game.turn is Side.Black)
        self.header_bot.setActive(self.game.turn is Side.White)

        self.black_hand.setPieces(self.game.hand[Side.Black], self.selection.arata_piece_id)
        self.black_cap.setPieces(self.game.captured_by[Side.Black], self.selection.arata_piece_id)
        self.white_hand.setPieces(self.game.hand[Side.White], self.selection.arata_piece_id)
        self.white_cap.setPieces(self.game.captured_by[Side.White], self.selection.arata_piece_id)
        # パネルの「+」ボタンを編集モード時のみ表示
        for panel in (self.black_hand, self.black_cap, self.white_hand, self.white_cap):
            panel.set_edit_mode(self.edit_mode)

        labels = getattr(self.game, "_snap_labels", None)
        if labels is None:
            labels = ["開始"] * len(self.game._snapshots)
        self.move_list.setEntries(labels, self.game._cursor)

        is_placement = self.game.phase is GamePhase.PLACEMENT

        # ナビ・モード系ボタン
        self.act_first.setEnabled(self.game.can_undo())
        self.act_back.setEnabled(self.game.can_undo())
        self.act_forward.setEnabled(self.game.can_redo())
        self.act_last.setEnabled(self.game.can_redo())
        self.act_clear.setEnabled(self.edit_mode)
        self.act_turn.setEnabled(self.edit_mode)
        self.act_add_piece.setEnabled(self.edit_mode)
        self.act_phase.setEnabled(self.edit_mode)
        # 配置完了はゲーム操作なので編集モード中は無効化
        self.act_finish.setEnabled(is_placement and not self.edit_mode)

        # ステータス
        if self.edit_mode:
            self.statusBar().showMessage(
                f"[編集モード] 手番: {self._turn_label(self.game.turn)} / 手数: {self.game.move_count}"
            )
            return
        if is_placement:
            n_hand = len(self.game.hand[self.game.turn])
            on_board = self.game._count_own_pieces_on_board(self.game.turn)
            sui_placed = self.game.board.find_sui(self.game.turn) is not None
            done_w = self.game._placement_done[Side.White]
            done_b = self.game._placement_done[Side.Black]
            phase_label = (
                "先手の配置中" if self.game.turn is Side.White else "後手の配置中"
            )
            other_done = " (相手は配置完了済み)" if (
                (self.game.turn is Side.White and done_b)
                or (self.game.turn is Side.Black and done_w)
            ) else ""
            if not sui_placed:
                hint = " — まず帥を自陣に置いてください"
            elif self.selection.arata_piece_id:
                hint = " — 配置先の自陣マスをクリック"
            else:
                hint = " — 駒を選んで自陣マスをクリック / 完了したら「配置完了」"
            self.statusBar().showMessage(
                f"[{phase_label}{other_done}] 残手駒: {n_hand} / 配置済: {on_board}{hint}"
            )
            return
        if self.game.winner is not None:
            self.statusBar().showMessage(
                f"勝者: {self._turn_label(self.game.winner)} (帥捕獲)"
            )
            return
        n_legal = len(self.game.legal_actions())
        sennichi = " [千日手]" if self.game.is_sennichite() else ""
        mode = ""
        if self.selection.arata_piece_id:
            mode = " — 新モード"
        elif self.selection.src is not None:
            mode = f" — 移動元: {self.selection.src}"
        self.statusBar().showMessage(
            f"手番: {self._turn_label(self.game.turn)} / 手数: {self.game.move_count}"
            f" / 合法手: {n_legal}{sennichi}{mode}"
        )

    @staticmethod
    def _turn_label(side: Side) -> str:
        return "先手 (白)" if side is Side.White else "後手 (黒)"

    def _last_move_coords(self) -> tuple[tuple[int, int], tuple[int, int]] | None:
        labels = getattr(self.game, "_snap_labels", [])
        if not labels or self.game._cursor == 0:
            return None
        # 直近の手をパース (フォーマット: "A→B" / "A ツケ→ B" / "新→ B")
        lab = labels[self.game._cursor]
        return _parse_move_coords(lab)

    # ---- イベント ----

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._reset_selection()
            self.refresh()
        elif event.key() == Qt.Key.Key_Left:
            self.on_undo()
        elif event.key() == Qt.Key.Key_Right:
            self.on_redo()
        else:
            super().keyPressEvent(event)

    def on_cell_clicked(self, x: int, y: int) -> None:
        coord = (x, y)
        if self.edit_mode:
            self._handle_edit_click(coord)
            return
        if self.game.phase is GamePhase.PLACEMENT:
            self._handle_placement_click(coord)
            return
        if self.game.winner is not None:
            return
        if self.selection.arata_piece_id is not None:
            self._do_arata(coord)
            return
        top = self.game.board.top_piece(*coord)
        if self.selection.src is None:
            if top is not None and top.color is self.game.turn:
                self.selection.src = coord
                self._compute_legal_dests()
            self.refresh()
            return
        if coord == self.selection.src:
            self._reset_selection()
            self.refresh()
            return
        self._do_move_or_stack(self.selection.src, coord)

    def _handle_placement_click(self, coord: tuple[int, int]) -> None:
        if self.selection.arata_piece_id is None:
            self.statusBar().showMessage(
                "布陣中: まず自分の手駒 (現手番側) を選択してください", 3000
            )
            return
        try:
            self.game.apply_placement(self.selection.arata_piece_id, *coord)
        except ValueError as e:
            QMessageBox.warning(self, "配置できません", str(e))
            return
        self._reset_selection()
        self.refresh()

    def on_hand_clicked(self, side: Side, piece_id: str, source: str = "hand") -> None:
        if self.edit_mode:
            self._handle_edit_hand_click(side, piece_id, source)
            return
        if self.game.winner is not None:
            return
        if source == "captured":
            # 通常モードでは捕獲駒も新で再利用可 (apply_arata 側で hand+captured 検索)
            pass
        if side is not self.game.turn:
            QMessageBox.information(self, "新", "相手側の駒は使えません")
            return
        if self.selection.arata_piece_id == piece_id:
            self._reset_selection()
        else:
            self._reset_selection()
            self.selection.arata_piece_id = piece_id
        self.refresh()

    def _handle_edit_hand_click(
        self, side: Side, piece_id: str, source: str
    ) -> None:
        side_label = "白" if side is Side.White else "黒"
        list_label = "手駒" if source == "hand" else "捕獲駒"
        ans = QMessageBox.question(
            self, "駒の削除",
            f"{side_label}の{list_label}からこの駒を削除しますか?",
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            if source == "hand":
                self.game.edit_remove_from_hand(piece_id, side)
            else:
                self.game.edit_remove_captured(piece_id, side)
        except ValueError as e:
            QMessageBox.warning(self, "削除失敗", str(e))
            return
        self.refresh()

    def on_move_list_clicked(self, row: int) -> None:
        target = max(0, min(row, len(self.game._snapshots) - 1))
        self.game._restore_snapshot(target)
        self._reset_selection()
        self.refresh()

    # ---- ナビ / 編集 ----

    def on_new_game(self, difficulty: DifficultyLevel) -> None:
        label = {
            DifficultyLevel.INTRODUCTORY: "入門 (初期配置①から対局, 特殊駒なし)",
            DifficultyLevel.BEGINNER: "初級 (初期配置②から対局, 弓のみ)",
            DifficultyLevel.INTERMEDIATE: "中級 (布陣段階から開始)",
            DifficultyLevel.ADVANCED: "上級 (布陣段階から開始)",
        }.get(difficulty, str(difficulty))
        ans = QMessageBox.question(
            self,
            "新規対局",
            f"現在の対局・履歴を破棄して、{label}を開始しますか?",
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        # 編集モードを確実に対局モードへ戻す (UI と内部フラグ両方)
        self.act_edit.setChecked(False)
        self.edit_mode = False
        self.game.reset(GameConfig(difficulty=difficulty))
        self._reset_selection()

        if difficulty is not DifficultyLevel.BEGINNER:
            self.statusBar().showMessage(
                "布陣段階: 自分の手駒を選んで自陣マスをクリック。"
                "両陣の帥を置き終えたら「布陣完了」で対局開始。",
                10000,
            )
        self.refresh()

    def on_finish_placement(self) -> None:
        if self.game.phase is not GamePhase.PLACEMENT:
            return
        try:
            self.game.finish_placement()
        except ValueError as e:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Critical)
            box.setWindowTitle("配置完了できません")
            box.setText(str(e))
            box.exec()
            return
        self._reset_selection()
        self.refresh()

    def on_undo(self) -> None:
        if self.game.undo():
            self._reset_selection()
            self.refresh()

    def on_redo(self) -> None:
        if self.game.redo():
            self._reset_selection()
            self.refresh()

    def on_goto_start(self) -> None:
        self.game.goto_start()
        self._reset_selection()
        self.refresh()

    def on_goto_end(self) -> None:
        self.game.goto_end()
        self._reset_selection()
        self.refresh()

    def on_toggle_edit(self, on: bool) -> None:
        self.edit_mode = on
        self._reset_selection()
        self.refresh()

    def on_toggle_turn(self) -> None:
        if not self.edit_mode:
            return
        self.game.edit_set_turn(self.game.turn.opponent())
        self.refresh()

    def on_clear_board(self) -> None:
        if not self.edit_mode:
            return
        ans = QMessageBox.question(
            self, "確認", "盤面の全駒を削除しますか? (戻す で復元できます)"
        )
        if ans == QMessageBox.StandardButton.Yes:
            self.game.edit_clear_board()
            self._reset_selection()
            self.refresh()

    def on_add_piece(self) -> None:
        if not self.edit_mode:
            return
        dlg = AddPieceDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if dlg.piece_type is None or dlg.color is None or dlg.target is None:
            return
        try:
            if dlg.target == "hand":
                self.game.edit_add_to_hand(dlg.piece_type, dlg.color)
            else:
                self.game.edit_add_captured(dlg.piece_type, dlg.color)
        except ValueError as e:
            QMessageBox.warning(self, "追加失敗", str(e))
            return
        self.refresh()

    def on_panel_add(self, side: Side, source: str) -> None:
        """各パネルの「+」ボタンが押されたとき。色と追加先はパネルに紐付く。"""
        if not self.edit_mode:
            return
        side_label = "白" if side is Side.White else "黒"
        list_label = "手駒" if source == "hand" else "捕獲駒"
        dlg = SimpleAddDialog(self, f"{side_label}の{list_label}に追加")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if dlg.piece_type is None:
            return
        try:
            if source == "hand":
                self.game.edit_add_to_hand(dlg.piece_type, side)
            else:
                self.game.edit_add_captured(dlg.piece_type, side)
        except ValueError as e:
            QMessageBox.warning(self, "追加失敗", str(e))
            return
        self.refresh()

    def on_toggle_phase(self) -> None:
        if not self.edit_mode:
            return
        if self.game.phase is GamePhase.PLACEMENT:
            self.game.edit_set_phase(GamePhase.PLAY)
        else:
            self.game.edit_set_phase(GamePhase.PLACEMENT)
        self._reset_selection()
        self.refresh()

    # ---- 内部処理 ----

    def _reset_selection(self) -> None:
        self.selection.clear()
        self.legal_dests.clear()

    def _compute_legal_dests(self) -> None:
        self.legal_dests.clear()
        if self.selection.src is None:
            return
        for act in self.game.legal_actions():
            if act.type in (ActionType.MOVE, ActionType.STACK) and act.src == self.selection.src:
                self.legal_dests.add(act.dst)

    def _available_choices(
        self, src: tuple[int, int], dst: tuple[int, int]
    ) -> list[Choice]:
        out: list[Choice] = []
        seen: set[ActionType] = set()
        for act in self.game.legal_actions():
            if act.src != src or act.dst != dst:
                continue
            if act.type is ActionType.MOVE and ActionType.MOVE not in seen:
                top = self.game.board.top_piece(*dst)
                if top is not None and top.color is not self.game.turn:
                    out.append(Choice.CAPTURE)
                else:
                    out.append(Choice.MOVE)
                seen.add(ActionType.MOVE)
            elif act.type is ActionType.STACK and ActionType.STACK not in seen:
                out.append(Choice.STACK)
                seen.add(ActionType.STACK)
        return out

    def _do_move_or_stack(
        self, src: tuple[int, int], dst: tuple[int, int]
    ) -> None:
        if dst not in self.legal_dests:
            self.statusBar().showMessage("非合法な着手です", 3000)
            return
        choices = self._available_choices(src, dst)
        if not choices:
            return
        if len(choices) == 1 and choices[0] is Choice.MOVE:
            chosen = Choice.MOVE
        else:
            dlg = ChoiceDialog(self, choices, f"{src} → {dst}")
            if dlg.exec() != QDialog.DialogCode.Accepted or dlg.selected is None:
                return
            chosen = dlg.selected
        action_type = ActionType.STACK if chosen is Choice.STACK else ActionType.MOVE
        try:
            self.game.apply(Action(action_type, src=src, dst=dst))
        except ValueError as e:
            self.statusBar().showMessage(f"失敗: {e}", 3000)
            return
        self._reset_selection()
        self.refresh()
        if self.game.winner is not None:
            QMessageBox.information(
                self, "決着", f"{self._turn_label(self.game.winner)} の勝ち (帥捕獲)"
            )

    def _do_arata(self, dst: tuple[int, int]) -> None:
        dlg = ChoiceDialog(self, [Choice.ARATA], f"({dst[0]},{dst[1]}) に打つ")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.game.apply(Action(
                ActionType.ARATA,
                dst=dst,
                hand_piece_id=self.selection.arata_piece_id,
            ))
        except ValueError as e:
            self.statusBar().showMessage(f"新失敗: {e}", 3000)
            return
        self._reset_selection()
        self.refresh()

    def _handle_edit_click(self, coord: tuple[int, int]) -> None:
        top = self.game.board.top_piece(*coord)
        dlg = EditDialog(self, top, coord)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            if dlg.action is EditAction.PLACE:
                assert dlg.piece_type is not None and dlg.color is not None
                self.game.edit_place(dlg.piece_type, dlg.color, *coord)
            elif dlg.action is EditAction.REMOVE:
                self.game.edit_remove_top(*coord)
        except ValueError as e:
            self.statusBar().showMessage(f"編集失敗: {e}", 3000)
            return
        self.refresh()


# ---------------------------------------------------------------------------
# 棋譜ラベルのパース (直前手のハイライト用)
# ---------------------------------------------------------------------------


def _parse_move_coords(label: str) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """ '(1,2)→(1,3)' のようなラベルから (src, dst) 座標を抽出。"""
    import re
    nums = re.findall(r"\((\d+),(\d+)\)", label)
    if len(nums) < 2:
        return None
    src = (int(nums[0][0]), int(nums[0][1]))
    dst = (int(nums[1][0]), int(nums[1][1]))
    return src, dst


# ---------------------------------------------------------------------------
# 起動
# ---------------------------------------------------------------------------


def _install_sigint_handler(app: QApplication) -> QTimer:
    """ターミナルからの Ctrl+C で QApplication を終了させる。

    Qt のイベントループは C 側で回るため Python の signal ハンドラが
    呼ばれない。短い QTimer を回して定期的に Python へ制御を返すことで
    SIGINT を拾えるようにする。返す QTimer は呼び出し側で GC されないよう保持。
    """
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    timer = QTimer()
    timer.start(200)
    timer.timeout.connect(lambda: None)  # no-op: Python に処理機会を与えるだけ
    return timer


def main() -> None:
    app = QApplication(sys.argv)
    _sigint_timer = _install_sigint_handler(app)  # noqa: F841 (GC 防止のため保持)

    global THEME
    THEME = Theme.detect(app)
    apply_global_stylesheet(app)

    # システムテーマ変更をリアルタイム追従 (PySide6 6.5+)
    try:
        app.styleHints().colorSchemeChanged.connect(
            lambda _scheme: _on_theme_change(app)
        )
    except (AttributeError, Exception):
        pass

    # 起動時は入門編の既定配置で開始 (中級/上級は空盤なので明示的に「新規対局」から選ぶ)
    game = Game(config=GameConfig(difficulty=DifficultyLevel.INTRODUCTORY))
    win = GungiWindow(game)
    win.resize(1200, 820)
    win.show()
    sys.exit(app.exec())


def _on_theme_change(app: QApplication) -> None:
    global THEME
    THEME = Theme.detect(app)
    apply_global_stylesheet(app)
    # ヘッダーの色などインライン QSS のものを再適用するため、全ウィンドウを再描画
    for w in app.topLevelWidgets():
        w.update()


if __name__ == "__main__":
    main()
