from pathlib import Path

DIR = Path(__file__).parent


def load(name: str, **kwargs: object) -> str:
    return (DIR / f"{name}.md").read_text().format(**kwargs)
