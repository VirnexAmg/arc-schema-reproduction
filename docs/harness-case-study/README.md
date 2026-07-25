# ls20 Harness 机制假设案例页

静态展示页：回答 harness 是否引导并保存了「十字 = 顺时针旋转 3×3」的正确机制假设。

## 打开方式

### 公开链接（GitHub Pages）

启用 Pages 后（见下方「首次启用」）：

- 案例页：https://virnexamg.github.io/arc-schema-reproduction/
- 若改为 Deploy from branch + `/docs`：https://virnexamg.github.io/arc-schema-reproduction/harness-case-study/

**首次启用（只需一次）**：打开
https://github.com/VirnexAmg/arc-schema-reproduction/settings/pages
→ Build and deployment → Source 选 **GitHub Actions** → Save。
然后到 Actions 里手动 Run workflow「Deploy harness case study to GitHub Pages」，或再 push 一次本目录。

## 本地打开方式


```bash
cd /home/chenhongyi/arc-schema-reproduction/docs/harness-case-study
python3 -m http.server 8765
```

浏览器访问：http://127.0.0.1:8765/

（需 HTTP 服务以加载 `case-data.json`；直接用 `file://` 打开通常会被浏览器拦截。）

## 文件

| 文件 | 说明 |
|------|------|
| `index.html` / `styles.css` / `app.js` | 案例页 |
| `case-data.json` | 从 `experiment-runs/` 只读解析出的证据（可再生成） |
| `assets/*.png` | 由本局观测 `frame_rle` 按 ARC 16 色调色板渲染的 ls20 首关画面 |

原始 `experiment-runs/` 未被修改。截图不是官方宣传图，而是实验日志里的真实帧。
