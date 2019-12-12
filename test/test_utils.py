#
# Utility classes used to extend the unittest capabilities
#
import inspect
import io
import logging
import re
import unittest




# Custom log handler that captures all root logging output
# from the unit tests.
#
class TestLogHandler(logging.Handler):

    messages = []

    def emit(self, record):
        msg = self.format(record)
        self.messages.append(msg)

    def reset(self):
        self.messages = []

    def get_messages(self):
        return self.messages


# Base test class that wraps tests to handle output of test
# descriptions using docstrings
#
class TestBase(unittest.TestCase):

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


# Extension class that allows a 'string contains' check in a unit test
# assertion. e.g.
#
# x.assert_called_once_with(contains(str))
#
class contains(str):
    def __eq__(self, other):
        return self.lower() in other.lower()


# Extension class that allows a regex type check in a unit test
# assertion. e.g.
#
# x.assert_called_once_with(matches(regex))
#
class matches(str):
    def __eq__(self, other):
        return re.search(self.lower(), other.lower(), re.IGNORECASE)