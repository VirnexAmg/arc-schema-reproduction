(function () {
  "use strict";

  const dataset = window.LS20_CASE_DATA;
  if (!dataset || !dataset.cases) {
    document.body.innerHTML =
      "<main style='padding:3rem;font-family:serif'>衍生数据未加载。请先运行 scripts/extract_case_data.py。</main>";
    return;
  }

  const stories = {
    phase1: [
      {
        range: "环境步 1–4",
        title: "先把画面变化抄下来",
        rating: "无关机制",
        summary:
          "ACTION1、ACTION2 被轮流试探。第一版没有对象概念，只把变化过的像素行硬编码进 step()；一次回测失败后，模型修正了 frame 字段与进度条累积。",
        hypothesis:
          "“动作会移动一个五格宽物体，同时底部进度条向前一格。”",
        actions: "↑ · ↓ · ↑ · ←（最后一步被墙挡住）",
        edit: 5,
        backtest: "v2 失败 → v3 通过；随后完整重写为 v6，并通过 4 条历史转移",
      },
      {
        range: "环境步 5–12",
        title: "回测把“像素录像”推成迷宫模型",
        rating: "行为捷径",
        summary:
          "BFS 按 5×5 玩家、墙与四向移动规划，先走到十字所在格。此处最关键的命名发生偏航：模型没有提出旋转，而是把这个 0/1 图标称作 collectible，并把左下图形称作 inventory。",
        hypothesis:
          "“0/1 小图标是可拾取物；进入格子会改变下方 inventory 图标，而且该回合不消耗倒计时。”",
        actions: "↑ ↑ ↑ ← ← ↓ ←，到达 (19,30)",
        edit: 6,
        backtest: "v7 失败：预测状态与历史观察不同；补上图标会在玩家离开后重现，v8 通过",
      },
      {
        range: "环境步 13–18",
        title: "先捡“钥匙”，再沿走廊进上方房间",
        rating: "行为过关，但机制说错",
        summary:
          "模型撤回了“碰到图标即通关”，改称它只是 collectible，真正出口在上方 framed symbol。第 18 步从 (34,15) 执行 ACTION1 后，环境真的把 levels 从 0 改成 1。",
        hypothesis:
          "“拾取 0/1 图标后，剩余目标是大框符号下方的 terminal corridor。”",
        actions: "右移三格，再连续上移三格",
        edit: 11,
        backtest: "v12 通过 16 条历史转移；但‘为什么解锁’仍未被解释",
        levelUp: true,
      },
      {
        range: "环境步 19",
        title: "看到升关后，代码记住了触发坐标",
        rating: "坐标记忆",
        summary:
          "升关带来整张新地图，最初的 exit-frame 泛化连续失败。最终模拟器直接记录：第一关、玩家在 (34,15)、再执行 ACTION1，就装载第二关。",
        hypothesis:
          "“进入上方 chamber 会完成第一关；用已观察到的位置与动作复现这次切图。”",
        actions: "观察第二关首帧，反复修补 _load_second_level()",
        edit: 16,
        backtest: "连续 5 次失败后修正地图与倒计时；v18–v22 恢复通过",
      },
      {
        range: "环境步 20–32",
        title: "第二关继续沿“钥匙—房间”解释扩展",
        rating: "替代机制",
        summary:
          "模型在新地图里把 0/1 图标、color-11 房间、进度条分别解释为钥匙、出口或补给，并多次改写 is_goal()。这些规则能解释部分转移，但没有反推第一关的旋转因果。",
        hypothesis:
          "“lower-right 的 0/1 glyph 是钥匙；某个 11-colored chamber 是出口或 timer reset。”",
        actions: "BFS 在若干候选房间之间试走",
        edit: 22,
        backtest: "候选目标多次替换；历史回测可以通过，真实环境却没有继续升关",
      },
      {
        range: "环境步 33–80",
        title: "坐标目标被证伪，最终只保留“见到升关才算”",
        rating: "诚实收缩，但未命中",
        summary:
          "先后尝试 lower-right 0/1、lower 11、(14,15) 房间；走到坐标仍未通关后，模型终于承认“坐标本身不足”。最终 world_model 保留第一关的硬编码升关、第二关的钥匙/补给/房间与超时重置。",
        hypothesis:
          "“只有环境真的增加 levels_completed 或进入 WIN，才能证明目标成立。”",
        actions: "探索第二关直到 80 步预算用尽",
        edit: 35,
        backtest: "v36 与最终 v37 均通过已见历史；第一关旋转机制仍为 0 次命中",
      },
    ],
    phase2: [
      {
        range: "环境步 1–3",
        title: "更快得到 5×5 迷宫移动模型",
        rating: "行为捷径",
        summary:
          "第二次运行很快从像素转移归纳出 5×5 玩家与四向移动，并把十字所在格叫作 target glyph。这里的“target”只表示要走进去的格子，没有任何旋转或图形匹配含义。",
        hypothesis:
          "“0/1 小图形所在的 5×5 格可进入；玩家覆盖它就算达到目标。”",
        actions: "↑ · ↓ · ←",
        edit: 5,
        backtest: "v6 通过 3 条历史转移",
      },
      {
        range: "环境步 4–11",
        title: "图标被重新解释为钥匙",
        rating: "替代机制",
        summary:
          "模型发现进入图标后状态栏变化，于是把它从 goal 改成 key，并认为钥匙让上方 5/9 patterned shrine 变得可进入。",
        hypothesis:
          "“collect lower 0/1 key → unlock top shrine。”",
        actions: "向左、向上到 (19,30)，再返回主走廊",
        edit: 21,
        backtest: "v22–v24 通过；BFS 开始规划前往上方 shrine",
      },
      {
        range: "环境步 12–17",
        title: "行为先过关，因果解释随后补写",
        rating: "行为过关，但机制说错",
        summary:
          "第 17 步是 planned ACTION1：玩家从 (34,15) 进入上方区域，levels 变成 1。观察到切图后，模型补写“进入 unlocked patterned shrine completes the level”。",
        hypothesis:
          "“钥匙解锁 patterned shrine；进入 shrine 就升关。”",
        actions: "→ → → ↑ ↑ ↑",
        edit: 25,
        backtest: "初次补写切图失败，修正两版后 v27 通过",
        levelUp: true,
      },
      {
        range: "环境步 18–84",
        title: "长预算换来更复杂的“钥匙—补给—出口”系统",
        rating: "替代机制扩张",
        summary:
          "模拟器开始区分 color-11 补给、5/9 patterned chamber、board-local 0/1 key、倒计时和生命。候选出口不断在颜色、坐标与前置条件之间切换。",
        hypothesis:
          "“每张地图有本地钥匙；patterned chamber 是出口；11 glyph 是预算补给。”",
        actions: "在第二关多房间之间进行 BFS 与探索",
        edit: 46,
        backtest: "多轮失败—修补—通过；仍没有产生十字旋转假设",
      },
      {
        range: "环境步 85–103",
        title: "出现了 rotate，但旋转的是状态栏",
        rating: "关键词假阳性",
        summary:
          "日志里唯一接近题意的词是 rotates / rotate。上下文明确写的是“钥匙让三组 paired status bands 轮换”，对象是底部 UI，不是左下 3×3 图形；也没有 clockwise、90° 或目标匹配。",
        hypothesis:
          "“Entering the 0/1 key rotates the three paired status bands。”",
        actions: "从不同方向重复进入图标，拟合状态栏变化",
        edit: 59,
        backtest: "v60 失败；持续修到 v62 才通过该段历史",
      },
      {
        range: "环境步 104–149",
        title: "最终模型更精细，核心解释仍未改变",
        rating: "未命中旋转机制",
        summary:
          "最终版本用图标消失与状态位判断 key possession，以固定 patterned chamber 和坐标判断出口，并模拟超时重置。149 次动作结束时仍只有 1 关。",
        hypothesis:
          "“钥匙拥有状态独立于装饰图标；进入固定 patterned chamber 才算下一目标。”",
        actions: "持续探索至 game over",
        edit: 147,
        backtest: "最终 75 / 174 次回测通过；99 次失败推动大量局部修补",
      },
    ],
  };

  const keywordOrder = [
    "cross",
    "rotate",
    "clockwise_90",
    "three_by_three",
    "match_target",
    "coordinate",
    "key",
    "chamber",
    "levels",
  ];

  const keywordNotes = {
    cross: () => "核心符号没有被命名为十字；这是最直接的缺口。",
    rotate: (phase, finalCount) =>
      phase === "phase2" && finalCount
        ? "有命中，但上下文是 status bands 轮换，不是 3×3 图形旋转。"
        : "没有提出旋转操作。",
    clockwise_90: () => "严格方向与角度均未出现。",
    three_by_three: (phase, finalCount) =>
      phase === "phase1" && finalCount
        ? "唯一一次只说“3x3 glyph 被玩家覆盖”，没有旋转含义。"
        : "没有把左下图形识别为待变换的 3×3。",
    match_target: () => "没有建立“变换结果 = 目标图形”的比较。",
    coordinate: () => "大量出现，说明模拟器依赖位置与固定触发条件。",
    key: () => "核心替代词：0/1 glyph 被解释为 key / collectible。",
    chamber: () => "核心替代词：上方目标区被解释为 chamber / shrine。",
    levels: () => "最终以环境计数器作为唯一可靠的通关证据。",
  };

  const evidenceQuotes = {
    phase1: [
      {
        where: "jsonl 第 90 行 · apply_patch · 环境步 12",
        label: "十字被改写成 collectible",
        text:
          "# The small 0/1 glyph is a collectible.\n# Entering its tile consumes it, changes the matching\n# inventory glyph below the maze.",
      },
      {
        where: "jsonl 第 183 行 · apply_patch · 环境步 19",
        label: "第一关升关被记成坐标条件",
        text:
          "if state.levels_completed == 0 \\\n   and old_pos == (34, 15) and aid == 1:\n    _load_second_level(nxt)",
      },
      {
        where: "world_model.py 第 265–276 行",
        label: "最终目标仍是房间、图标与坐标",
        text:
          "# entering the chamber containing the 11-colored glyph...\n# The remaining matching chamber is at (14,15)\n# A coordinate alone is not sufficient...",
      },
    ],
    phase2: [
      {
        where: "jsonl 第 181 行 · apply_patch · 环境步 11",
        label: "钥匙—房间假设",
        text:
          "# After collecting the lower 0/1 key, the color-5/9\n# shrine at the top of the maze becomes traversable.",
      },
      {
        where: "jsonl 第 763 行 · apply_patch · 环境步 85",
        label: "rotate 的实际上下文",
        text:
          "# Entering the 0/1 key rotates the three paired status bands\n# into the observed collected-key pattern.",
      },
      {
        where: "world_model.py 第 309–327 行",
        label: "最终出口仍是固定 patterned chamber",
        text:
          "# Each maze's exit is its distinctive 5/9 patterned chamber.\n# In level 2 this is the chamber at (top=40, left=14)...",
      },
    ],
  };

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatMoney(value) {
    return `$${Number(value).toFixed(2)}`;
  }

  function clipCode(value, limit = 780) {
    const text = String(value || "").trim();
    if (!text) return "";
    if (text.length <= limit) return text;
    return `${text.slice(0, limit).trimEnd()}\n…`;
  }

  function nextBacktest(caseData, edit) {
    return caseData.backtests.find((item) => item.sequence > edit.sequence);
  }

  function renderTimeline(phase) {
    const caseData = dataset.cases[phase];
    const rounds = stories[phase];
    const levelChange = caseData.level_changes[0];

    $("#timeline-title").textContent = `从第一次试探，到第 ${levelChange.step} 步升关`;
    $("#timeline-lead").textContent =
      phase === "phase1"
        ? "Phase 1 是主案例。下面把 36 次代码修改归并为 6 个认知回合：每一轮都保留动作、假设、关键改动与回测结果。"
        : "Phase 2 给了更长预算。它更早行为过关，也产生了更多局部修补；这让“rotate 假阳性”更值得单独核验。";

    $("#ledger-edits").textContent = caseData.edits.length;
    $("#ledger-backtests").textContent = caseData.backtest_summary.total;
    $("#ledger-pass-rate").textContent =
      `${caseData.backtest_summary.passed} / ${caseData.backtest_summary.failed}`;

    $("#timeline-entries").innerHTML = rounds
      .map((round, index) => {
        const edit = caseData.edits[round.edit - 1];
        const backtest = nextBacktest(caseData, edit);
        const oldCode =
          clipCode(edit.old) || "(write_code：本轮完整重写；前版按动作硬编码像素变化)";
        const newCode = clipCode(edit.new);
        const lineLabel = `jsonl 第 ${edit.line} 行 · ${edit.tool} · v${edit.version ?? "?"}`;
        const backtestClass =
          backtest && !backtest.passed ? "backtest-line is-fail" : "backtest-line";
        const levelHtml = round.levelUp
          ? `<div class="level-event">
              <strong>0 → 1</strong>
              <p>环境第 ${levelChange.step} 步 · ACTION${levelChange.action} ·
              ${escapeHtml(levelChange.kind)} · 玩家 ${escapeHtml(
                levelChange.player_before.join(",")
              )} → 新关卡首帧</p>
            </div>`
          : "";

        return `<article class="timeline-entry ${round.levelUp ? "is-level-up" : ""}">
          <div class="round-number">${String(index + 1).padStart(2, "0")}</div>
          <div class="round-body">
            <p class="round-meta">
              <span>${escapeHtml(round.range)}</span>
              <span class="round-rating">评级 · ${escapeHtml(round.rating)}</span>
            </p>
            <h3>${escapeHtml(round.title)}</h3>
            <p class="round-summary">${escapeHtml(round.summary)}</p>
            <div class="hypothesis-note">
              <span>本轮假设</span>
              <p>${escapeHtml(round.hypothesis)}</p>
            </div>
            <p class="action-path"><b>动作：</b><code>${escapeHtml(round.actions)}</code></p>
            <div class="diff-block">
              <div class="diff-head">
                <span>world_model.py</span>
                <b>${escapeHtml(lineLabel)}</b>
              </div>
              <div class="diff-grid">
                <div class="diff-pane diff-old">
                  <label>OLD / BEFORE</label>
                  <pre>${escapeHtml(oldCode)}</pre>
                </div>
                <div class="diff-pane diff-new">
                  <label>NEW / AFTER</label>
                  <pre>${escapeHtml(newCode)}</pre>
                </div>
              </div>
              <p class="${backtestClass}">
                <b>run_backtest</b>
                <span>${escapeHtml(round.backtest)}</span>
              </p>
            </div>
            ${levelHtml}
          </div>
        </article>`;
      })
      .join("");
  }

  function renderKeywords(phase) {
    const caseData = dataset.cases[phase];
    const finalScan = caseData.keyword_scan.final_world_model;
    const editsScan = caseData.keyword_scan.all_code_edits;

    $("#evidence-phase-label").textContent = phase === "phase1" ? "P1" : "P2";
    $("#keyword-ruling").innerHTML =
      phase === "phase1"
        ? `<strong>严格机制词：0 命中</strong>
           <p>十字、旋转、顺时针 / 90°、目标匹配全部缺席。唯一的 “3x3” 只是尺寸描述：
           <code>its 3x3 glyph is covered from tile position (44,45)</code>，并非旋转假设。</p>`
        : `<strong>rotate：假阳性</strong>
           <p>最终模拟器里出现 1 次 rotate，全部代码修改里出现 3 次。上下文都是
           <code>paired status bands</code> 的状态轮换；cross、clockwise / 90°、3×3、目标匹配仍为 0。</p>`;

    $("#keyword-table-body").innerHTML = keywordOrder
      .map((key) => {
        const finalCount = finalScan[key].count;
        const editCount = editsScan[key].count;
        const finalClass = finalCount ? "count-hit" : "count-zero";
        const editClass = editCount ? "count-hit" : "count-zero";
        return `<tr>
          <td>${escapeHtml(finalScan[key].label)}</td>
          <td><span class="${finalClass}">${finalCount}</span></td>
          <td><span class="${editClass}">${editCount}</span></td>
          <td class="review-note">${escapeHtml(
            keywordNotes[key](phase, finalCount, editCount)
          )}</td>
        </tr>`;
      })
      .join("");
  }

  function renderEvidence(phase) {
    const caseData = dataset.cases[phase];
    $("#key-code-evidence").innerHTML = `<dl>${evidenceQuotes[phase]
      .map(
        (quote) => `<div class="evidence-quote">
          <dt>${escapeHtml(quote.where)}<br /><b>${escapeHtml(quote.label)}</b></dt>
          <dd><pre><code>${escapeHtml(quote.text)}</code></pre></dd>
        </div>`
      )
      .join("")}</dl>`;

    const sources = caseData.sources;
    const sourceLabels = [
      ["jsonl", "harness-run-0.jsonl", "完整工具、动作与环境事件"],
      ["world_model", "world_model.py", "运行结束时保存的模拟器"],
      ["notes", "notes.md", "运行结束时保存的笔记"],
      ["experiment", "experiment.json", "配置、成本与结果摘要"],
    ];
    $("#source-links").innerHTML = sourceLabels
      .map(([key, label, note]) => {
        const href = `../../${sources[key].replaceAll("\\", "/")}`;
        return `<a href="${escapeHtml(href)}">
          <b>${escapeHtml(label)}</b>
          <small>${escapeHtml(note)}</small>
        </a>`;
      })
      .join("");
  }

  function renderContext() {
    const p1 = dataset.cases.phase1;
    const p2 = dataset.cases.phase2;
    const ds = dataset.cases.deepseek;
    $("#phase1-context").textContent =
      `第 ${p1.level_changes[0].step} 步过 L1；Harness ${formatMoney(
        p1.harness.estimated_cost_usd
      )}，baseline ${formatMoney(p1.baseline.estimated_cost_usd)}`;
    $("#phase2-context").textContent =
      `第 ${p2.level_changes[0].step} 步过 L1；${p2.edits.length} 次代码修改，${p2.backtest_summary.failed} 次回测失败`;
    $("#deepseek-context").textContent =
      `双方 0 关；Harness ${ds.backtest_summary.passed} / ${ds.backtest_summary.total} 次回测通过`;
  }

  function selectPhase(phase) {
    const caseData = dataset.cases[phase];
    $$(".phase-button").forEach((button) => {
      const active = button.dataset.phase === phase;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });

    $("#cover-run-id").textContent = caseData.run_id;
    $("#cover-proof").textContent =
      `${caseData.label} · 第 ${caseData.level_changes[0].step} 步 levels 0→1 · ` +
      `${caseData.edits.length} 次代码修改 · ` +
      `${caseData.backtest_summary.total} 次回测`;

    renderTimeline(phase);
    renderKeywords(phase);
    renderEvidence(phase);
  }

  $$(".phase-button").forEach((button) => {
    button.addEventListener("click", () => selectPhase(button.dataset.phase));
  });

  function updateProgress() {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const ratio = max > 0 ? window.scrollY / max : 0;
    $("#reading-progress-bar").style.width = `${Math.min(1, ratio) * 100}%`;
  }

  window.addEventListener("scroll", updateProgress, { passive: true });
  window.addEventListener("resize", updateProgress);

  renderContext();
  selectPhase("phase1");
  updateProgress();
})();
