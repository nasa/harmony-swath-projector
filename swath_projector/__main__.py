"""Run the Harmony Swath Projector adapter via the Harmony CLI."""

from argparse import ArgumentParser
from sys import argv

from harmony import is_harmony_cli, run_cli, setup_cli

from swath_projector.adapter import SwathProjectorAdapter


def main(arguments: list[str]):
    """Parse command line arguments and invoke the appropriate method to
    respond to them.

    """
    parser = ArgumentParser(
        prog='harmony-swath-projector',
        description='Run the Harmony Swath Projector Tool',
    )
    setup_cli(parser)
    harmony_arguments, _ = parser.parse_known_args(arguments[1:])

    if is_harmony_cli(harmony_arguments):
        run_cli(parser, harmony_arguments, SwathProjectorAdapter)
    else:
        parser.error('Only --harmony CLIs are supported')


if __name__ == '__main__':
    main(argv)
