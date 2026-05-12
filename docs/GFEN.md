# GFEN - Gungi Forsyth-Edwards Notation

軍儀の任意局面を 1 行のテキストで表現するシリアライズ形式。
チェスの FEN / 将棋の SFEN に相当する位置表記。

## 目次

- [概要](#概要)
- [フォーマット](#フォーマット)
- [board セクション](#board-セクション)
- [その他のフィールド](#その他のフィールド)
- [特殊形 (startpos)](#特殊形-startpos)
- [例](#例)
- [用途](#用途)

## 概要

- 1 行の ASCII 文字列
- 11 フィールド (半角スペース区切り)
- 駒の配置・手駒・捕獲駒・手番・進行段階・難易度などを完全に表現
- UGI プロトコル (`position gfen ...`) や棋譜ファイルの初期局面記述に使用

## フォーマット

```
<board> <turn> <phase> <hand_w> <hand_b> <cap_w> <cap_b> <done_w> <done_b> <ply> <diff>
```

| # | フィールド | 型 | 説明 |
|---|---|---|---|
| 1 | `board` | string | 盤面 (詳細は[board セクション](#board-セクション)) |
| 2 | `turn` | `w` \| `b` | 手番 |
| 3 | `phase` | `pl` \| `pa` \| `fi` | 進行段階 (placement / play / finished) |
| 4 | `hand_w` | string | 先手の手駒 (駒種コードを `,` 区切り、無ければ `-`) |
| 5 | `hand_b` | string | 後手の手駒 |
| 6 | `cap_w` | string | 先手の捕獲駒 |
| 7 | `cap_b` | string | 後手の捕獲駒 |
| 8 | `done_w` | `0` \| `1` | 先手の布陣完了フラグ |
| 9 | `done_b` | `0` \| `1` | 後手の布陣完了フラグ |
| 10 | `ply` | int | 手数 (累計) |
| 11 | `diff` | `intro` \| `beginner` \| `intermediate` \| `advanced` | 難易度 |

## board セクション

### 構造

```
<rank 8>/<rank 7>/...../<rank 1>/<rank 0>
```

- 9 ランクを `/` で区切る
- 上から下 (`y=8` → `y=0`)
- 各ランクは 9 セルを `|` で区切る

### セルの表現

| 種類 | 記法 | 例 |
|---|---|---|
| 空きマス | 連続空き数の数字 (1-9) | `3` = 空き 3 マス連続 |
| 1 駒 | 3 字 (色 1 字 + 駒コード 2 字) | `wSu` = 先手の帥 |
| スタック | 駒を `+` で連結 (下から上へ) | `wHy+wSm` = 兵の上に侍 |

### ランクの圧縮

連続する空きマスは 1 つの数字にまとめる。

例: 「空き 4 + 駒 1 つ + 空き 4」は `4|wSu|4` (3 セル分の表現)。

### 例: 初期配置①

```
3|bCj|bSu|bTa|3/1|bSn|2|bYa|2|bSn|1/bHy|1|bTo|bSm|bHy|bSm|bTo|1|bHy/9/9/9/wHy|1|wTo|wSm|wHy|wSm|wTo|1|wHy/1|wSn|2|wYa|2|wSn|1/3|wTa|wSu|wCj|3
```

各ランクの内訳:

| y | 内容 |
|---|---|
| 8 | 後手バックランク (中・帥・大) |
| 7 | 後手 2 段目 (忍 槍 忍) |
| 6 | 後手 3 段目 (兵・砦・侍・兵・侍・砦・兵) |
| 5,4,3 | 空 |
| 2 | 先手 3 段目 |
| 1 | 先手 2 段目 |
| 0 | 先手バックランク |

## その他のフィールド

### turn / phase

| 値 | 意味 |
|---|---|
| `w` | 先手 (白) の手番 |
| `b` | 後手 (黒) の手番 |
| `pl` | PLACEMENT (布陣段階) |
| `pa` | PLAY (対局段階) |
| `fi` | FINISHED (終局) |

### 手駒 / 捕獲駒

駒種コード (色プレフィクス無し、2 文字) を `,` 区切りで列挙。空は `-`。

例:
- `Sh,Sh,Ya,Ya,Ki,Ki,Hy` (小×2、槍×2、馬×2、兵×1)
- `-` (空)

### done_w / done_b

布陣段階で各プレイヤーが「配置完了」を宣言したかのフラグ。`0` または `1`。

### ply

開始からの累計手数 (整数)。

### diff

軍儀の難易度モード。`intro` / `beginner` / `intermediate` / `advanced` のいずれか。

## 特殊形 (startpos)

開始局面のショートカット。`decode_gfen()` は以下を特殊形として受理する:

| 形式 | 意味 |
|---|---|
| `startpos:intro` | 入門編の初期配置 |
| `startpos:beginner` | 初級編の初期配置 |
| `startpos:intermediate` | 中級編 (空盤、PLACEMENT 段階) |
| `startpos:advanced` | 上級編 (空盤、PLACEMENT 段階) |
| `startpos` | 難易度未指定。`setoption Difficulty` の pending 値を採用、無ければ `intro` |

## 例

### 開始局面 (入門編)

```
3|bCj|bSu|bTa|3/1|bSn|2|bYa|2|bSn|1/bHy|1|bTo|bSm|bHy|bSm|bTo|1|bHy/9/9/9/wHy|1|wTo|wSm|wHy|wSm|wTo|1|wHy/1|wSn|2|wYa|2|wSn|1/3|wTa|wSu|wCj|3 w pa Sh,Sh,Ya,Ya,Ki,Ki,Hy Sh,Sh,Ya,Ya,Ki,Ki,Hy - - 0 0 0 intro
```

### スタック例

中央 (4,4) に兵→侍が積まれた局面の board セクション:

```
9/9/9/9/4|wHy+wSm|4/9/9/9/9
```

### 詰将棋風の局面

中央 (4,5) に黒帥単独、(4,4) に白兵のみ:

```
9/9/9/4|bSu|4/4|wHy|4/9/9/9/9 w pa - - - - 0 0 0 intro
```

## 用途

- **UGI**: `position gfen <11 フィールド> [moves ...]` で任意局面を指定
- **棋譜ファイル**: 初期局面の保存 (`.gungi` の `[InitialGFEN ...]`、`.gsa` の `$INITIAL_GFEN:...`、`.json` の `initial_gfen` フィールド)
- **デバッグ**: 任意局面を 1 行で渡せるのでテストデータが書きやすい

## 関連仕様

- [UGI](UGI.md) — 通信プロトコル
- [GSA](GSA.md) — 棋譜フォーマット
