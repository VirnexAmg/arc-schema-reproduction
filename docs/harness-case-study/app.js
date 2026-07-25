/* ls20 harness case study — reads case-data.json only; no invented evidence. */

const GRADE_CLASS = {
  "说对了机制": "hit",
  "明确命中": "hit",
  "沾边，但没说对": "partial",
  "部分相关": "partial",
  "过了关，但机制说错": "wrong-pass",
  "行为上过关但机制说错": "wrong-pass",
  "与旋转机制无关": "irrelevant",
  "完全无关": "irrelevant",
};

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function conclusionOf(data) {
  return data.conclusion || data.verdict || {};
}

function btLabel(bt) {
  if (!bt) return "这一步之后没有紧接着做回测，或被下一轮修改打断了";
  if (bt.note) return bt.note;
  if (bt.passed === true) return `回测通过（核对了 ${bt.checked ?? "?"} 步历史）`;
  if (bt.passed === false) {
    const why = bt.reason ? `；原因：${bt.reason}` : "";
    return `回测未通过（在第 ${bt.mismatch_index ?? "?"} 步对不上，共核对 ${bt.checked ?? "?"}${esc(why)}）`;
  }
  return "回测结果未知";
}

function renderSwatch(hex, id) {
  const border = hex.toLowerCase() === "#ffffff" || hex.toLowerCase() === "#cccccc"
    ? "1px solid #c9c2b6"
    : "1px solid transparent";
  return `<span class="swatch" title="颜色 ${id}" style="background:${esc(hex)};border:${border}"></span>`;
}

function renderColorSection(legend) {
  if (!legend) return "";
  const palette = (legend.palette || [])
    .map(
      (c) => `
      <div class="color-chip">
        ${renderSwatch(c.hex, c.id)}
        <div class="color-chip-text">
          <strong>${c.id}</strong>
          <span>${esc(c.name)}</span>
        </div>
      </div>`
    )
    .join("");

  const roles = (legend.model_roles || [])
    .map((r) => {
      const swatches = (r.swatches || [])
        .map((id) => {
          const c = (legend.palette || []).find((x) => x.id === id);
          return c ? renderSwatch(c.hex, id) : "";
        })
        .join("");
      return `
      <div class="color-role">
        <div class="color-role-head">
          ${swatches}
          <strong>颜色 ${esc(r.ids)}</strong>
          <span>${esc(r.role)}</span>
        </div>
        <p>${esc(r.detail)}</p>
      </div>`;
    })
    .join("");

  return `
    <section>
      <h2>颜色编号是什么意思？</h2>
      <p class="section-lead">${esc(legend.intro)}</p>
      <h3 class="subhead">调色板（编号 → 外观）</h3>
      <div class="palette-grid">${palette}</div>
      <h3 class="subhead">这份 world_model.py 里的角色含义</h3>
      <div class="color-roles">${roles}</div>
      <p class="theory-note">${esc(legend.footnote || "")}</p>
    </section>`;
}

function renderTimeline(rounds) {
  return rounds
    .map((r) => {
      const gclass = GRADE_CLASS[r.grade] || "irrelevant";
      return `
      <article class="t-item ${gclass}">
        <div class="t-top">
          <span class="t-round">第 ${r.round} 轮 · 环境约第 ${r.env_step} 步 · 日志第 ${r.jsonl_line} 行</span>
          <span class="t-phase">${esc(r.phase)}</span>
          <span class="grade ${gclass}">${esc(r.grade)}</span>
        </div>
        <p class="t-hyp">${esc(r.hypothesis)}</p>
        <div class="t-meta">
          <div>代码怎么改：${esc(r.code_change)}</div>
          <div>回测情况：${btLabel(r.backtest)}</div>
          <div>为什么这样评：${esc(r.grade_reason)}</div>
        </div>
      </article>`;
    })
    .join("");
}

function renderHits(hits, emptyMsg) {
  if (!hits || !hits.length) return `<p class="section-lead">${esc(emptyMsg)}</p>`;
  return `<div class="hit-list">${hits
    .map(
      (h) => `
    <div class="hit">
      <span class="tag">${esc(h.match)}</span>
      <span>日志第 ${h.jsonl_line} 行 · ${esc(h.source)}</span>
      <pre class="code">${esc(h.snippet)}</pre>
    </div>`
    )
    .join("")}</div>`;
}

function wmScanRows(scan) {
  const interesting = Object.entries(scan || {}).filter(([, v]) => v.count > 0);
  if (!interesting.length) {
    return "<p>终态 world_model.py 里没有出现与旋转、十字相关的词。</p>";
  }
  return `<ul>${interesting
    .map(([k, v]) => {
      const sample = v.samples?.[0] ? `<pre class="code">${esc(v.samples[0])}</pre>` : "";
      return `<li><strong>${esc(k)}</strong> 出现 ${v.count} 次${sample}</li>`;
    })
    .join("")}</ul>`;
}

function figureById(figures, id) {
  return (figures || []).find((f) => f.id === id);
}

function renderFigure(fig, extraClass = "") {
  if (!fig) return "";
  return `
    <figure class="shot ${extraClass}">
      <img src="${esc(fig.src)}" alt="${esc(fig.caption)}" loading="lazy" />
      <figcaption>${esc(fig.caption)}</figcaption>
    </figure>`;
}

function renderFigureRow(figures, ids) {
  const items = ids.map((id) => figureById(figures, id)).filter(Boolean);
  if (!items.length) return "";
  return `<div class="shot-row">${items.map((f) => renderFigure(f)).join("")}</div>`;
}

function renderVisionSection(data) {
  const v = data.vision_analysis;
  if (!v) return "";
  const figures = data.figures || [];
  return `
    <section>
      <h2>${esc(v.title)}</h2>
      <p class="section-lead"><strong>${esc(v.short_answer)}</strong> ${esc(v.one_liner)}</p>

      <div class="vision-grid">
        <div class="panel">
          <h3>这局实际怎么看世界</h3>
          <ul>
            <li><code>vision_enabled = ${esc(String(v.config.vision_enabled))}</code></li>
            <li><code>render_mode = ${esc(String(v.config.render_mode))}</code></li>
            <li>${esc(v.config.observation)}</li>
          </ul>
          <p class="theory-note">依据：${esc(v.config.source)}</p>
          <pre class="code">模型看到的是这种文本，而不是上面的图：
"5:4,4:28,3:1,5:2,9:1,5:1,9:1,5:2,3:1,4:23"
"5:4,4:10,3:7,0:1,3:7,4:5,3:20,4:10"</pre>
        </div>
        <div class="panel">
          <h3>为什么和没开视觉相关</h3>
          <ul>${v.why_related.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>
        </div>
      </div>

      ${renderFigureRow(figures, ["l1-cross", "l1-inventory", "l1-target"])}

      <div class="panel" style="margin-top:1rem">
        <h3>但也不只是视觉的问题</h3>
        <ul>${v.not_only_reason.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>
      </div>

      ${renderFigure(figureById(figures, "l1-clear"))}
    </section>`;
}

function renderPhase(data, key) {
  const p = data[key];
  const search = data.search_summary[key];
  const edits = data[`${key}_edits_key`] || [];
  const snippets = p.wm_snippets || {};
  const conclusion = conclusionOf(data);

  const theory = p.model_theory;
  const theoryHtml = theory
    ? `
          <p class="quote">${esc(theory.headline)}</p>
          <p class="theory-source">依据：<code>${esc(theory.source)}</code>（不是 notes.md）</p>
          <ul class="theory-list">
            ${theory.bullets
              .map(
                (b) => `
              <li>
                <strong>${esc(b.label)}</strong> — ${esc(b.text)}
                ${b.quote ? `<pre class="code">${esc(b.quote)}</pre>` : ""}
              </li>`
              )
              .join("")}
          </ul>
          <p class="theory-note">${esc(theory.notes_note || "")}</p>`
    : `
          <p class="quote">见终态 world_model.py。</p>
          <ul>
            <li>notes.md：${p.notes_is_empty_template ? "几乎是空模板" : "有内容"}</li>
          </ul>`;

  const levelStep = p.level_changes[0]?.env_step ?? "—";

  const figures = data.figures || [];

  return `
    <section>
      <h2>真实机制，和模型实际写下的理解</h2>
      <p class="section-lead">${esc(
        data.model_theory_source_note ||
          "左边是真实机制；右边摘自本局终态 world_model.py。"
      )}</p>

      ${renderFigure(figureById(figures, "l1-start"), "shot-hero")}
      <p class="section-lead" style="margin-top:0.75rem">
        上图由本局第一关开局观测帧渲染。人眼容易看到白色十字、左下蓝色图示和上方目标图案；
        而这局模型只收到 RLE 文本，没有这类截图。
      </p>

      <div class="compare">
        <div class="panel truth">
          <h3>真实机制</h3>
          <p class="quote">${esc(data.true_mechanism.summary)}</p>
          <ul>${data.true_mechanism.key_terms.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>
        </div>
        <div class="panel model">
          <h3>模型写在 world_model.py 里的理解</h3>
          ${theoryHtml}
        </div>
      </div>
      <div class="answers">
        ${(conclusion.answers || [])
          .map(
            (a) => `
          <div class="answer">
            <strong>${esc(a.q)}</strong>
            <span>${esc(a.a)}</span>
          </div>`
          )
          .join("")}
      </div>
    </section>

    ${renderVisionSection(data)}

    ${renderColorSection(data.color_legend)}

    <section>
      <h2>假设是怎么一步步改过来的</h2>
      <p class="section-lead">
        实验编号 ${esc(p.run_id)}，模型 ${esc(p.model)}。
        环境走了 ${p.env_transitions} 步，改代码 ${p.code_edits} 次，
        回测通过 ${p.backtests.passed}/${p.backtests.total} 次；
        大约在第 ${levelStep} 步升到第 1 关。
        这里看的是「有没有碰到十字等于旋转」，不是「过关够不够快」。
      </p>
      <div class="timeline">${renderTimeline(p.hypothesis_rounds)}</div>
    </section>

    <section class="evidence">
      <h2>可核对的原始证据</h2>
      <p class="section-lead">都能追溯到日志行号或 workspace 文件。原始 experiment-runs 没有改动。</p>

      <details open>
        <summary>和「旋转 / 十字 / 3×3」有关的检索</summary>
        <div class="body">
          <p>在模型回复和工具参数里检索：<code>rotate|rotation|clockwise|3x3|cross|十字|顺时针</code>（已去掉 across 这类误报）。</p>
          <p><strong>命中情况：</strong> ${
            Object.keys(search.strict_mech_in_jsonl || {}).length
              ? Object.entries(search.strict_mech_in_jsonl)
                  .map(([k, v]) => `<code>${esc(k)}</code> ${v} 次`)
                  .join(" · ")
              : "没有命中"
          }</p>
          ${renderHits(
            p.mech_hits_dedup,
            "这局日志里没有严格命中旋转、十字一类表述；若有，也已在时间线里说明是容易误会的用法。"
          )}
          <p style="margin-top:1rem"><strong>终态 world_model.py 里的相关词：</strong></p>
          ${wmScanRows(p.final_wm_keyword_scan)}
        </div>
      </details>

      <details>
        <summary>notes.md 最终内容（有没有写下旋转假设）</summary>
        <div class="body">
          <p>路径：<code>${esc(p.path)}/workspace-harness-0/notes.md</code></p>
          <pre class="code">${esc(p.notes_md_final)}</pre>
        </div>
      </details>

      <details>
        <summary>过关条件：是机制说对了，还是记成了捷径？</summary>
        <div class="body">
          ${
            snippets.level_clear_shortcut
              ? `<p>Phase1：用坐标记下「过第一关」：</p><pre class="code">${esc(snippets.level_clear_shortcut)}</pre>`
              : ""
          }
          ${
            snippets.shrine_complete
              ? `<p>Phase2：写成走进图案房间就过关：</p><pre class="code">${esc(snippets.shrine_complete)}</pre>`
              : ""
          }
          ${
            snippets.is_goal
              ? `<p><code>is_goal</code>：</p><pre class="code">${esc(snippets.is_goal)}</pre>`
              : "<p>终态的 is_goal 主要看是否 WIN，或 levels_completed 是否增加，而不是「旋转后是否对齐」。 </p>"
          }
          ${
            snippets["3x3_glyph"]
              ? `<p>唯一出现的「3x3」注释（指小图案外形，不是旋转）：</p><pre class="code">${esc(snippets["3x3_glyph"])}</pre>`
              : ""
          }
          ${
            snippets.rotate_status
              ? `<p>「rotate」出现在状态栏重排里，不是 3×3 顺时针旋转：</p><pre class="code">${esc(snippets.rotate_status)}</pre>`
              : ""
          }
        </div>
      </details>

      <details>
        <summary>关键代码修改原文（可对照上面的轮次）</summary>
        <div class="body">
          ${edits
            .map(
              (e) => `
            <div class="hit">
              <strong>日志第 ${e.jsonl_line} 行</strong> · ${esc(e.tool)} · 环境约第 ${e.env_step} 步
              <pre class="code">${esc(e.new_preview || "")}</pre>
            </div>`
            )
            .join("") || "<p>没有摘录。</p>"}
        </div>
      </details>

      <details>
        <summary>本局成绩（仅作背景，不是主线）</summary>
        <div class="body">
          <div class="stats-inline">
            <span>harness 完成关卡 ${p.harness.levels_completed}</span>
            <span>得分 ${Number(p.harness.score).toFixed(3)}</span>
            <span>结束状态 ${esc(p.harness.status)}</span>
            <span>环境动作 ${p.harness.environment_actions}</span>
            <span>探索 / 计划 ${p.harness.exploration_actions} / ${p.harness.planned_actions}</span>
            <span>baseline 完成关卡 ${p.baseline.levels_completed}</span>
          </div>
          <p style="margin-top:0.75rem;color:var(--muted)">过关只说明碰巧走到了正确状态；本页要回答的是：保存下来的理论有没有说对机制。</p>
        </div>
      </details>
    </section>
  `;
}

function render(data) {
  const active = data.primary_case || "phase2";
  const ds = data.deepseek;
  const conclusion = conclusionOf(data);

  document.getElementById("app").innerHTML = `
    <header class="site-header">
      <div class="wrap">
        <p class="eyebrow">Schema-like harness · ls20 案例拆解</p>
        <h1>${esc(data.title)}</h1>
        <p class="lede">
          这不是「谁过关更快」的对比页。我们想看清一件事：
          harness 有没有引导模型形成并保存正确机制——
          「十字表示把左下角 3×3 顺时针转 90°；转完与目标一致后，再走到对应位置通关」。
          notes.md 几乎是空的，所以主要依据终态 <code>world_model.py</code> 的注释和逻辑。
        </p>
        <div class="verdict ${esc(conclusion.color || "red")}">
          <div class="verdict-label">结论：${esc(conclusion.label || "没有")}</div>
          <p>${esc(conclusion.one_liner || "")}</p>
        </div>
        <div class="meta-row">
          <span>重点看：<strong>Phase2 的 world_model</strong> <code>${esc(data.phase2.run_id)}</code></span>
          <span>补充：<strong>Phase1</strong> <code>${esc(data.phase1.run_id)}</code></span>
          <span>对照：DeepSeek D2（0 关）</span>
        </div>
        <div class="phase-switch" role="tablist" aria-label="选择实验阶段">
          <button type="button" data-phase="phase2" aria-pressed="${active === "phase2" ? "true" : "false"}">Phase2 · 看 world_model</button>
          <button type="button" data-phase="phase1" aria-pressed="${active === "phase1" ? "true" : "false"}">Phase1 · 更短的故事</button>
        </div>
      </div>
    </header>

    <main class="wrap">
      <div id="phase-root">${renderPhase(data, active)}</div>

      <section class="footnote">
        <h2>对照：DeepSeek D2</h2>
        <p>
          实验 <code>${esc(ds.run_id)}</code>：一关都没过，
          回测 ${ds.backtests.passed}/${ds.backtests.total} 次通过，
          写 notes ${ds.notes_writes} 次，改代码也很勤——
          工具环在转，但没有形成能过关的有效理论。
        </p>
        <p>
          它在 notes 里用过 rotate，但说的是「色块堆上下循环移位、去匹配某个图案」，
          不是「十字把左下角 3×3 顺时针转 90°」。最终的 world_model 也没有落到真实机制上。
        </p>
        ${renderHits(ds.rotate_note_samples, "没有可供展示的 rotate 摘录。")}
      </section>
    </main>

    <footer class="site-footer">
      <div class="wrap">
        数据只读自 <code>experiment-runs/</code>；展示用文件在 <code>docs/harness-case-study/</code>。
        本地查看：在本目录运行 <code>python3 -m http.server 8765</code>，打开
        <code>http://127.0.0.1:8765/</code>。
      </div>
    </footer>
  `;

  const root = document.getElementById("phase-root");
  document.querySelectorAll(".phase-switch button").forEach((btn) => {
    btn.addEventListener("click", () => {
      const phase = btn.dataset.phase;
      document.querySelectorAll(".phase-switch button").forEach((b) => {
        b.setAttribute("aria-pressed", b === btn ? "true" : "false");
      });
      root.innerHTML = renderPhase(data, phase);
    });
  });
}

async function main() {
  try {
    const res = await fetch("./case-data.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    render(data);
  } catch (err) {
    document.getElementById("app").innerHTML = `
      <div class="wrap err">
        <strong>加载不了 case-data.json</strong>
        <p>浏览器通常不允许直接用 <code>file://</code> 读本地 JSON。请到目录
        <code>docs/harness-case-study/</code> 运行：</p>
        <pre class="code">python3 -m http.server 8765</pre>
        <p>然后打开 <code>http://127.0.0.1:8765/</code></p>
        <p style="color:var(--muted)">报错信息：${esc(err.message)}</p>
      </div>`;
  }
}

main();
