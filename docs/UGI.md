# UGI - Universal Gungi Interface

将棋の USI (Universal Shogi Interface) に相当する、軍儀 (Gungi) 用の
エンジン-GUI 通信プロトコル。GUI とエンジンが標準入出力 (stdin/stdout)
を介して文字列メッセージを交換する。

## 目次

- [位置付け](#位置付け)
- [メッセージ形式](#メッセージ形式)
- [駒コード](#駒コード)
- [座標](#座標)
- [アクション記法](#アクション記法)
- [GUI → Engine コマンド](#gui--engine-コマンド)
- [Engine → GUI 応答](#engine--gui-応答)
- [標準オプション](#標準オプション)
- [詰み探索 (go mate)](#詰み探索-go-mate)
- [セッション例](#セッション例)
- [エンジン実装ガイド](#エンジン実装ガイド)
- [関連仕様](#関連仕様)

## 位置付け

```
GUI (gui.py)
    ↕ UGI (本仕様)
Engine (engine_*.py / 外部プロセス)
```

- **GUI**: 盤面表示・ユーザ操作・棋譜管理を担う
- **Engine**: 局面を解析して次の手や詰み手順を返す
- **UGI**: 両者の境界に立つ文字列プロトコル

## メッセージ形式

- **行ベース**: 1 行 = 1 メッセージ。改行 (LF) で区切る
- **方向**: GUI → Engine と Engine → GUI の二方向
- **エンコーディング**: UTF-8
- **トークン区切り**: 半角スペース 1 つ以上
- **コメント**: 仕様上は無し。`info string ...` を擬似的に用いることはある

## 駒コード

2 文字 ASCII。色プレフィクスは `w` (先手・白) / `b` (後手・黒)。

| 駒 | コード | 駒 | コード |
|---|---|---|---|
| 帥 | `Su` | 兵 | `Hy` |
| 大 | `Ta` | 弓 | `Ym` |
| 中 | `Cj` | 筒 | `Tt` |
| 小 | `Sh` | 砲 | `Od` |
| 侍 | `Sm` | 謀 | `Bo` |
| 槍 | `Ya` | 馬 | `Ki` |
| 忍 | `Sn` | 砦 | `To` |

例:
- `wSu` = 先手の帥
- `bTa` = 後手の大

## 座標

- `x` (列) と `y` (行) は **0..8** の 1 桁
- マス指定は `<x><y>` の 2 文字連結
- 例: `42` = (col 4, row 2)

> GFEN 内の座標も同じ 0-based。`.gsa` 棋譜は別仕様 (1-based) なので混同しないこと。

## アクション記法

USI 準拠の文字列形式。

| 種類 | 記法 | 例 | 意味 |
|---|---|---|---|
| 移動 (MOVE) | `<sx><sy><dx><dy>` | `4243` | (4,2) から (4,3) へ移動 |
| ツケ (STACK) | `<sx><sy><dx><dy>+` | `4243+` | (4,2) の駒を (4,3) の上にツケる |
| 打ち (ARATA/PLACEMENT) | `<駒>*<dx><dy>` | `Hy*43` | 手駒の兵を (4,3) に打つ |
| 配置完了 | `done` | | 布陣段階の終了宣言 |
| 投了 | `resign` | | 投了 |
| 待機 | `null` | | デバッグ用 no-op |

末尾の `+` は将棋 USI の「成り」を軍儀の「ツケ」 choice に流用したもの。

`*` は phase により意味が変わる:
- **PLACEMENT (布陣)** → 手駒から盤面へ配置
- **PLAY (対局)** → 手駒/捕獲駒から「新 (あらた)」として打つ

## GUI → Engine コマンド

### `ugi`

プロトコル開始の合図。Engine は自身の情報と受付オプションを返してから
`ugiok` で終了することを示す。

応答: [`id`](#id-name--id-author), [`option`](#option), [`ugiok`](#ugiok)

### `isready`

準備確認。Engine は初期化が完了したら [`readyok`](#readyok) を返す。

### `uginewgame`

新規対局通知。Engine は内部状態をリセットする。`setoption Difficulty` が
先行していれば、その難易度で新規対局を開始する。

応答: 無し (情報的に `info string` を返してもよい)

### `position <spec> [moves <m1> <m2> ...]`

対局局面の設定。

`<spec>`:
- `startpos[:<difficulty>]` — 既定の開始局面 (難易度別)
- `gfen <11 フィールド>` — 任意局面 ([GFEN 仕様](GFEN.md) 参照)

`moves` 以降の手を順に適用する。

例:
```
position startpos:intro moves 4243 4645
position gfen 9/9/4|wSu|4/9/9/9/9/9/4|bSu|4 w pa - - - - 0 0 0 intro
```

### `go [parameters...]`

通常の探索を依頼。

パラメータ (key value のペア、kv_pairs 形式):

| パラメータ | 型 | 意味 |
|---|---|---|
| `movetime <ms>` | int | この手にかける最大時間 (ミリ秒) |
| `depth <n>` | int | 最大探索深さ |
| `nodes <n>` | int | 最大ノード数 |
| `infinite` | flag | 無制限 (stop コマンドまで継続) |

応答:
1. (任意) [`info ...`](#info) を 0 回以上
2. [`bestmove <move>`](#bestmove) で終了

### `go mate <N|infinite>`

任意局面からの詰み探索を依頼。詳細は [詰み探索 (go mate)](#詰み探索-go-mate) 参照。

- `<N>`: 最大攻方手数 (詰み手順の長さ)
- `infinite`: 無制限 (実装側で打ち切り上限を設定可)

応答: [`checkmate ...`](#checkmate)

### `stop`

進行中の思考を中断。Engine は現時点の最善手を返して終了。

応答: 通常の `bestmove` (`go` 中断時) または `checkmate timeout` (`go mate` 中断時)

### `setoption name <key> value <value>`

オプション設定。受付可能な名前は Engine が `ugi` 応答時の [`option`](#option) で公開。

例:
```
setoption name Difficulty value beginner
```

### `ponderhit`

(予約) 相手の予想手が当たった通知。現在の参考実装では no-op。

### `quit`

Engine 終了。

## Engine → GUI 応答

### `id name <name>` / `id author <author>`

Engine の自己紹介。`ugi` 直後に 1 回ずつ返す。

### `ugiok`

`ugi` 応答の終端。これを返した時点で Engine は GUI からのコマンドを
受け付けられる状態。

### `readyok`

`isready` への応答。

### `option name <key> type <type> default <value> [...]`

受付可能なオプションを公開。`ugi` への応答中に 0 個以上含めて良い。

`<type>` は USI と同じ:
- `check`: bool (`true` / `false`)
- `spin`: 整数 (`default`, `min`, `max` を持つ)
- `combo`: 列挙 (`var v1 var v2 ...` で値を列挙)
- `button`: 押下のみ (`value` 無し)
- `string`: 文字列

例:
```
option name Difficulty type combo default intro var intro var beginner var intermediate var advanced
```

### `info ...`

探索情報。`go` 応答中に 0 回以上送出してよい。

代表的なフィールド (USI 準拠):

| フィールド | 意味 |
|---|---|
| `depth <n>` | 探索深さ |
| `seldepth <n>` | 選択的探索深さ |
| `score cp <eval>` | センチポーン単位の評価値 |
| `score mate <n>` | 詰みまでの手数 (正: 自分が詰み、負: 相手が詰み) |
| `nodes <n>` | 探索ノード数 |
| `time <ms>` | 経過時間 |
| `nps <n>` | ノード/秒 |
| `pv <m1> <m2> ...` | 最善応手列 (Principal Variation) |
| `string <text>` | 任意メッセージ (GUI 表示用) |

例:
```
info depth 5 score cp 120 nodes 50000 time 1200 pv 4243 5868 3132
info string thinking...
```

### `bestmove <move> [ponder <move>]`

`go` への最終応答。`<move>` は [アクション記法](#アクション記法) の文字列。
`ponder` は予想される相手の応手 (オプション)。

例:
```
bestmove 4243
bestmove Hy*42 ponder 5868
```

### `checkmate ...`

`go mate` への応答。4 形のいずれか:

| 応答 | 意味 |
|---|---|
| `checkmate <m1> <m2> ...` | 詰み手順 (攻方・受方の手が交互) |
| `checkmate nomate` | この局面では詰まないことを証明 |
| `checkmate timeout` | 制限時間/手数内に解けなかった (打ち切り) |
| `checkmate notimplemented` | このエンジンは詰み探索未対応 |

## 標準オプション

### Difficulty

軍儀の難易度モード。`combo` 型。

| 値 | 内容 |
|---|---|
| `intro` | 入門編 (初期配置①、特殊駒なし、2 段ツケ、帥ツケ不可) |
| `beginner` | 初級編 (初期配置②、弓のみ、2 段ツケ、帥ツケ不可) |
| `intermediate` | 中級編 (自由配置、全種特殊駒、2 段ツケ、帥ツケ可) |
| `advanced` | 上級編 (自由配置、全種特殊駒、3 段ツケ、帥ツケ可) |

適用タイミングの優先順位:

1. `position startpos:<diff>` の明示指定 (最優先)
2. GFEN 11 番目フィールド (`position gfen ...` の場合)
3. `setoption Difficulty` で設定された pending 値 (次の `uginewgame` または `position startpos` 難易度未指定時)
4. デフォルト (`intro`)

## 詰み探索 (go mate)

### コマンド

```
go mate <N>          # N 手以内の詰みを探索 (N は攻方手数)
go mate infinite     # 無制限 (実装側で打ち切り上限可)
```

### 応答ステータス

| ステータス | 意味 | 続く情報 |
|---|---|---|
| `mate` | 強制詰みを発見 | 詰み手順 (UGI アクション記法、攻方/受方交互) |
| `nomate` | この局面では詰まないことを証明済み | 無し |
| `timeout` | 制限時間/手数/ノード数を超過 | 無し |
| `notimplemented` | このエンジンは詰み探索未対応 | 無し |

### 例

```
GUI:    position gfen 9/9/9/9/4|bSu|4|/4|wHy|4/9/9/9 w pa - - - - 0 0 0 intro
GUI:    go mate 3
Engine: info string searching mate in 3
Engine: checkmate 4445
```

`4445` = 白の兵を (4,4) から (4,5) へ移動して黒帥を捕獲 (1 手詰)。

### 通常 `go` との関係

- `go` と `go mate` は同じエンジンプロセスが処理する (やねうら王等と同じ設計)
- `go` 中に `stop` が来たら現時点の最善手で `bestmove`
- `go mate` 中に `stop` が来たら `checkmate timeout`
- エンジンが詰み探索を実装しない場合は `checkmate notimplemented` を返す
  (`MateResult(kind="notimplemented")` がデフォルト)

## セッション例

### 通常対局 (1 手分)

```
GUI:    ugi
Engine: id name SampleEngine
Engine: id author Someone
Engine: option name Difficulty type combo default intro var intro var beginner var intermediate var advanced
Engine: ugiok
GUI:    isready
Engine: readyok
GUI:    setoption name Difficulty value beginner
GUI:    uginewgame
GUI:    position startpos moves 4243
GUI:    go movetime 1000
Engine: info depth 3 score cp 12 nodes 1234 time 800 pv 3424
Engine: bestmove 3424
```

### 詰み探索

```
GUI:    position gfen <詰将棋風の局面> moves
GUI:    go mate 5
Engine: info string mate search depth=3
Engine: checkmate 4334 5444 3344
```

3 手詰: 白 (4,3)→(3,4) → 黒 (5,4)→(4,4) → 白 (3,3)→(4,4) で帥捕獲。

## エンジン実装ガイド

最小実装は `engine_stub.py` の `StubEngine` を参照。

### 基底クラス

```python
from protocol import UGIHandler, encode_move, MateResult
from game import GamePhase

class MyEngine(UGIHandler):
    NAME = "MyEngine"
    AUTHOR = "Author"

    def search(self, params: dict[str, str]) -> str:
        """通常探索。UGI アクション記法を返す。"""
        ...

    def search_mate(self, max_moves: int | None) -> MateResult:
        """詰み探索 (任意)。実装しなければデフォルトの notimplemented が返る。"""
        return MateResult(kind="mate", moves=("4243", "5868"))
```

### 必須オーバーライド

- `search(self, params)`: `go [movetime/depth/...]` の応答。アクション記法の 1 手を返す。

### 任意オーバーライド

- `search_mate(self, max_moves)`: `go mate` の応答。デフォルトは `notimplemented`。
- `cmd_setoption(self, args)`: 独自オプション処理。デフォルトは `Difficulty` のみ。
- その他 `cmd_*`: 各 UGI コマンドのカスタマイズ。

### REPL 起動

```python
if __name__ == "__main__":
    MyEngine().run_repl()
```

`run_repl()` は stdin から 1 行ずつ読み、`handle(line)` で振り分けて
stdout に応答を吐く簡易ループ。エンジンを `python engine_*.py` で起動する
だけで GUI とサブプロセス IPC ができる。

## 関連仕様

- [GFEN](GFEN.md) — 局面のシリアライズ形式
- [GSA](GSA.md) — 棋譜ファイルフォーマット
