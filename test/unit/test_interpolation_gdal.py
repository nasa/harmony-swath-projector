from logging import Logger
from subprocess import STDOUT
from unittest.mock import patch

import numpy as np
import xarray

from PyMods.interpolation_gdal import (gdal_resample_all_variables,
                                       gdal_resample)
from test.test_utils import TestBase


class TestInterpolationGdal(TestBase):

    def setUp(self):
        self.file_information = (
            'SUBDATASET_1_NAME=NETCDF:"test/data/africa.nc":lat\n'
            'SUBDATASET_2_NAME=NETCDF:"test/data/africa.nc":lon\n'
            'SUBDATASET_3_NAME=NETCDF:"test/data/africa.nc":red_var\n'
            'SUBDATASET_4_NAME=NETCDF:"test/data/africa.nc":green_var\n'
            'SUBDATASET_5_NAME=NETCDF:"test/data/africa.nc":blue_var\n'
            'SUBDATASET_6_NAME=NETCDF:"test/data/africa.nc":alpha_var\n'
        )
        self.message_parameters = {'input_file': 'test/data/africa.nc'}
        self.temp_directory = '/tmp/01234'
        self.variable = 'NETCDF:"file.nc":variable_name'
        self.output_file = 'path/to/output.nc'
        self.logger = Logger('test')
        self.base_parameters = {'crs': 'EPSG:4326'}
        self.basic_command = ['gdalwarp', '-geoloc', '-t_srs', 'EPSG:4326',
                              self.variable, self.output_file]

    @patch('PyMods.interpolation_gdal.gdal_resample')
    def test_gdal_resample_all_variables(self, mock_gdal_resample):
        """ Ensure gdal_resample is called for each non-coordinate variable,
            and those variables are all included in the list of outputs.

        """
        output_variables = gdal_resample_all_variables(self.message_parameters,
                                                       self.file_information,
                                                       self.temp_directory,
                                                       self.logger)
        expected_output = ['red_var', 'green_var', 'blue_var', 'alpha_var']
        self.assertEqual(output_variables, expected_output)
        self.assertEqual(mock_gdal_resample.call_count, 4)

        for variable in expected_output:
            full_variable = f'NETCDF:"test/data/africa.nc":{variable}'
            variable_output_path = f'/tmp/01234/{variable}.nc'
            mock_gdal_resample.assert_any_call(self.message_parameters,
                                               full_variable,
                                               variable_output_path,
                                               self.logger)

    @patch('PyMods.interpolation_gdal.gdal_resample')
    def test_gdal_resample_single_exception(self, mock_gdal_resample):
        """ Ensure that if a single variable fails reprojection, the remaining
            variables will still be reprojected.

        """
        mock_gdal_resample.side_effect = [KeyError('random'), None, None, None]

        output_variables = gdal_resample_all_variables(self.message_parameters,
                                                       self.file_information,
                                                       self.temp_directory,
                                                       self.logger)

        expected_output = ['green_var', 'blue_var', 'alpha_var']
        self.assertEqual(output_variables, expected_output)
        self.assertEqual(mock_gdal_resample.call_count, 4)

        all_variables = expected_output + ['red_var']

        for variable in all_variables:
            full_variable = f'NETCDF:"test/data/africa.nc":{variable}'
            variable_output_path = f'/tmp/01234/{variable}.nc'
            mock_gdal_resample.assert_any_call(self.message_parameters,
                                               full_variable,
                                               variable_output_path,
                                               self.logger)

    @patch('subprocess.check_output')
    def test_gdal_resample(self, mock_check_output):
        """ Ensure that the correct command is being sent to gdalwarp, given
            no additional parameters.

        """

        with self.subTest('No additional command options'):
            gdal_resample(self.base_parameters, self.variable,
                          self.output_file, self.logger)
            mock_check_output.assert_called_once_with(self.basic_command,
                                                      stderr=STDOUT)

    @patch('subprocess.check_output')
    def test_gdal_resample_interpolation(self, mock_check_output):
        """ Ensure the correct command is being sent to gdalwarp, for valid or
            invalid interpolation options.

        """
        with self.subTest('With valid interpolation'):
            parameters = {'interpolation': 'near'}
            parameters.update(self.base_parameters)
            gdal_resample(parameters, self.variable, self.output_file,
                          self.logger)
            mock_check_output.assert_called_once_with([
                'gdalwarp', '-geoloc', '-t_srs', 'EPSG:4326', '-r', 'near',
                self.variable, self.output_file
            ], stderr=STDOUT)

        with self.subTest('Ignores EWA interpolation'):
            mock_check_output.reset_mock()
            parameters = {'interpolation': 'ewa'}
            parameters.update(self.base_parameters)
            gdal_resample(parameters, self.variable, self.output_file,
                          self.logger)
            mock_check_output.assert_called_once_with(self.basic_command,
                                                      stderr=STDOUT)

    @patch('subprocess.check_output')
    def test_gdal_resample_extents(self, mock_check_output):
        """ Ensure the correct command is being sent to gdalwarp, for valid or
            invalid x_extent and y_extent options.

        """
        with self.subTest('With valid x_extent and y_extent'):
            parameters = {'x_extent': {'min': -20, 'max': 60},
                          'x_min': -20,
                          'x_max': 60,
                          'y_extent': {'min': 10, 'max': 35},
                          'y_min': 10,
                          'y_max': 35}

            parameters.update(self.base_parameters)
            gdal_resample(parameters, self.variable, self.output_file,
                          self.logger)
            mock_check_output.assert_called_once_with([
                'gdalwarp', '-geoloc', '-t_srs', 'EPSG:4326', '-te', '-20',
                '10', '60', '35', self.variable, self.output_file
            ], stderr=STDOUT)

        with self.subTest('Ignores x_extent when missing y_extent'):
            mock_check_output.reset_mock()
            parameters = {'x_extent': {'min': -20, 'max': 60},
                          'x_min': -20,
                          'x_max': 60}
            parameters.update(self.base_parameters)
            gdal_resample(parameters, self.variable, self.output_file,
                          self.logger)
            mock_check_output.assert_called_once_with(self.basic_command,
                                                      stderr=STDOUT)

        with self.subTest('Ignores y_extent when missing x_extent'):
            mock_check_output.reset_mock()
            parameters = {'y_extent': {'min': 10, 'max': 35},
                          'y_min': 10,
                          'y_max': 35}
            parameters.update(self.base_parameters)
            gdal_resample(parameters, self.variable, self.output_file,
                          self.logger)
            mock_check_output.assert_called_once_with(self.basic_command,
                                                      stderr=STDOUT)

    @patch('subprocess.check_output')
    def test_gdal_resample_resolutions(self, mock_check_output):
        """ Ensure the correct command is being sent to gdalwarp, for valid or
            invalid xres and yres options.

        """
        with self.subTest('With valid xres and yres'):
            # Using non-square pixels, just to make sure xres and yres are
            # placed in the correct order.
            parameters = {'xres': 36, 'yres': 12}
            parameters.update(self.base_parameters)
            gdal_resample(parameters, self.variable, self.output_file, self.logger)
            mock_check_output.assert_called_once_with([
                'gdalwarp', '-geoloc', '-t_srs', 'EPSG:4326', '-tr', '36',
                '12', self.variable, self.output_file
            ], stderr=STDOUT)

        with self.subTest('Ignores xres when missing yres'):
            mock_check_output.reset_mock()
            parameters = {'xres': 36}
            parameters.update(self.base_parameters)
            gdal_resample(parameters, self.variable, self.output_file,
                          self.logger)
            mock_check_output.assert_called_once_with(self.basic_command,
                                                      stderr=STDOUT)

        with self.subTest('Ignores yres when missing xres'):
            mock_check_output.reset_mock()
            parameters = {'yres': 12}
            parameters.update(self.base_parameters)
            gdal_resample(parameters, self.variable, self.output_file,
                          self.logger)
            mock_check_output.assert_called_once_with(self.basic_command,
                                                      stderr=STDOUT)

    @patch('subprocess.check_output')
    def test_gdal_resample_dimensions(self, mock_check_output):
        """ Ensure the correct command is being sent to gdalwarp, for valid or
            invalid width and height options.

        """
        with self.subTest('With valid width and height'):
            parameters = {'height': 500, 'width': 1000}
            parameters.update(self.base_parameters)
            gdal_resample(parameters, self.variable, self.output_file,
                          self.logger)
            mock_check_output.assert_called_once_with([
                'gdalwarp', '-geoloc', '-t_srs', 'EPSG:4326', '-ts', '1000',
                '500', self.variable, self.output_file
            ], stderr=STDOUT)

        with self.subTest('Ignores width when missing height'):
            mock_check_output.reset_mock()
            parameters = {'width': 1000}
            parameters.update(self.base_parameters)
            gdal_resample(parameters, self.variable, self.output_file,
                          self.logger)
            mock_check_output.assert_called_once_with(self.basic_command,
                                                      stderr=STDOUT)

        with self.subTest('Ignores height when missing width'):
            mock_check_output.reset_mock()
            parameters = {'height': 500}
            parameters.update(self.base_parameters)
            gdal_resample(parameters, self.variable, self.output_file,
                          self.logger)
            mock_check_output.assert_called_once_with(self.basic_command,
                                                      stderr=STDOUT)
