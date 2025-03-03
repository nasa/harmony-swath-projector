"""Utility classes used to extend the unittest capabilities."""

from os import sep
from os.path import basename
from shutil import copy


class StringContains:
    """A custom matcher that can be used in `unittest` assertions, ensuring
    a substring is contained in one of the expected arguments.

    """

    def __init__(self, expected_substring):
        self.expected_substring = expected_substring

    def __eq__(self, string_to_check):
        return self.expected_substring in string_to_check


def download_side_effect(file_path, working_dir, **kwargs):
    """A side effect to be used when mocking the `harmony.util.download`
    function. This should copy the input file (assuming it is a local
    file path) to the working directory, and then return the new file
    path.

    """
    file_base_name = basename(file_path)
    output_file_path = sep.join([working_dir, file_base_name])

    copy(file_path, output_file_path)
    return output_file_path
