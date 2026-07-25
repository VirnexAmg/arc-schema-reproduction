import arc_agi
from arcengine import GameAction


def main() -> None:
    print("1. Initializing Arcade...")
    arc = arc_agi.Arcade()

    print("2. Creating ls20 environment...")
    env = arc.make("ls20", render_mode="terminal")

    if env is None:
        raise RuntimeError("Failed to create environment")

    print("3. Available actions:")
    print(env.action_space)

    print("4. Taking ACTION1...")
    observation = env.step(GameAction.ACTION1)

    print("5. Observation:")
    print(observation)

    print("6. Scorecard:")
    print(arc.get_scorecard())


if __name__ == "__main__":
    main()