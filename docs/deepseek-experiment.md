# DeepSeek-v4-pro experiment notes
# Updated: 2026-07-24
#
# Harness upgrades in play:
# - GAME_OVER -> automatic RESET(0), keep Timeline + world_model.py + notes
# - backtest skips RESET / terminal bookkeeping (Schema-style)
# - cold-start explore + idle-theory explore burst
# - explore least-used fallback (avoid action-1 collapse)
#
# Protocol (fair text A/B, vision OFF):
# - Game: ls20, seed=0
#
# Phase history:
# - D0 smoke: thinking=high, max-actions 16 — many JSON failures
# - D1: thinking=high, delib=24, max-actions 220 — rewrite stall, 17 env steps
# - D1b: thinking=medium, delib=8, explore=16, harness-only 120 — full budget,
#   0 levels, 27/35 empty-content JSON failures
# - D2 (current): thinking=DISABLED (Sol-aligned), baseline_max_tokens=2048,
#   delib=16, explore=8, max-actions=160, timeout=10800, A/B both agents
#
# Success signals:
# - paired_valid
# - levels_completed >= 1 on either agent (primary)
# - harness planned_actions > 0 and fewer model_failures than D1b
# - game_over_resets > 0 if deaths occur after L1
