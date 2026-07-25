# Sol / Schema proximity budget notes
# Date: 2026-07-22 (updated for Sol-ready .env)
#
# gpt-5.6-sol list price (short context): $5 / $0.50 cached / $30 output per 1M tokens.
# Default effort: medium. Do not use xhigh/max under $100.
#
# What money buys (order-of-magnitude, medium):
# - Phase0 smoke (12 actions, A/B or harness-focused): ~$2–5
# - Diagnostic 50–80 action pair: ~$5–15
# - Serious 100–200 action harness push for level>=1: ~$15–40
# - Schema-like 500–800 action clear with xhigh: NOT in $50 pool
#
# Recommended account budgets:
# - Smoke + one diagnostic: $15–25
# - Prove levels_completed>=1 on ls20 (serious): $50 (set ARC_MAX_SPEND_USD=45)
# - Single-game near-human efficiency attempt: $100–300
# - Multi-game Public-set style replication: $1000+
#
# Spend plan with $50 account + current Sol .env:
# 1) Confirm pricing is 5.0 / 0.5 / 30.0 and ARC_MAX_SPEND_USD=45
# 2) Phase0: --max-actions 12 (expect ~$2–5)
# 3) If backtest-green + any planned match: one 60–100 action harness run
# 4) Optional second seed/push only if remaining spend > ~$15
# 5) Stop on spend_budget; do not raise to xhigh on $50
