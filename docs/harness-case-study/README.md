# ls20 Harness 机制假设案例页（最终版）

静态展示页：回答 harness 是否引导并保存了「十字 = 顺时针旋转 3×3」的正确机制假设。

## 版本

| 目录 | 说明 |
|------|------|
| `docs/harness-case-study/` | **最终版**（当前公开站点） |
| `docs/harness-case-study-v1-draft/` | **旧版排版备份**（保留，不删除） |

## 公开链接

https://virnexamg.github.io/arc-schema-reproduction/

由 `gh-pages` 分支托管本目录内容。

## 本地打开

```bash
cd /home/chenhongyi/arc-schema-reproduction/docs/harness-case-study
python3 -m http.server 8765
```

浏览器：http://127.0.0.1:8765/

旧版备份预览：

```bash
cd /home/chenhongyi/arc-schema-reproduction/docs/harness-case-study-v1-draft
python3 -m http.server 8766
```

## 文件

| 文件 | 说明 |
|------|------|
| `index.html` / `styles.css` / `app.js` | 案例页 |
| `case-data.json` | 从 `experiment-runs/` 只读解析出的证据 |
| `assets/*.png` | 由本局观测 `frame_rle` 渲染的画面 |

原始 `experiment-runs/` 未被修改。
