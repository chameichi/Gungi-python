"""GUI ⇄ AI エンジン サブプロセス通信ブリッジ.

`QProcess` を使ってエンジン (例: `engine_stub.py`) を起動し、UGI 文字列を
行単位で送受信する。受信は `bestmove` / `info` を Qt シグナルで通知。

GUI 側は以下のように使う:

    bridge = EngineBridge(parent=self)
    bridge.bestmove_received.connect(self._on_engine_bestmove)
    bridge.start("python", ["engine_stub.py"])
    bridge.send("ugi")
    bridge.send("isready")
    bridge.send("setoption name Difficulty value intro")
    bridge.send("uginewgame")
    bridge.send("position startpos:intro")
    bridge.send("go movetime 1000")
    # bestmove_received(move_str) で着手を受け取る
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QProcess, Signal


class EngineBridge(QObject):
    """エンジンサブプロセスとの行ベース通信ラッパ。"""

    # bestmove / info / 任意行の通知
    bestmove_received = Signal(str)
    info_received = Signal(str)
    line_received = Signal(str)
    # プロセス終了 (異常終了を含む)
    finished = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.proc = QProcess(self)
        self.proc.readyReadStandardOutput.connect(self._on_stdout)
        self.proc.readyReadStandardError.connect(self._on_stderr)
        self.proc.finished.connect(self._on_finished)
        self._buffer = ""

    # ---- ライフサイクル ----

    def start(self, command: str, args: list[str]) -> None:
        """エンジンを起動。`command args...` の形で実行される。"""
        self.proc.start(command, args)
        self.proc.waitForStarted(5000)

    def stop(self) -> None:
        """`quit` を送ってからプロセスを終了させる。"""
        if self.proc.state() != QProcess.ProcessState.NotRunning:
            self.send("quit")
            if not self.proc.waitForFinished(2000):
                self.proc.kill()
                self.proc.waitForFinished(1000)

    def is_running(self) -> bool:
        return self.proc.state() == QProcess.ProcessState.Running

    # ---- 送受信 ----

    def send(self, line: str) -> None:
        """1 行送る。末尾改行は付与する。"""
        if not self.is_running():
            return
        self.proc.write((line + "\n").encode("utf-8"))

    def _on_stdout(self) -> None:
        data = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip("\r")
            if not line:
                continue
            self._dispatch(line)

    def _on_stderr(self) -> None:
        data = bytes(self.proc.readAllStandardError()).decode("utf-8", "replace")
        # stderr はログ用途として line_received に流す
        for line in data.splitlines():
            if line:
                self.line_received.emit(f"[stderr] {line}")

    def _on_finished(self, exit_code: int) -> None:
        self.finished.emit(exit_code)

    def _dispatch(self, line: str) -> None:
        self.line_received.emit(line)
        if line.startswith("bestmove "):
            # bestmove <move> [ponder <move>] → 先頭の move のみ取り出し
            tokens = line.split()
            if len(tokens) >= 2:
                self.bestmove_received.emit(tokens[1])
            return
        if line.startswith("info "):
            self.info_received.emit(line)
            return
        # ugiok / readyok / id / option など他のメッセージは line_received のみ
