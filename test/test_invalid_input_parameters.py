import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


import unittest
from unittest.mock import patch

from reproject import HarmonyAdapter
from harmony import BaseHarmonyAdapter

from test_utils import contains, matches, TestBase


class TestReprojectInput(TestBase):

    # TEST CASE: No granules attribute
    #
    @patch.object(BaseHarmonyAdapter, 'completed_with_error')
    @patch.object(BaseHarmonyAdapter, 'cleanup')
    def test_input_with_no_granules_attribute(self, cleanup, completed_with_error):
        """Handle a harmony message that does not list any granules"""
        test_data = {}
        reprojector = HarmonyAdapter(test_data)
        reprojector.invoke()

        completed_with_error.assert_called_once_with(contains("No granules specified for reprojection"))
        cleanup.assert_called_once()



    # TEST CASE: Invalid granules attribute
    #
    @patch.object(BaseHarmonyAdapter, 'completed_with_error')
    @patch.object(BaseHarmonyAdapter, 'cleanup')
    def test_input_with_invalid_granules_attribute(self, cleanup, completed_with_error):
        """Handle a harmony message that has an invalid granule list"""
        test_data = {'granules' : 'string'}
        reprojector = HarmonyAdapter(test_data)
        reprojector.invoke()

        completed_with_error.assert_called_once_with(contains("Invalid granule list"))
        cleanup.assert_called_once()


    # TEST CASE: More than one granule provided
    #
    @patch.object(BaseHarmonyAdapter, 'completed_with_error')
    @patch.object(BaseHarmonyAdapter, 'cleanup')
    def test_completed_with_error_when_too_many_granules(self, cleanup, completed_with_error):
        """Handle a harmony message that has more than one granule in the granule list"""
        test_data = {'granules' : ["granule-1", "granule-2", "granule-3"]}
        reprojector = HarmonyAdapter(test_data)
        reprojector.invoke()

        completed_with_error.assert_called_once_with(contains("Too many granules"))
        cleanup.assert_called_once()




    # TEST CASE: No such local file
    #
    @patch.object(BaseHarmonyAdapter, 'completed_with_error')
    @patch.object(BaseHarmonyAdapter, 'cleanup')
    def test_completed_with_error_when_local_file_not_exists(self, cleanup, completed_with_error):
        """Handle a harmony message that references a granule local file that does not exist"""
        test_data = {'granules' : [{'local_filename' : '/home/test/data/no_such_file'}]}
        reprojector = HarmonyAdapter(test_data)
        reprojector.invoke()

        completed_with_error.assert_called_once_with(contains("Input file does not exist"))
        cleanup.assert_called_once()



    # TEST CASE: Local file is not a valid data file
    #
    @patch.object(BaseHarmonyAdapter, 'completed_with_error')
    @patch.object(BaseHarmonyAdapter, 'cleanup')
    def test_completed_with_error_when_local_file_not_valid(self, cleanup, completed_with_error):
        """Handle a harmony message that references a granule local file that is not valid data"""
        test_data = {'granules' : [{'local_filename' : '/home/test/data/InvalidDataFile.nc'}]}
        reprojector = HarmonyAdapter(test_data)
        reprojector.invoke()

        completed_with_error.assert_called_once_with(contains("Cannot determine input file format"))
        cleanup.assert_called_once()

if __name__ == '__main__':
    unittest.main()