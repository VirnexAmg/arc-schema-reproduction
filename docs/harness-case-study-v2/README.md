# ls20 Harness 案例展示页（v2）

## 打开

推荐从仓库根目录启动静态服务：

```powershell
python -m http.server 8000
```

然后访问：

```text
http://localhost:8000/docs/harness-case-study-v2/
```

页面数据通过 `case-data.js` 同步加载，因此直接双击 `index.html` 也能阅读；但推荐使用本地服务，以便证据区链接可以正常打开仓库里的原始日志。

## 重新生成衍生数据

```powershell
.venv\Scripts\python.exe docs\harness-case-study-v2\scripts\extract_case_data.py
```

脚本只读以下三个运行目录，不修改原始日志：

- `experiment-runs/20260722T100318.351779Z/`
- `experiment-runs/20260722T110925.665615Z/`
- `experiment-runs/20260724T094149.364803Z/`

输出仅写入当前展示目录：

- `case-data.json`：便于人工审阅的格式化数据
- `case-data.js`：供静态页面直接加载的数据

叙事时间线把 Phase 1 的 36 次代码修改归并成 6 个阅读回合；原始修改、工具序列与 40 次回测仍完整保留在衍生数据中。
