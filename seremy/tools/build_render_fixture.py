"""Generate a deterministic 100-file, 50,000-line canvas benchmark input."""
from pathlib import Path
import argparse


def generate(root):
    root = Path(root).resolve()
    for index in range(100):
        directory = root / f'package{index // 10}'
        directory.mkdir(parents=True, exist_ok=True)
        lines = [f'def function{number}(): return {number}' for number in range(10)]
        lines += ['# source context for the rendering workload'] * 440
        lines += [f'function{number % 10}()' for number in range(50)]
        (directory / f'module{index}.py').write_text('\n'.join(lines), encoding='utf8')
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    print(generate(parser.parse_args().output))


if __name__ == '__main__':
    main()
