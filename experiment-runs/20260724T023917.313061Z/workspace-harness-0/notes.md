# Observed patterns
- There are two interacting areas: puzzle area rows 8-24 (cols 32-40) and counter area rows 61-62.
- Actions 1 and 2 alternate between two puzzle states (A and B) located in rows 8-24, while simultaneously incrementing the count of color 3 and decrementing color 11 in rows 61-62. Each proper action (1 or 2) changes the counter by 1, but sometimes an action does nothing (likely when not the correct turn).
- Action 3 initially set counter to 3:34,11:8 without changing the puzzle area (only rows 61-62 changed). Its role is unclear; possibly starts the sequence.
- Action 4 is untried. Explore it next to see its effect.