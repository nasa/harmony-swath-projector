from logging import Logger
from unittest.mock import Mock, patch

from pyproj import Proj
from pyresample.geometry import AreaDefinition
import numpy as np
import xarray

from PyMods.interpolation_pyresample import (check_for_valid_interpolation,
                                             EPSILON,
                                             FILL_VALUE,
                                             get_swath_definition,
                                             get_target_area,
                                             pyresample_bilinear,
                                             pyresample_ewa,
                                             pyresample_nearest_neighbour,
                                             resample_all_variables,
                                             resample_variable,
                                             RADIUS_OF_INFLUENCE,
                                             ROWS_PER_SCAN)
from test.test_utils import TestBase


class TestInterpolationPyResample(TestBase):

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
        self.logger = Logger('test')

    @patch('xarray.open_dataset')
    @patch('PyMods.interpolation_pyresample.get_target_area')
    @patch('PyMods.interpolation_pyresample.resample_variable')
    def test_resample_all_variables(self, mock_resample_variable,
                                    mock_target_area, mock_open_dataset):
        """ Ensure resample_variable is called for each non-coordinate
            variable, and those variables are all included in the list of
            outputs.

        """
        fake_dataset = 'a dataset'
        mock_open_dataset.return_value = fake_dataset

        fake_target_area = 'a target area'
        mock_target_area.return_value = fake_target_area

        parameters = {'interpolation': 'near'}
        parameters.update(self.message_parameters)

        output_variables = resample_all_variables(parameters,
                                                  self.file_information,
                                                  self.temp_directory,
                                                  self.logger)

        expected_output = ['red_var', 'green_var', 'blue_var', 'alpha_var']
        self.assertEqual(output_variables, expected_output)
        self.assertEqual(mock_resample_variable.call_count, 4)

        print(mock_resample_variable.calls)
        for variable in expected_output:
            variable_output_path = f'/tmp/01234/{variable}.nc'
            mock_resample_variable.assert_any_call(parameters,
                                                   fake_dataset,
                                                   variable,
                                                   {},
                                                   fake_target_area,
                                                   variable_output_path,
                                                   self.logger)

    @patch('xarray.open_dataset')
    @patch('PyMods.interpolation_pyresample.get_target_area')
    @patch('PyMods.interpolation_pyresample.resample_variable')
    def test_resample_single_exception(self, mock_resample_variable,
                                       mock_target_area, mock_open_dataset):
        """ Ensure that if a single variable fails reprojection, the remaining
            variables will still be reprojected.

        """
        fake_dataset = 'a dataset'
        mock_open_dataset.return_value = fake_dataset

        fake_target_area = 'a target area'
        mock_target_area.return_value = fake_target_area

        mock_resample_variable.side_effect = [KeyError('random'), None, None, None]

        parameters = {'interpolation': 'near'}
        parameters.update(self.message_parameters)

        output_variables = resample_all_variables(parameters,
                                                  self.file_information,
                                                  self.temp_directory,
                                                  self.logger)

        expected_output = ['green_var', 'blue_var', 'alpha_var']
        self.assertEqual(output_variables, expected_output)
        self.assertEqual(mock_resample_variable.call_count, 4)

        all_variables = expected_output + ['red_var']

        for variable in all_variables:
            variable_output_path = f'/tmp/01234/{variable}.nc'
            mock_resample_variable.assert_any_call(parameters,
                                                   fake_dataset,
                                                   variable,
                                                   {},
                                                   fake_target_area,
                                                   variable_output_path,
                                                   self.logger)

    @patch('PyMods.interpolation_pyresample.pyresample_nearest_neighbour')
    @patch('PyMods.interpolation_pyresample.pyresample_ewa')
    @patch('PyMods.interpolation_pyresample.pyresample_bilinear')
    def test_resample_variable(self, mock_bilinear, mock_ewa, mock_nearest):
        """ Ensure that for each interpolation method, the correct function is
            called to reproject the variable.

        """
        test_args = [['bilinear', 1, 0, 0], ['ewa', 0, 1, 0], ['near', 0, 0, 1]]

        for interpolation, bilinear_calls, ewa_calls, nearest_calls in test_args:
            with self.subTest(interpolation):
                mock_bilinear.reset_mock()
                mock_ewa.reset_mock()
                mock_nearest.reset_mock()

                parameters = {'interpolation': interpolation}
                resample_variable(parameters, 'fake dataset', 'variable_name',
                                  {}, 'target area', '/output/path.nc',
                                  self.logger)

                self.assertEqual(mock_bilinear.call_count, bilinear_calls)
                self.assertEqual(mock_ewa.call_count, ewa_calls)
                self.assertEqual(mock_nearest.call_count, nearest_calls)

    @patch('PyMods.interpolation_pyresample.write_netcdf')
    @patch('PyMods.interpolation_pyresample.get_swath_definition')
    @patch('PyMods.interpolation_pyresample.get_variable_values')
    @patch('PyMods.interpolation_pyresample.get_sample_from_bil_info')
    @patch('PyMods.interpolation_pyresample.get_bil_info')
    def test_resample_bilinear(self, mock_get_bil_info, mock_get_sample,
                               mock_get_values, mock_get_swath,
                               mock_write_netcdf):
        """ The bilinear interpolation should call both get_bil_info and
            get_sample_from_bil_info if there are no matching entries for the
            coordinates in the reprojection information. If there is an entry,
            then only get_sample_from_bil_info should be called.

        """
        mock_get_bil_info.return_value = ['vertical', 'horizontal',
                                          'input_indices', 'point_mapping']
        mock_get_sample.return_value = 'results'
        mock_get_swath.return_value = 'swath'
        mock_values = Mock(**{'ravel.return_value': 'ravel data'})
        mock_get_values.return_value = mock_values

        dataset = xarray.open_dataset('test/data/africa.nc', decode_cf=False)
        projection = Proj('+proj=longlat +ellps=WGS84')

        message_parameters = {'projection': projection,
                              'grid_transform': 'grid_transform value'}
        target_area = Mock(spec=AreaDefinition, shape='ta_shape')

        with self.subTest('No pre-existing bilinear information'):
            pyresample_bilinear(message_parameters, dataset, 'alpha_var',
                                {}, target_area, 'path/to/output', self.logger)

            mock_get_bil_info.assert_called_once_with('swath', target_area,
                                                      radius=50000,
                                                      neighbours=16)
            mock_get_sample.assert_called_once_with('ravel data',
                                                    'vertical',
                                                    'horizontal',
                                                    'input_indices',
                                                    'point_mapping',
                                                    output_shape='ta_shape')
            mock_write_netcdf.assert_called_once_with('path/to/output',
                                                      'results',
                                                      projection,
                                                      'grid_transform value')

        with self.subTest('Pre-existing bilinear information'):
            mock_get_bil_info.reset_mock()
            mock_get_sample.reset_mock()
            mock_write_netcdf.reset_mock()

            bilinear_information = {
                ('lon', 'lat'): {
                    'vertical_distances': 'vertical_old',
                    'horizontal_distances': 'horizontal_old',
                    'valid_input_indices': 'input_indices_old',
                    'valid_point_mapping': 'point_mapping_old',
                }
            }

            pyresample_bilinear(message_parameters, dataset, 'alpha_var',
                                bilinear_information, target_area,
                                'path/to/output', self.logger)

            mock_get_bil_info.assert_not_called()
            mock_get_sample.assert_called_once_with('ravel data',
                                                    'vertical_old',
                                                    'horizontal_old',
                                                    'input_indices_old',
                                                    'point_mapping_old',
                                                    output_shape='ta_shape')
            mock_write_netcdf.assert_called_once_with('path/to/output',
                                                      'results',
                                                      projection,
                                                      'grid_transform value')

    @patch('PyMods.interpolation_pyresample.write_netcdf')
    @patch('PyMods.interpolation_pyresample.get_swath_definition')
    @patch('PyMods.interpolation_pyresample.get_variable_values')
    @patch('PyMods.interpolation_pyresample.fornav')
    @patch('PyMods.interpolation_pyresample.ll2cr')
    def test_resample_ewa(self, mock_ll2cr, mock_fornav, mock_get_values,
                          mock_get_swath, mock_write_netcdf):
        """ EWA interpolation should call both ll2cr and fornav if there are
            no matching entries for the coordinates in the reprojection
            information. If there is an entry, then only fornav  should be
            called.

        """
        mock_ll2cr.return_value = ['swath_points_in_grid', 'columns', 'rows']
        mock_fornav.return_value = ('', 'results')
        mock_get_swath.return_value = 'swath'
        mock_values = np.ones((2, 3))
        mock_get_values.return_value = mock_values

        dataset = xarray.open_dataset('test/data/africa.nc', decode_cf=False)
        projection = Proj('+proj=longlat +ellps=WGS84')

        message_parameters = {'projection': projection,
                              'grid_transform': 'grid_transform value'}
        target_area = Mock(spec=AreaDefinition)

        with self.subTest('No pre-existing bilinear information'):
            pyresample_ewa(message_parameters, dataset, 'alpha_var', {},
                           target_area, 'path/to/output', self.logger)

            mock_ll2cr.assert_called_once_with('swath', target_area)
            mock_fornav.assert_called_once_with('columns', 'rows', target_area,
                                                mock_values,
                                                rows_per_scan=ROWS_PER_SCAN)
            mock_write_netcdf.assert_called_once_with('path/to/output',
                                                      'results',
                                                      projection,
                                                      'grid_transform value')

        with self.subTest('Pre-existing bilinear information'):
            mock_ll2cr.reset_mock()
            mock_fornav.reset_mock()
            mock_write_netcdf.reset_mock()

            ewa_information = {('lon', 'lat'): {'columns': 'old_columns',
                                                'rows': 'old_rows'}}

            pyresample_ewa(message_parameters, dataset, 'alpha_var',
                           ewa_information, target_area, 'path/to/output',
                           self.logger)

            mock_ll2cr.assert_not_called()
            mock_fornav.assert_called_once_with('old_columns', 'old_rows',
                                                target_area, mock_values,
                                                rows_per_scan=ROWS_PER_SCAN)
            mock_write_netcdf.assert_called_once_with('path/to/output',
                                                      'results',
                                                      projection,
                                                      'grid_transform value')

    @patch('PyMods.interpolation_pyresample.write_netcdf')
    @patch('PyMods.interpolation_pyresample.get_swath_definition')
    @patch('PyMods.interpolation_pyresample.get_variable_values')
    @patch('PyMods.interpolation_pyresample.resample_nearest')
    def test_resample_nearest(self, mock_nearest, mock_get_values,
                              mock_get_swath, mock_write_netcdf):
        """ EWA interpolation should call both ll2cr and fornav if there are
            no matching entries for the coordinates in the reprojection
            information. If there is an entry, then only fornav  should be
            called.

        """
        mock_nearest.return_value = 'results'
        mock_get_swath.return_value = 'swath'
        mock_values = np.ones((2, 3))
        mock_get_values.return_value = mock_values

        dataset = xarray.open_dataset('test/data/africa.nc', decode_cf=False)
        projection = Proj('+proj=longlat +ellps=WGS84')

        message_parameters = {'projection': projection,
                              'grid_transform': 'grid_transform value'}
        target_area = Mock(spec=AreaDefinition)

        pyresample_nearest_neighbour(message_parameters, dataset, 'alpha_var',
                                     {}, target_area, 'path/to/output',
                                     self.logger)

        mock_nearest.assert_called_once_with('swath', mock_values, target_area,
                                             radius_of_influence=RADIUS_OF_INFLUENCE,
                                             fill_value=FILL_VALUE,
                                             epsilon=EPSILON)

        mock_write_netcdf.assert_called_once_with('path/to/output',
                                                  'results',
                                                  projection,
                                                  'grid_transform value')

    def test_check_for_valid_interpolation(self):
        """ Ensure all valid interpolations don't raise an exception. """
        interpolations = ['bilinear', 'ewa', 'near']

        for interpolation in interpolations:
            with self.subTest(interpolation):
                parameters = {'interpolation': interpolation}
                check_for_valid_interpolation(parameters, self.logger)

        with self.subTest('Invalid interpolation'):
            with self.assertRaises(ValueError):
                parameters = {'interpolation': 'something else'}
                check_for_valid_interpolation(parameters, self.logger)

    def test_get_swath_definition(self):
        """ Ensure a valid SwathDefinition object can be created for a dataset
            with coordinates. The shape of the swath definition should match
            the shapes of the input coordinates, and the longitude and latitude
            values should be correctly stored in the swath definition.

        """
        dataset = xarray.open_dataset('test/data/africa.nc', decode_cf=False)
        longitudes = dataset.variables.get('lon')
        latitudes = dataset.variables.get('lat')
        coordinates = ('lat', 'lon')
        swath_definition = get_swath_definition(dataset, coordinates)

        self.assertEqual(swath_definition.shape, longitudes.shape)
        np.testing.assert_array_equal(longitudes, swath_definition.lons)
        np.testing.assert_array_equal(latitudes, swath_definition.lats)

    def test_get_target_area(self):
        """ Ensure a valid AreaDefinition object can be created from a
            processed SwotRepr message. The object should contain a grid that
            is linearly spaced in both projected coordinates, with the
            specified number of rows and columns.

        """
        parameters = {'height': 3,
                      'width': 6,
                      'projection': Proj('+proj=longlat'),
                      'x_min': -20,
                      'x_max': 40,
                      'y_min': 20,
                      'y_max': 50}

        # The expected coordinates are to the cell centres, where as the
        # extents are to the edges of the grids.
        expected_x_coord = np.array([-15, -5, 5, 15, 25, 35])
        expected_y_coord = np.array([45, 35, 25])

        area_definition = get_target_area(parameters)

        self.assertEqual(area_definition.shape, (3, 6))

        self.assertEqual(area_definition.projection_x_coords.shape, (6, ))
        np.testing.assert_array_equal(area_definition.projection_x_coords,
                                      expected_x_coord)

        self.assertEqual(area_definition.projection_y_coords.shape, (3, ))
        np.testing.assert_array_equal(area_definition.projection_y_coords,
                                      expected_y_coord)
