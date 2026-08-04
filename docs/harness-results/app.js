(function () {
  "use strict";

  const thoughtStages = {
    movement: {
      step: "阶段 1 · evidence 1–4 · Level 1",
      title: "确认四个动作的方向映射",
      image: "assets/l1-start.png",
      alt: "ls20 第一关初始画面",
      caption: "L1 初始画面。紫红 5×5 tile 位于主走廊下方，底部青色条记录动作资源。",
      observation:
        "四次试探显示，同一个紫红 5×5 物体分别发生整块的上、下、左、右平移；普通动作同时消耗底部计时条。",
      hypothesis:
        "ACTION1/2/3/4 分别对应上/下/左/右，每次移动一个 5×5 tile 宽度；绿色是主要可通行区域。",
      action:
        "依次测试四个动作，并把每次 before/after transition 写入世界模型；回放已见转移，检查是否能逐像素复现。",
      result:
        "四向控制假说得到支持。后续世界模型和导航使用该映射，不再重复估计基础动作语义。",
      status: "supported",
      statusLabel: "supported",
      evidence: "最终账本：H_action4_right、H_actor_motion；Full run 早期 evidence 1–4。",
    },
    switch: {
      step: "阶段 2 · evidence 5–19 · L1 → L2",
      title: "修订黑蓝 motif 的对象语义",
      image: "assets/l2-start.png",
      alt: "第一关完成后出现的第二关入口画面",
      caption: "env step 19：L1 已完成，环境切换到 L2。这个边界来自真实环境，不由世界模型伪造。",
      observation:
        "tile 进入黑蓝 motif 后，motif 被暂时覆盖，左下 display 改变；tile 离开后 motif 重新出现。目标框只在图形关系满足时允许完成。",
      hypothesis:
        "黑蓝 0/1 motif 不是墙，而是持久地面开关；重叠会同步或变换左下图形，离开后恢复底图。",
      action:
        "沿已认证走廊进入开关，再走向灰框目标；每个 navigation 动作都先用当前 WM 预测，再与真实画面对比。",
      result:
        "原先的 solid obstacle 假说被拒，H_glyph_gate 得到支持；L1 在环境动作 19、调用 8 完成。",
      status: "supported",
      statusLabel: "revised → supported",
      evidence: "H_motif_block = rejected；H_glyph_gate = supported，evidence 1–18；level checkpoint env 19。",
    },
    level2: {
      step: "阶段 3 · evidence 36–336 · Level 2",
      title: "L2 的补给机制与目标判定",
      image: "assets/l2-final-route.png",
      alt: "第二关接近最终路线时的画面",
      caption: "env step 331：上方补给已恢复计时条，tile 正沿最后路线接近目标。",
      observation:
        "青色环进入后消失并免费把两条计时条补满；开关会改变 display 朝向。某些反射关系可进入目标框，但接触并不会直接升关。",
      hypothesis:
        "青色环是一用即消耗的 recharge source；L2 每次普通动作消耗两格。目标接触比面板通行更严格，需要精确朝向。",
      action:
        "用两个补给点维持资源，反复经过开关调整图形；在 evidence 272 主动测试一个非精确候选，它未移动、未扣时、未升关。",
      result:
        "“反射即可完成”被反例收缩为 exact-only completion；修订路线后在 evidence/env 336 完成 L2。",
      status: "supported",
      statusLabel: "supported after falsification",
      evidence: "H_cyan_source、H_exact_orientation = supported；L2 checkpoint env 336 / call 50。",
    },
    reject: {
      step: "阶段 4 · evidence 337–467 · Level 3",
      title: "L3 中两条迁移假说被真实接触否证",
      image: "assets/l3-rejected.png",
      alt: "第三关目标关系第二次被拒后的画面",
      caption: "env step 467：第二种目标关系被真实接触证伪；tile 原地不动，资源也未消耗。",
      observation:
        "L3 新增蓝边 portal、紫色 display 和方向相关开关。按旧经验，精确 equality 应该完成，但 evidence 439 的目标接触没有反应；恢复后的 half-turn 在 467 再次被拒。",
      hypothesis:
        "先测试紫色 display 与目标精确相等，再测试 180° half-turn。这两种都是合理迁移候选，但不能只因 L2 成功就视为已确认。",
      action:
        "分别把两种候选朝向带到目标并进行一次免费接触；把‘不移动、不扣时、不升关’记录为反例。",
      result:
        "exact equality 与 half-turn 两条目标关系均被拒绝；相应反例保留在假说账本和 notes 历史中。",
      status: "rejected",
      statusLabel: "2 hypotheses rejected",
      evidence: "H_level3_gate_contact = supported；H_level3_purple_goal 记录 evidence 439 与 467 的双重拒绝。",
    },
    current: {
      step: "阶段 5 · evidence 478–493 · Level 3 未完成",
      title: "调用预算停止时的未决候选",
      image: "assets/l3-current.png",
      alt: "Full harness 结束时第三关当前画面",
      caption: "env step 493：portal 和上方补给路线再次通过预测校验，tile 已接近中央开关。",
      observation:
        "八次向上动作再次验证 portal；上方青色补给再次免费充满两条计时条。当前 half-turn 朝向在这些动作中保持不变。",
      hypothesis:
        "下一候选是目标的 top-bottom reflection；从上方进入中央开关可能产生所需变换。若仍失败，再测试 left-right reflection。",
      action:
        "把 tile 带到距上方入开关测试约四步的位置，同时在 notes 中写下具体路线和触发修订的条件。",
      result:
        "72-call 上限先到，L3 未完成。候选状态保持为 active，而不是被提升为 supported，并记录下一项可证伪测试。",
      status: "active",
      statusLabel: "active / unresolved",
      evidence: "H_current_orientation、H_level3_purple_goal = active；最终 notes v72，evidence 478–493。",
    },
  };

  const qs = (selector, root = document) => root.querySelector(selector);
  const qsa = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function renderThought(stageKey) {
    const stage = thoughtStages[stageKey];
    if (!stage) return;

    const image = qs("#thinking-image");
    image.src = stage.image;
    image.alt = stage.alt;
    qs("#thinking-caption").textContent = stage.caption;
    qs("#thought-step").textContent = stage.step;
    qs("#thought-title").textContent = stage.title;
    qs("#thought-observation").textContent = stage.observation;
    qs("#thought-hypothesis").textContent = stage.hypothesis;
    qs("#thought-action").textContent = stage.action;
    qs("#thought-result").textContent = stage.result;
    qs("#thought-evidence").textContent = stage.evidence;

    const status = qs("#thought-status");
    status.textContent = stage.statusLabel;
    status.className = "";
    if (stage.status === "rejected") status.classList.add("is-rejected");
    if (stage.status === "active") status.classList.add("is-active");

    qsa(".thinking-tab").forEach((button) => {
      const isActive = button.dataset.stage === stageKey;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-selected", String(isActive));
    });
  }

  qsa(".thinking-tab").forEach((button) => {
    button.addEventListener("click", () => renderThought(button.dataset.stage));
  });

  qsa(".filter-button").forEach((button) => {
    button.addEventListener("click", () => {
      const filter = button.dataset.filter;
      qsa(".filter-button").forEach((item) => {
        item.classList.toggle("is-active", item === button);
      });
      qsa(".experiment-row").forEach((row) => {
        row.hidden = filter !== "all" && row.dataset.grade !== filter;
      });
    });
  });

  function updateProgress() {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const ratio = max > 0 ? window.scrollY / max : 0;
    qs("#reading-progress-bar").style.width = `${Math.min(1, ratio) * 100}%`;
  }

  window.addEventListener("scroll", updateProgress, { passive: true });
  window.addEventListener("resize", updateProgress);

  renderThought("movement");
  updateProgress();
})();
