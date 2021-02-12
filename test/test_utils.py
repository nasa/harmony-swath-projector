""" Utility classes used to extend the unittest capabilities. """
from os import sep
from os.path import basename
from shutil import copy
import inspect
import logging
import unittest


class TestLogHandler(logging.Handler):
    """ Custom log handler that captures all root logging output from the unit
        tests.

    """
    messages = []

    def emit(self, record):
        msg = self.format(record)
        self.messages.append(msg)

    def reset(self):
        self.messages = []

    def get_messages(self):
        return self.messages


class TestBase(unittest.TestCase):
    """ Base test class that wraps tests to handle output of test descriptions
        using docstrings

    """

    _log_handler = None

    def setUp(self):
        description = inspect.getdoc(getattr(self, self._testMethodName)) or self._testMethodName
        hdr = '-' * (len(description) + 6)
        print("\n%s\nTEST: %s\n%s" % (hdr, description, hdr))

        if not TestBase._log_handler:
            TestBase._log_handler = TestLogHandler()
            logging.basicConfig(handlers=[TestBase._log_handler], level=logging.DEBUG)

        TestBase._log_handler.reset()


    def tearDown(self):
        messages = TestBase._log_handler.get_messages()
        if messages:
            print("Logging output:")
            for msg in messages:
                print("   ", msg)
        print("\n\n")


class StringContains:
    """ A custom matcher that can be used in `unittest` assertions, ensuring
        a substring is contained in one of the expected arguments.

    """
    def __init__(self, expected_substring):
        self.expected_substring = expected_substring

    def __eq__(self, string_to_check):
        return self.expected_substring in string_to_check


def download_side_effect(file_path, working_dir, **kwargs):
    """ A side effect to be used when mocking the `harmony.util.download`
        function. This should copy the input file (assuming it is a local
        file path) to the working directory, and then return the new file
        path.

    """
    file_base_name = basename(file_path)
    output_file_path = sep.join([working_dir, file_base_name])

    copy(file_path, output_file_path)
    return output_file_path
