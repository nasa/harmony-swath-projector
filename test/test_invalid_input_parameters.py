import unittest
from harmony.util import HarmonyException, config
from harmony.message import Message

from swotrepr import HarmonyAdapter
from pymods.reproject import reproject
from test.test_utils import TestBase


class TestReprojectInput(TestBase):

    # TEST CASE: No granules attribute
    #
    def test_raises_when_input_has_no_granules_attribute(self):
        """Handle a harmony message that does not list any granules"""
        reprojector = HarmonyAdapter(Message({
            'format': {},
            'sources': [{}]
        }), config=config(False))

        with self.assertRaises(HarmonyException) as cm:
            reprojector.invoke()

        self.assertEqual(str(cm.exception), 'No granules specified for reprojection')

    # TEST CASE: No such local file
    #
    def test_raises_when_local_file_does_not_exist(self):
        """Handle a harmony message that references a granule local file that does not exist"""
        reprojector = HarmonyAdapter(Message({
            'format': {},
            'sources': [{'granules': [{}]}]
        }), config=config(False))

        with self.assertRaises(Exception) as cm:
            reproject(reprojector.message, 'test/data/no_such_file', '/no/such/dir', reprojector.logger)

        self.assertEqual(str(cm.exception), 'Input file does not exist')

    # TEST CASE: Local file is not a valid data file
    #
    def test_raises_when_local_file_not_valid(self):
        """Handle a harmony message that references a granule local file that is not valid data"""

        reprojector = HarmonyAdapter(Message({
            'format': {},
            'sources': [{'granules': [{}]}]
        }), config=config(False))

        with self.assertRaises(Exception) as cm:
            reproject(reprojector.message, 'test/data/InvalidDataFile.nc', '/no/such/dir', reprojector.logger)

        self.assertEqual(str(cm.exception), 'Cannot determine input file format')


if __name__ == '__main__':
    unittest.main()
