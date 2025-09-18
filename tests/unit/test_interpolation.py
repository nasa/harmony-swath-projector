from logging import Logger
from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch

import numpy as np
from netCDF4 import Dataset, Dimension
from pyproj import Proj
from pyresample.geometry import AreaDefinition
from varinfo import VarInfoFromNetCDF4

from swath_projector.interpolation import (
    EPSILON,
    RADIUS_OF_INFLUENCE,
    allocate_target_array,
    check_for_valid_interpolation,
    get_parameters_tuple,
    get_reprojection_cache,
    get_swath_definition,
    get_target_area,
    resample_all_variables,
    resample_layer,
    resample_variable,
    resample_variable_data,
)
from swath_projector.nc_single_band import HARMONY_TARGET
from swath_projector.reproject import CF_CONFIG_FILE


class TestInterpolation(TestCase):

    def setUp(self):
        self.science_variables = ('/red_var', '/green_var', '/blue_var', '/alpha_var')
        self.message_parameters = {
            'crs': '+proj=longlat',
            'input_file': 'tests/data/africa.nc',
            'interpolation': 'bilinear',
            'projection': Proj('+proj=longlat'),
            'height': None,
            'width': None,
            'x_extent': None,
            'y_extent': None,
            'x_min': None,
            'x_max': None,
            'y_min': None,
            'y_max': None,
            'xres': None,
            'yres': None,
        }
        self.temp_directory = '/tmp/01234'
        self.logger = Logger('test')
        self.var_info = VarInfoFromNetCDF4(
            self.message_parameters['input_file'],
            short_name='harmony_example_l2',
            config_file=CF_CONFIG_FILE,
        )
        self.mock_target_area = MagicMock(
            spec=AreaDefinition, shape='ta_shape', area_id='/lon, /lat'
        )

    def assert_areadefinitions_equal(self, area_one, area_two):
        """Compare the properties of two AreaDefinitions."""
        # Check the ID is set, as it is used in nc_single_band:
        self.assertEqual(area_one.area_id, area_two.area_id)

        # Check the corner points:
        self.assertListEqual(area_one.corners, area_two.corners)

        attributes = ['height', 'width', 'proj_str']

        for attribute in attributes:
            self.assertEqual(
                getattr(area_one, attribute), getattr(area_two, attribute), attribute
            )

    @patch('swath_projector.interpolation.resample_variable')
    def test_resample_all_variables(self, mock_resample_variable):
        """Ensure resample_variable is called for each non-coordinate
        variable, and those variables are all included in the list of
        outputs.

        The default message being supplied does not have sufficient
        information to construct a target area for all variables, so the
        cache being sent to all variables should be empty.

        """
        parameters = {'interpolation': 'ewa-nn'}
        parameters.update(self.message_parameters)

        output_variables = resample_all_variables(
            parameters,
            self.science_variables,
            self.temp_directory,
            self.logger,
            self.var_info,
        )

        expected_output = ['/red_var', '/green_var', '/blue_var', '/alpha_var']
        self.assertEqual(output_variables, expected_output)
        self.assertEqual(mock_resample_variable.call_count, 4)

        for variable in expected_output:
            variable_output_path = f'/tmp/01234{variable}.nc'
            mock_resample_variable.assert_any_call(
                parameters,
                variable,
                {},
                variable_output_path,
                self.logger,
                self.var_info,
            )

    @patch('swath_projector.interpolation.resample_variable')
    def test_resample_single_exception(self, mock_resample_variable):
        """Ensure that if a single variable fails reprojection, the remaining
        variables will still be reprojected.

        """
        mock_resample_variable.side_effect = [KeyError('random'), None, None, None]

        parameters = {'interpolation': 'ewa-nn'}
        parameters.update(self.message_parameters)

        output_variables = resample_all_variables(
            parameters,
            self.science_variables,
            self.temp_directory,
            self.logger,
            self.var_info,
        )

        expected_output = ['/green_var', '/blue_var', '/alpha_var']
        self.assertEqual(output_variables, expected_output)
        self.assertEqual(mock_resample_variable.call_count, 4)

        all_variables = expected_output + ['/red_var']

        for variable in all_variables:
            variable_output_path = f'/tmp/01234{variable}.nc'
            mock_resample_variable.assert_any_call(
                parameters,
                variable,
                {},
                variable_output_path,
                self.logger,
                self.var_info,
            )

    @patch('swath_projector.interpolation.allocate_target_array')
    @patch('swath_projector.interpolation.get_preferred_ordered_dimensions_info')
    @patch('swath_projector.interpolation.write_single_band_output')
    @patch('swath_projector.interpolation.get_swath_definition')
    @patch('swath_projector.interpolation.get_target_area')
    @patch('swath_projector.interpolation.get_variable_values')
    @patch('swath_projector.interpolation.get_sample_from_bil_info')
    @patch('swath_projector.interpolation.get_bil_info')
    def test_resample_bilinear(
        self,
        mock_get_bil_info,
        mock_get_sample,
        mock_get_values,
        mock_get_target_area,
        mock_get_swath,
        mock_write_output,
        mock_get_preferred_ordered_dimensions_info,
        mock_allocate_target_array,
    ):
        """The bilinear interpolation should call both get_bil_info and
        get_sample_from_bil_info if there are no matching entries for the
        coordinates in the reprojection information. If there is an entry,
        then only get_sample_from_bil_info should be called.

        """
        mock_get_bil_info.return_value = [
            'vertical',
            'horizontal',
            'input_indices',
            'point_mapping',
        ]
        results = np.array([4.0])
        mock_get_sample.return_value = results
        mock_get_swath.return_value = 'swath'
        ravel_data = np.ones((3,))

        mock_values = MagicMock()
        mock_values.__getitem__.return_value.ravel.return_value = ravel_data
        mock_get_values.return_value = mock_values

        mock_get_target_area.return_value = self.mock_target_area

        mock_ordered_non_track_dim_objs = MagicMock()
        mock_get_preferred_ordered_dimensions_info.return_value = (
            None,
            mock_ordered_non_track_dim_objs,
        )

        message_parameters = self.message_parameters
        message_parameters['interpolation'] = 'bilinear'
        variable_name = '/alpha_var'
        output_path = 'path/to/output'

        with self.subTest('No pre-existing bilinear information'):
            resample_variable(
                message_parameters,
                variable_name,
                {},
                output_path,
                self.logger,
                self.var_info,
            )

            expected_cache = {
                ('/lat', '/lon'): {
                    'vertical_distances': 'vertical',
                    'horizontal_distances': 'horizontal',
                    'valid_input_indices': 'input_indices',
                    'valid_point_mapping': 'point_mapping',
                    'target_area': self.mock_target_area,
                },
            }

            mock_get_bil_info.assert_called_once_with(
                'swath', self.mock_target_area, radius=50000, neighbours=16
            )
            mock_get_sample.assert_called_once_with(
                ravel_data,
                'vertical',
                'horizontal',
                'input_indices',
                'point_mapping',
                output_shape='ta_shape',
            )
            mock_write_output.assert_called_once_with(
                self.mock_target_area,
                results,
                variable_name,
                output_path,
                expected_cache,
                {},
                mock_ordered_non_track_dim_objs,
            )

        with self.subTest('Pre-existing bilinear information'):
            mock_get_bil_info.reset_mock()
            mock_get_sample.reset_mock()
            mock_write_output.reset_mock()

            bilinear_information = {
                ('/lat', '/lon'): {
                    'vertical_distances': 'vertical_old',
                    'horizontal_distances': 'horizontal_old',
                    'valid_input_indices': 'input_indices_old',
                    'valid_point_mapping': 'point_mapping_old',
                    'target_area': self.mock_target_area,
                }
            }

            resample_variable(
                message_parameters,
                variable_name,
                bilinear_information,
                output_path,
                self.logger,
                self.var_info,
            )

            mock_get_bil_info.assert_not_called()
            mock_get_sample.assert_called_once_with(
                ravel_data,
                'vertical_old',
                'horizontal_old',
                'input_indices_old',
                'point_mapping_old',
                output_shape='ta_shape',
            )
            mock_write_output.assert_called_once_with(
                self.mock_target_area,
                results,
                variable_name,
                output_path,
                bilinear_information,
                {},
                mock_ordered_non_track_dim_objs,
            )

        with self.subTest('Harmony message defines target area'):
            mock_get_target_area.reset_mock()
            mock_get_bil_info.reset_mock()
            mock_get_sample.reset_mock()
            mock_write_output.reset_mock()

            harmony_target_area = MagicMock(
                spec=AreaDefinition, area_id=HARMONY_TARGET, shape='harmony_shape'
            )

            input_cache = {
                HARMONY_TARGET: {'target_area': harmony_target_area},
            }

            resample_variable(
                message_parameters,
                variable_name,
                input_cache,
                output_path,
                self.logger,
                self.var_info,
            )

            # Check that there is a new entry in the cache, and that it only
            # contains references to the original Harmony target area object,
            # not copies of those objects.
            expected_cache = {
                HARMONY_TARGET: {'target_area': harmony_target_area},
                ('/lat', '/lon'): {
                    'vertical_distances': 'vertical',
                    'horizontal_distances': 'horizontal',
                    'valid_input_indices': 'input_indices',
                    'valid_point_mapping': 'point_mapping',
                    'target_area': harmony_target_area,
                },
            }
            self.assertDictEqual(input_cache, expected_cache)

            mock_get_bil_info.assert_called_once_with(
                'swath', harmony_target_area, radius=50000, neighbours=16
            )
            mock_get_sample.assert_called_once_with(
                ravel_data,
                'vertical',
                'horizontal',
                'input_indices',
                'point_mapping',
                output_shape='harmony_shape',
            )

            # The Harmony target area should be given to the output function
            mock_write_output.assert_called_once_with(
                harmony_target_area,
                results,
                variable_name,
                output_path,
                expected_cache,
                {},
                mock_ordered_non_track_dim_objs,
            )
            mock_get_target_area.assert_not_called()

    @patch('swath_projector.interpolation.allocate_target_array')
    @patch('swath_projector.interpolation.get_preferred_ordered_dimensions_info')
    @patch('swath_projector.interpolation.write_single_band_output')
    @patch('swath_projector.interpolation.get_swath_definition')
    @patch('swath_projector.interpolation.get_target_area')
    @patch('swath_projector.interpolation.get_variable_values')
    @patch('swath_projector.interpolation.fornav')
    @patch('swath_projector.interpolation.ll2cr')
    def test_resample_ewa(
        self,
        mock_ll2cr,
        mock_fornav,
        mock_get_values,
        mock_get_target_area,
        mock_get_swath,
        mock_write_output,
        mock_get_preferred_ordered_dimensions_info,
        mock_allocate_target_array,
    ):
        """EWA interpolation should call both ll2cr and fornav if there are
        no matching entries for the coordinates in the reprojection
        information. If there is an entry, then only fornav should be
        called.

        """
        mock_ll2cr.return_value = ['swath_points_in_grid', 'columns', 'rows']
        results = np.array([6.0])
        mock_fornav.return_value = ('', results)
        mock_get_swath.return_value = 'swath'

        mock_values_data = np.ones((2, 3))
        mock_values = MagicMock()
        mock_values.__getitem__.return_value = mock_values_data
        mock_get_values.return_value = mock_values

        mock_get_target_area.return_value = self.mock_target_area

        mock_ordered_non_track_dim_objs = MagicMock()
        mock_get_preferred_ordered_dimensions_info.return_value = (
            None,
            mock_ordered_non_track_dim_objs,
        )

        message_parameters = self.message_parameters
        message_parameters['interpolation'] = 'ewa'
        variable_name = '/alpha_var'
        output_path = 'path/to/output'

        with self.subTest('No pre-existing EWA information'):
            resample_variable(
                message_parameters,
                variable_name,
                {},
                output_path,
                self.logger,
                self.var_info,
            )

            expected_cache = {
                ('/lat', '/lon'): {
                    'columns': 'columns',
                    'rows': 'rows',
                    'target_area': self.mock_target_area,
                }
            }

            mock_ll2cr.assert_called_once_with('swath', self.mock_target_area)
            mock_fornav.assert_called_once_with(
                'columns',
                'rows',
                self.mock_target_area,
                mock_values[:],
                maximum_weight_mode=False,
                rows_per_scan=2,  # Added in QuickFix DAS-2216 to be fixed in DAS-2220
            )
            mock_write_output.assert_called_once_with(
                self.mock_target_area,
                results,
                variable_name,
                output_path,
                expected_cache,
                {},
                mock_ordered_non_track_dim_objs,
            )

        with self.subTest('Pre-existing EWA information'):
            mock_ll2cr.reset_mock()
            mock_fornav.reset_mock()
            mock_write_output.reset_mock()

            ewa_information = {
                ('/lat', '/lon'): {
                    'columns': 'old_columns',
                    'rows': 'old_rows',
                    'target_area': self.mock_target_area,
                }
            }

            resample_variable(
                message_parameters,
                variable_name,
                ewa_information,
                output_path,
                self.logger,
                self.var_info,
            )

            mock_ll2cr.assert_not_called()
            mock_fornav.assert_called_once_with(
                'old_columns',
                'old_rows',
                self.mock_target_area,
                mock_values[:],
                maximum_weight_mode=False,
                rows_per_scan=2,  # Added in QuickFix DAS-2216 to be fixed in DAS-2220
            )
            mock_write_output.assert_called_once_with(
                self.mock_target_area,
                results,
                variable_name,
                output_path,
                ewa_information,
                {},
                mock_ordered_non_track_dim_objs,
            )

    @patch('swath_projector.interpolation.allocate_target_array')
    @patch('swath_projector.interpolation.get_preferred_ordered_dimensions_info')
    @patch('swath_projector.interpolation.write_single_band_output')
    @patch('swath_projector.interpolation.get_swath_definition')
    @patch('swath_projector.interpolation.get_target_area')
    @patch('swath_projector.interpolation.get_variable_values')
    @patch('swath_projector.interpolation.fornav')
    @patch('swath_projector.interpolation.ll2cr')
    def test_resample_ewa_nn(
        self,
        mock_ll2cr,
        mock_fornav,
        mock_get_values,
        mock_get_target_area,
        mock_get_swath,
        mock_write_output,
        mock_get_preferred_ordered_dimensions_info,
        mock_allocate_target_array,
    ):
        """EWA-NN interpolation should call both ll2cr and fornav if there are
        no matching entries for the coordinates in the reprojection
        information. If there is an entry, then only fornav should
        be called.
        """
        mock_ll2cr.return_value = ['swath_points_in_grid', 'columns', 'rows']
        results = np.array([5.0])
        mock_fornav.return_value = ('', results)
        mock_get_swath.return_value = 'swath'

        mock_values_data = np.ones((2, 3))
        mock_values = MagicMock()
        mock_values.__getitem__.return_value = mock_values_data
        mock_get_values.return_value = mock_values

        mock_get_target_area.return_value = self.mock_target_area

        mock_ordered_non_track_dim_objs = MagicMock()
        mock_get_preferred_ordered_dimensions_info.return_value = (
            None,
            mock_ordered_non_track_dim_objs,
        )

        message_parameters = self.message_parameters
        message_parameters['interpolation'] = 'ewa-nn'
        variable_name = '/alpha_var'
        output_path = 'path/to/output'

        with self.subTest('No pre-existing EWA-NN information'):
            resample_variable(
                message_parameters,
                variable_name,
                {},
                output_path,
                self.logger,
                self.var_info,
            )

            expected_cache = {
                ('/lat', '/lon'): {
                    'columns': 'columns',
                    'rows': 'rows',
                    'target_area': self.mock_target_area,
                }
            }

            mock_ll2cr.assert_called_once_with('swath', self.mock_target_area)
            mock_fornav.assert_called_once_with(
                'columns',
                'rows',
                self.mock_target_area,
                mock_values[:],
                maximum_weight_mode=True,
                rows_per_scan=2,  # Added in QuickFix DAS-2216 to be fixed in DAS-2220
            )
            mock_write_output.assert_called_once_with(
                self.mock_target_area,
                results,
                variable_name,
                output_path,
                expected_cache,
                {},
                mock_ordered_non_track_dim_objs,
            )

        with self.subTest('Pre-existing EWA-NN information'):
            mock_ll2cr.reset_mock()
            mock_fornav.reset_mock()
            mock_write_output.reset_mock()

            ewa_nn_information = {
                ('/lat', '/lon'): {
                    'columns': 'old_columns',
                    'rows': 'old_rows',
                    'target_area': self.mock_target_area,
                }
            }

            resample_variable(
                message_parameters,
                variable_name,
                ewa_nn_information,
                output_path,
                self.logger,
                self.var_info,
            )

            mock_ll2cr.assert_not_called()
            mock_fornav.assert_called_once_with(
                'old_columns',
                'old_rows',
                self.mock_target_area,
                mock_values[:],
                maximum_weight_mode=True,
                rows_per_scan=2,  # Added in QuickFix DAS-2216 to be fixed in DAS-2220
            )
            mock_write_output.assert_called_once_with(
                self.mock_target_area,
                results,
                variable_name,
                output_path,
                ewa_nn_information,
                {},
                mock_ordered_non_track_dim_objs,
            )

        with self.subTest('Harmony message defines target area'):
            mock_get_target_area.reset_mock()
            mock_ll2cr.reset_mock()
            mock_fornav.reset_mock()
            mock_write_output.reset_mock()

            harmony_target_area = MagicMock(
                spec=AreaDefinition, area_id=HARMONY_TARGET, shape='harmony_shape'
            )

            cache = {HARMONY_TARGET: {'target_area': harmony_target_area}}

            resample_variable(
                message_parameters,
                variable_name,
                cache,
                output_path,
                self.logger,
                self.var_info,
            )

            # Check that there is a new entry in the cache, and that it only
            # contains references to the original Harmony target area object,
            # not copies of those objects.
            expected_cache = {
                HARMONY_TARGET: {'target_area': harmony_target_area},
                ('/lat', '/lon'): {
                    'columns': 'columns',
                    'rows': 'rows',
                    'target_area': harmony_target_area,
                },
            }
            self.assertDictEqual(cache, expected_cache)

            mock_ll2cr.assert_called_once_with('swath', harmony_target_area)
            mock_fornav.assert_called_once_with(
                'columns',
                'rows',
                harmony_target_area,
                mock_values[:],
                maximum_weight_mode=True,
                rows_per_scan=2,  # Added in QuickFix DAS-2216 to be fixed in DAS-2220
            )

            # The Harmony target area should be given to the output function
            mock_write_output.assert_called_once_with(
                harmony_target_area,
                results,
                variable_name,
                output_path,
                expected_cache,
                {},
                mock_ordered_non_track_dim_objs,
            )
            mock_get_target_area.assert_not_called()

    @patch('swath_projector.interpolation.allocate_target_array')
    @patch('swath_projector.interpolation.get_preferred_ordered_dimensions_info')
    @patch('swath_projector.interpolation.write_single_band_output')
    @patch('swath_projector.interpolation.get_swath_definition')
    @patch('swath_projector.interpolation.get_target_area')
    @patch('swath_projector.interpolation.get_variable_values')
    @patch('swath_projector.interpolation.get_sample_from_neighbour_info')
    @patch('swath_projector.interpolation.get_neighbour_info')
    def test_resample_nearest(
        self,
        mock_get_info,
        mock_get_sample,
        mock_get_values,
        mock_get_target_area,
        mock_get_swath,
        mock_write_output,
        mock_get_preferred_ordered_dimensions_info,
        mock_allocate_target_array,
    ):
        """Nearest neighbour interpolation should call both get_neighbour_info
        and get_sample_from_neighbour_info if there are no matching entries
        for the coordinates in the reprojection information. If there is an
        entry, then only get_sample_from_neighbour_info should be called.

        """
        mock_get_info.return_value = [
            'valid_input_index',
            'valid_output_index',
            'index_array',
            'distance_array',
        ]
        results = np.array([4.0])
        mock_get_sample.return_value = results
        mock_get_swath.return_value = 'swath'

        mock_values_data = np.ones((2, 3))
        mock_values = MagicMock()
        mock_values.__getitem__.return_value = mock_values_data
        mock_get_values.return_value = mock_values

        mock_get_target_area.return_value = self.mock_target_area

        mock_ordered_non_track_dim_objs = MagicMock()
        mock_get_preferred_ordered_dimensions_info.return_value = (
            None,
            mock_ordered_non_track_dim_objs,
        )

        message_parameters = self.message_parameters
        message_parameters['interpolation'] = 'near'
        variable_name = '/alpha_var'
        output_path = 'path/to/output'
        alpha_var_fill = 0.0

        with self.subTest('No pre-existing nearest neighbour information'):
            resample_variable(
                message_parameters,
                variable_name,
                {},
                output_path,
                self.logger,
                self.var_info,
            )

            expected_cache = {
                ('/lat', '/lon'): {
                    'valid_input_index': 'valid_input_index',
                    'valid_output_index': 'valid_output_index',
                    'index_array': 'index_array',
                    'distance_array': 'distance_array',
                    'target_area': self.mock_target_area,
                }
            }

            mock_get_info.assert_called_once_with(
                'swath',
                self.mock_target_area,
                RADIUS_OF_INFLUENCE,
                epsilon=EPSILON,
                neighbours=1,
            )
            mock_get_sample.assert_called_once_with(
                'nn',
                'ta_shape',
                mock_values[:],
                'valid_input_index',
                'valid_output_index',
                'index_array',
                distance_array='distance_array',
                fill_value=alpha_var_fill,
            )
            mock_write_output.assert_called_once_with(
                self.mock_target_area,
                results,
                variable_name,
                output_path,
                expected_cache,
                {},
                mock_ordered_non_track_dim_objs,
            )

        with self.subTest('Pre-existing nearest neighbour information'):
            mock_get_info.reset_mock()
            mock_get_sample.reset_mock()
            mock_write_output.reset_mock()

            nearest_information = {
                ('/lat', '/lon'): {
                    'valid_input_index': 'old_valid_input',
                    'valid_output_index': 'old_valid_output',
                    'index_array': 'old_index_array',
                    'distance_array': 'old_distance',
                    'target_area': self.mock_target_area,
                }
            }

            resample_variable(
                message_parameters,
                variable_name,
                nearest_information,
                output_path,
                self.logger,
                self.var_info,
            )

            mock_get_info.assert_not_called()
            mock_get_sample.assert_called_once_with(
                'nn',
                'ta_shape',
                mock_values[:],
                'old_valid_input',
                'old_valid_output',
                'old_index_array',
                distance_array='old_distance',
                fill_value=alpha_var_fill,
            )
            mock_write_output.assert_called_once_with(
                self.mock_target_area,
                results,
                variable_name,
                output_path,
                nearest_information,
                {},
                mock_ordered_non_track_dim_objs,
            )

        with self.subTest('Harmony message defines target area'):
            mock_get_target_area.reset_mock()
            mock_get_info.reset_mock()
            mock_get_sample.reset_mock()
            mock_write_output.reset_mock()

            harmony_target_area = MagicMock(
                spec=AreaDefinition, area_id=HARMONY_TARGET, shape='harmony_shape'
            )

            cache = {HARMONY_TARGET: {'target_area': harmony_target_area}}

            resample_variable(
                message_parameters,
                variable_name,
                cache,
                output_path,
                self.logger,
                self.var_info,
            )

            # Check that there is a new entry in the cache, and that it only
            # contains references to the original Harmony target area object,
            # not copies of those objects.
            expected_cache = {
                HARMONY_TARGET: {'target_area': harmony_target_area},
                ('/lat', '/lon'): {
                    'valid_input_index': 'valid_input_index',
                    'valid_output_index': 'valid_output_index',
                    'index_array': 'index_array',
                    'distance_array': 'distance_array',
                    'target_area': harmony_target_area,
                },
            }

            self.assertDictEqual(cache, expected_cache)
            mock_get_target_area.assert_not_called()
            mock_get_info.assert_called_once_with(
                'swath',
                harmony_target_area,
                RADIUS_OF_INFLUENCE,
                epsilon=EPSILON,
                neighbours=1,
            )
            mock_get_sample.assert_called_once_with(
                'nn',
                'harmony_shape',
                mock_values[:],
                'valid_input_index',
                'valid_output_index',
                'index_array',
                distance_array='distance_array',
                fill_value=alpha_var_fill,
            )

            # The Harmony target area should be given to the output function
            mock_write_output.assert_called_once_with(
                harmony_target_area,
                results,
                variable_name,
                output_path,
                expected_cache,
                {},
                mock_ordered_non_track_dim_objs,
            )

    @patch('swath_projector.interpolation.allocate_target_array')
    @patch('swath_projector.interpolation.get_preferred_ordered_dimensions_info')
    @patch('swath_projector.interpolation.write_single_band_output')
    @patch('swath_projector.interpolation.get_swath_definition')
    @patch('swath_projector.interpolation.get_target_area')
    @patch('swath_projector.interpolation.get_variable_values')
    @patch('swath_projector.interpolation.get_sample_from_neighbour_info')
    @patch('swath_projector.interpolation.get_neighbour_info')
    def test_resample_scaled_variable(
        self,
        mock_get_info,
        mock_get_sample,
        mock_get_values,
        mock_get_target_area,
        mock_get_swath,
        mock_write_output,
        mock_get_preferred_ordered_dimensions_info,
        mock_allocate_target_array,
    ):
        """Ensure that an input variable that contains scaling attributes,
        `add_offset` and `scale_factor` passes those attributes to the
        function that writes the intermediate output, so that the variable
        in that dataset is also correctly scaled.

        """
        mock_get_info.return_value = [
            'valid_input_index',
            'valid_output_index',
            'index_array',
            'distance_array',
        ]
        results = np.array([4.0])
        mock_get_sample.return_value = results
        mock_get_swath.return_value = 'swath'

        mock_values_data = np.ones((2, 3))
        mock_values = MagicMock()
        mock_values.__getitem__.return_value = mock_values_data
        mock_get_values.return_value = mock_values

        mock_get_target_area.return_value = self.mock_target_area

        mock_ordered_non_track_dim_objs = MagicMock()
        mock_get_preferred_ordered_dimensions_info.return_value = (
            None,
            mock_ordered_non_track_dim_objs,
        )

        message_parameters = self.message_parameters
        message_parameters['interpolation'] = 'near'
        variable_name = '/blue_var'  # blue_var has scale and offset
        output_path = 'path/to/output'
        blue_var_fill = 0.0

        resample_variable(
            message_parameters,
            variable_name,
            {},
            output_path,
            self.logger,
            self.var_info,
        )

        expected_cache = {
            ('/lat', '/lon'): {
                'valid_input_index': 'valid_input_index',
                'valid_output_index': 'valid_output_index',
                'index_array': 'index_array',
                'distance_array': 'distance_array',
                'target_area': self.mock_target_area,
            }
        }
        expected_scaling = {'add_offset': 0, 'scale_factor': 2}

        mock_get_info.assert_called_once_with(
            'swath',
            self.mock_target_area,
            RADIUS_OF_INFLUENCE,
            epsilon=EPSILON,
            neighbours=1,
        )
        mock_get_sample.assert_called_once_with(
            'nn',
            'ta_shape',
            mock_values[:],
            'valid_input_index',
            'valid_output_index',
            'index_array',
            distance_array='distance_array',
            fill_value=blue_var_fill,
        )
        mock_write_output.assert_called_once_with(
            self.mock_target_area,
            results,
            variable_name,
            output_path,
            expected_cache,
            expected_scaling,
            mock_ordered_non_track_dim_objs,
        )

    def test_check_for_valid_interpolation(self):
        """Ensure all valid interpolations don't raise an exception."""
        interpolations = ['bilinear', 'ewa', 'ewa-nn', 'near']

        for interpolation in interpolations:
            with self.subTest(interpolation):
                parameters = {'interpolation': interpolation}
                check_for_valid_interpolation(parameters, self.logger)

        with self.subTest('Invalid interpolation'):
            with self.assertRaises(ValueError):
                parameters = {'interpolation': 'something else'}
                check_for_valid_interpolation(parameters, self.logger)

    def test_get_swath_definition(self):
        """Ensure a valid SwathDefinition object can be created for a dataset
        with coordinates. The shape of the swath definition should match
        the shapes of the input coordinates, and the longitude and latitude
        values should be correctly stored in the swath definition.

        """
        dataset = Dataset('tests/data/africa.nc')
        longitudes = dataset['/lon']
        latitudes = dataset['/lat']
        coordinates = ('/lat', '/lon')
        swath_definition = get_swath_definition(dataset, coordinates)

        self.assertEqual(swath_definition.shape, longitudes.shape)
        np.testing.assert_array_equal(longitudes, swath_definition.lons)
        np.testing.assert_array_equal(latitudes, swath_definition.lats)

    def test_get_swath_definition_wrapping_longitudes(self):
        """Ensure that a dataset with coordinates that have longitude ranging
        from 0 to 360 degrees will produce a valid SwathDefinition object,
        with the longitudes ranging from -180 degrees to 180 degrees.

        """
        dataset = Dataset('test.nc', 'w', diskless=True)

        lat_values = np.array([[20, 20], [10, 10]])
        raw_lon_values = np.array([[180, 190], [180, 190]])
        wrapped_lon_values = np.array([[-180, -170], [-180, -170]])

        dataset.createDimension('lat', size=2)
        dataset.createDimension('lon', size=2)
        dataset.createVariable('latitude', lat_values.dtype, dimensions=('lat', 'lon'))
        dataset.createVariable(
            'longitude', raw_lon_values.dtype, dimensions=('lat', 'lon')
        )
        dataset['longitude'][:] = raw_lon_values[:]
        dataset['latitude'][:] = lat_values[:]

        coordinates = ('/latitude', '/longitude')
        swath_definition = get_swath_definition(dataset, coordinates)

        self.assertEqual(swath_definition.shape, lat_values.shape)
        np.testing.assert_array_equal(lat_values, swath_definition.lats)
        np.testing.assert_array_equal(wrapped_lon_values, swath_definition.lons)
        dataset.close()

    def test_get_swath_definition_one_dimensional_coordinates(self):
        """Ensure that if 1-D coordinate arrays are used to produce a swath,
        they are converted to 2-D before being used to construct the
        object.

        """
        dataset = Dataset('test_1d.nc', 'w', diskless=True)

        lat_values = np.array([20, 15, 10])
        lon_values = np.array([150, 160, 170])
        lat_values_2d = np.array([[20], [15], [10]])
        lon_values_2d = np.array([[150], [160], [170]])

        dataset.createDimension('lat', size=3)
        dataset.createDimension('lon', size=3)
        dataset.createVariable('latitude', lat_values.dtype, dimensions=('lat',))
        dataset.createVariable('longitude', lon_values.dtype, dimensions=('lon',))
        dataset['longitude'][:] = lon_values[:]
        dataset['latitude'][:] = lat_values[:]

        coordinates = ('/latitude', '/longitude')
        swath_definition = get_swath_definition(dataset, coordinates)

        self.assertEqual(swath_definition.shape, (lat_values.size, 1))
        np.testing.assert_array_equal(lat_values_2d, swath_definition.lats)
        np.testing.assert_array_equal(lon_values_2d, swath_definition.lons)
        dataset.close()

    def test_get_reprojection_cache_minimal(self):
        """If a Harmony message does not contain any target area information,
        then an empty cache should be retrieved.

        """
        self.assertDictEqual(get_reprojection_cache(self.message_parameters), {})

    def test_get_cache_information_extents(self):
        """If a Harmony message defines the extents of a target area, but
        neither dimensions nor resolutions, then an empty cache should be
        retrieved.

        """
        message_parameters = self.message_parameters
        message_parameters['x_min'] = -10
        message_parameters['x_max'] = 10
        message_parameters['y_min'] = -5
        message_parameters['y_max'] = 5

        self.assertDictEqual(get_reprojection_cache(message_parameters), {})

    def test_get_reprojection_cache_extents_resolutions(self):
        """If a Harmony message defines the target area extents and
        resolutions, the returned cache should contain an entry that will
        be used for all variables.

        """
        message_parameters = self.message_parameters
        message_parameters['x_min'] = -10
        message_parameters['x_max'] = 10
        message_parameters['y_min'] = -5
        message_parameters['y_max'] = 5
        message_parameters['xres'] = 1
        message_parameters['yres'] = -1

        expected_target_area = AreaDefinition.from_extent(
            HARMONY_TARGET,
            message_parameters['projection'].definition_string(),
            (10, 20),
            (-10, -5, 10, 5),
        )

        cache = get_reprojection_cache(message_parameters)

        self.assertIn(HARMONY_TARGET, cache)
        self.assertSetEqual(set(cache[HARMONY_TARGET].keys()), {'target_area'})

        self.assert_areadefinitions_equal(
            cache[HARMONY_TARGET]['target_area'], expected_target_area
        )

    def test_get_reprojection_cache_extents_dimensions(self):
        """If the Harmony message defines the target area extents and
        dimensions, the returned cache should contain an entry that will be
        used for all variables.

        """
        message_parameters = self.message_parameters
        message_parameters['x_min'] = -10
        message_parameters['x_max'] = 10
        message_parameters['y_min'] = -5
        message_parameters['y_max'] = 5
        message_parameters['height'] = 10
        message_parameters['width'] = 20

        expected_target_area = AreaDefinition.from_extent(
            HARMONY_TARGET,
            message_parameters['projection'].definition_string(),
            (10, 20),
            (-10, -5, 10, 5),
        )

        cache = get_reprojection_cache(message_parameters)

        self.assertIn(HARMONY_TARGET, cache)
        self.assertSetEqual(set(cache[HARMONY_TARGET].keys()), {'target_area'})

        self.assert_areadefinitions_equal(
            cache[HARMONY_TARGET]['target_area'], expected_target_area
        )

    def test_get_reprojection_cache_dimensions(self):
        """If the Harmony message defines the target area dimensions, but not
        the extents, then the retrieved cache should be empty.

        """
        message_parameters = self.message_parameters
        message_parameters['height'] = 10
        message_parameters['width'] = 20

        self.assertDictEqual(get_reprojection_cache(message_parameters), {})

    def test_get_reprojection_cache_resolutions(self):
        """If the Harmony message defines the target area resolutions, but not
        the extents, then the retrieved cache should be empty.

        """
        message_parameters = self.message_parameters
        message_parameters['xres'] = 1
        message_parameters['yres'] = -1

        self.assertDictEqual(get_reprojection_cache(message_parameters), {})

    @patch('swath_projector.interpolation.get_projected_resolution')
    @patch('swath_projector.interpolation.get_extents_from_perimeter')
    @patch('swath_projector.interpolation.get_coordinate_data')
    def test_get_target_area_minimal(
        self, mock_get_coordinates, mock_get_extents, mock_get_resolution
    ):
        """If the Harmony message does not define a target area, then that
        information should be derived from the coordinate variables
        referred to in the variable metadata.

        Note: These unit tests are primarily to make sure the correct
        combinations of message and variable-specific parameters are being
        used. The full functional test comes from those in the main `test`
        directory.

        """
        latitudes = 'lats'
        longitudes = 'lons'
        mock_get_coordinates.side_effect = [latitudes, longitudes]
        mock_get_extents.return_value = (-20, 20, 0, 40)
        mock_get_resolution.return_value = 2.0

        # The dimensions are (20 - -20) / 2 = (40 - 0) / 2 = 20.
        expected_target_area = AreaDefinition.from_extent(
            '/lat, /lon',
            self.message_parameters['projection'].definition_string(),
            (20, 20),
            (-20, 0, 20, 40),
        )

        target_area = get_target_area(
            self.message_parameters, 'coordinate_group', ('/lat', '/lon'), self.logger
        )

        self.assertEqual(mock_get_coordinates.call_count, 2)
        mock_get_coordinates.assert_any_call(
            'coordinate_group', ('/lat', '/lon'), 'lat'
        )
        mock_get_coordinates.assert_any_call(
            'coordinate_group', ('/lat', '/lon'), 'lon'
        )
        mock_get_extents.assert_called_once_with(
            self.message_parameters['projection'], longitudes, latitudes
        )
        mock_get_resolution.assert_called_once_with(
            self.message_parameters['projection'], longitudes, latitudes
        )

        self.assert_areadefinitions_equal(target_area, expected_target_area)

    @patch('swath_projector.interpolation.get_projected_resolution')
    @patch('swath_projector.interpolation.get_extents_from_perimeter')
    @patch('swath_projector.interpolation.get_coordinate_data')
    def test_get_target_area_extents(
        self, mock_get_coordinates, mock_get_extents, mock_get_resolution
    ):
        """If the Harmony message defines the target area extents, these
        should be used, with the dimensions and resolution of the output
        being defined by the coordinate data from the variable.

        """
        latitudes = 'lats'
        longitudes = 'lons'
        mock_get_coordinates.side_effect = [latitudes, longitudes]
        mock_get_extents.return_value = (-20, 20, 0, 40)
        mock_get_resolution.return_value = 2.0

        message_parameters = self.message_parameters
        message_parameters['x_min'] = -10
        message_parameters['x_max'] = 10
        message_parameters['y_min'] = -5
        message_parameters['y_max'] = 5

        # The dimensions are x = (10 - -10) / 2 = 10, y = (5 - -5) / 2 = 5
        expected_target_area = AreaDefinition.from_extent(
            '/lat, /lon',
            self.message_parameters['projection'].definition_string(),
            (5, 10),
            (-10, -5, 10, 5),
        )

        target_area = get_target_area(
            self.message_parameters, 'coordinate_group', ('/lat', '/lon'), self.logger
        )

        self.assertEqual(mock_get_coordinates.call_count, 2)
        mock_get_coordinates.assert_any_call(
            'coordinate_group', ('/lat', '/lon'), 'lat'
        )
        mock_get_coordinates.assert_any_call(
            'coordinate_group', ('/lat', '/lon'), 'lon'
        )
        mock_get_extents.assert_not_called()
        mock_get_resolution.assert_called_once_with(
            self.message_parameters['projection'], longitudes, latitudes
        )

        self.assert_areadefinitions_equal(target_area, expected_target_area)

    @patch('swath_projector.interpolation.get_projected_resolution')
    @patch('swath_projector.interpolation.get_extents_from_perimeter')
    @patch('swath_projector.interpolation.get_coordinate_data')
    def test_get_target_area_extents_resolutions(
        self, mock_get_coordinates, mock_get_extents, mock_get_resolution
    ):
        """If the Harmony message defines the target area extents and
        resolutions, these should be used for the target area definition.
        Note, this shouldn't happen in practice, as it should result in a
        global definition being defined when the reprojection cache is
        instantiated.

        """
        latitudes = 'lats'
        longitudes = 'lons'
        mock_get_coordinates.side_effect = [latitudes, longitudes]
        mock_get_extents.return_value = (-20, 20, 0, 40)
        mock_get_resolution.return_value = 2.0

        message_parameters = self.message_parameters
        message_parameters['x_min'] = -10
        message_parameters['x_max'] = 10
        message_parameters['y_min'] = -5
        message_parameters['y_max'] = 5
        message_parameters['xres'] = 1
        message_parameters['yres'] = -1

        # The dimensions are x = (10 - -10) / 1 = 20, y = (5 - -5) / 1 = 10
        expected_target_area = AreaDefinition.from_extent(
            '/lat, /lon',
            self.message_parameters['projection'].definition_string(),
            (10, 20),
            (-10, -5, 10, 5),
        )

        target_area = get_target_area(
            self.message_parameters, 'coordinate_group', ('/lat', '/lon'), self.logger
        )

        self.assertEqual(mock_get_coordinates.call_count, 2)
        mock_get_coordinates.assert_any_call(
            'coordinate_group', ('/lat', '/lon'), 'lat'
        )
        mock_get_coordinates.assert_any_call(
            'coordinate_group', ('/lat', '/lon'), 'lon'
        )
        mock_get_extents.assert_not_called()
        mock_get_resolution.assert_not_called()

        self.assert_areadefinitions_equal(target_area, expected_target_area)

    @patch('swath_projector.interpolation.get_projected_resolution')
    @patch('swath_projector.interpolation.get_extents_from_perimeter')
    @patch('swath_projector.interpolation.get_coordinate_data')
    def test_get_target_area_extents_dimensions(
        self, mock_get_coordinates, mock_get_extents, mock_get_resolution
    ):
        """If the Harmony message defines the target area extents and
        dimensions, these should be used for the target area definition.
        Note, this shouldn't happen in practice, as it should result in a
        global definition being defined when the reprojection cache is
        instantiated.

        """
        latitudes = 'lats'
        longitudes = 'lons'
        mock_get_coordinates.side_effect = [latitudes, longitudes]
        mock_get_extents.return_value = (-20, 20, 0, 40)
        mock_get_resolution.return_value = 2.0

        message_parameters = self.message_parameters
        message_parameters['x_min'] = -10
        message_parameters['x_max'] = 10
        message_parameters['y_min'] = -5
        message_parameters['y_max'] = 5
        message_parameters['height'] = 10
        message_parameters['width'] = 10

        expected_target_area = AreaDefinition.from_extent(
            '/lat, /lon',
            self.message_parameters['projection'].definition_string(),
            (10, 10),
            (-10, -5, 10, 5),
        )

        target_area = get_target_area(
            self.message_parameters, 'coordinate_group', ('/lat', '/lon'), self.logger
        )

        self.assertEqual(mock_get_coordinates.call_count, 2)
        mock_get_coordinates.assert_any_call(
            'coordinate_group', ('/lat', '/lon'), 'lat'
        )
        mock_get_coordinates.assert_any_call(
            'coordinate_group', ('/lat', '/lon'), 'lon'
        )
        mock_get_extents.assert_not_called()
        mock_get_resolution.assert_not_called()

        self.assert_areadefinitions_equal(target_area, expected_target_area)

    @patch('swath_projector.interpolation.get_projected_resolution')
    @patch('swath_projector.interpolation.get_extents_from_perimeter')
    @patch('swath_projector.interpolation.get_coordinate_data')
    def test_get_target_area_dimensions(
        self, mock_get_coordinates, mock_get_extents, mock_get_resolution
    ):
        """If the Harmony message defines the target area dimensions, then
        that information should be used, along with the extents as
        defined by the variables associated coordinates.

        """
        latitudes = 'lats'
        longitudes = 'lons'
        mock_get_coordinates.side_effect = [latitudes, longitudes]
        mock_get_extents.return_value = (-20, 20, 0, 40)
        mock_get_resolution.return_value = 4.0

        message_parameters = self.message_parameters
        message_parameters['height'] = 10
        message_parameters['width'] = 10

        expected_target_area = AreaDefinition.from_extent(
            '/lat, /lon',
            self.message_parameters['projection'].definition_string(),
            (10, 10),
            (-20, 0, 20, 40),
        )

        target_area = get_target_area(
            self.message_parameters, 'coordinate_group', ('/lat', '/lon'), self.logger
        )

        self.assertEqual(mock_get_coordinates.call_count, 2)
        mock_get_coordinates.assert_any_call(
            'coordinate_group', ('/lat', '/lon'), 'lat'
        )
        mock_get_coordinates.assert_any_call(
            'coordinate_group', ('/lat', '/lon'), 'lon'
        )
        mock_get_extents.assert_called_once_with(
            message_parameters['projection'], longitudes, latitudes
        )
        mock_get_resolution.assert_not_called()

        self.assert_areadefinitions_equal(target_area, expected_target_area)

    @patch('swath_projector.interpolation.get_projected_resolution')
    @patch('swath_projector.interpolation.get_extents_from_perimeter')
    @patch('swath_projector.interpolation.get_coordinate_data')
    def test_get_target_area_resolutions(
        self, mock_get_coordinates, mock_get_extents, mock_get_resolution
    ):
        """If the Harmony message defines the target area resolutions, then
        that information should be used, along with the extents as
        defined by the variables associated coordinates.

        """
        latitudes = 'lats'
        longitudes = 'lons'
        mock_get_coordinates.side_effect = [latitudes, longitudes]
        mock_get_extents.return_value = (-20, 20, 0, 40)
        mock_get_resolution.return_value = 2.0

        message_parameters = self.message_parameters
        message_parameters['xres'] = 4
        message_parameters['yres'] = -5

        # The dimensions are (20 - -20) / 4 = (40 - 0) / 5 = 8
        expected_target_area = AreaDefinition.from_extent(
            '/lat, /lon',
            self.message_parameters['projection'].definition_string(),
            (8, 10),
            (-20, 0, 20, 40),
        )

        target_area = get_target_area(
            self.message_parameters, 'coordinate_group', ('/lat', '/lon'), self.logger
        )

        self.assertEqual(mock_get_coordinates.call_count, 2)
        mock_get_coordinates.assert_any_call(
            'coordinate_group', ('/lat', '/lon'), 'lat'
        )
        mock_get_coordinates.assert_any_call(
            'coordinate_group', ('/lat', '/lon'), 'lon'
        )
        mock_get_extents.assert_called_once_with(
            message_parameters['projection'], longitudes, latitudes
        )
        mock_get_resolution.assert_not_called()

        self.assert_areadefinitions_equal(target_area, expected_target_area)

    def test_get_parameters_tuple(self):
        """Ensure that the function behaves correctly when all, some or none
        of the requested parameters are not `None` in the input dictionary.

        If any of the requested parameters are `None`, then the function
        should return `None`. Otherwise a tuple of the corresponding values
        will be returned, in the requested order.

        """
        input_parameters = {'a': 1, 'b': 2, 'c': None}

        test_args = [
            ['All valid', ['a', 'b'], (1, 2)],
            ['Some valid', ['a', 'b', 'c'], None],
            ['None valid', ['c'], None],
        ]

        for description, keys, expected_output in test_args:
            with self.subTest(description):
                self.assertEqual(
                    get_parameters_tuple(input_parameters, keys), expected_output
                )

    @patch('swath_projector.interpolation.resample_layer')
    def test_resample_variable_data(self, mock_resample_layer):
        """Test the recursive resampling of n-dimensional variables"""
        resampler = Mock()

        with self.subTest("2D variable resampling"):
            s_var_2d = np.ones((1, 2))
            t_var_2d = np.empty((2, 4))
            mock_resample_layer.return_value = np.ones((2, 4))
            expected_2d = np.ones((2, 4))
            results = resample_variable_data(s_var_2d, t_var_2d, -9999, {}, resampler)
            np.testing.assert_array_equal(expected_2d, results)

        with self.subTest("3D variable resampling"):
            s_var_3d = np.ones((2, 1, 2))
            t_var_3d = np.empty((2, 2, 4))
            layer_values = [1, 2]
            mock_resample_layer.side_effect = [
                np.ones((2, 4)) * val for val in layer_values
            ]
            expected_3d = np.stack(
                [
                    np.ones((2, 4)) * 1,
                    np.ones((2, 4)) * 2,
                ]
            )
            results = resample_variable_data(s_var_3d, t_var_3d, -9999, {}, resampler)
            np.testing.assert_array_equal(expected_3d, results)

        with self.subTest("4D variable resampling"):
            s_var_4d = np.ones((3, 2, 1, 2))
            t_var_4d = np.empty((3, 2, 2, 4))
            layer_values = [1, 2, 3, 4, 5, 6]
            mock_resample_layer.side_effect = [
                np.ones((2, 4)) * val for val in layer_values
            ]
            expected_4d = np.stack(
                [
                    np.stack(
                        [
                            np.ones((2, 4)) * 1,
                            np.ones((2, 4)) * 2,
                        ]
                    ),
                    np.stack(
                        [
                            np.ones((2, 4)) * 3,
                            np.ones((2, 4)) * 4,
                        ]
                    ),
                    np.stack(
                        [
                            np.ones((2, 4)) * 5,
                            np.ones((2, 4)) * 6,
                        ]
                    ),
                ]
            )
            results = resample_variable_data(s_var_4d, t_var_4d, -9999, {}, resampler)
            np.testing.assert_array_equal(expected_4d, results)

    def test_resample_layer(self):
        """Ensure that the resample is called with the correct parameters"""
        # Example input data.
        source_layer = np.array([[1, 2], [3, 4]])
        fill_value = -9999
        reprojection_information = {'target_shape': (3, 3)}

        mocked_resample_result = np.array([[1, 2, 3], [4, 5, 6], [7, 8, 9]])
        mock_resampler = Mock(return_value=mocked_resample_result)
        result = resample_layer(
            source_layer, fill_value, reprojection_information, mock_resampler
        )
        mock_resampler.assert_called_once_with(
            {'values': source_layer, 'fill_value': fill_value},
            reprojection_information,
        )
        np.testing.assert_array_equal(result, mocked_resample_result)

    def test_allocate_target_array(self):
        """Ensure the target array is returned in the correct shape and datatype"""

        dim1 = Mock(spec=Dimension, size=5)
        dim2 = Mock(spec=Dimension, size=10)

        non_track_dims = [dim1, dim2]
        target_area_shape = (2, 3)
        dtype = np.float32

        result = allocate_target_array(non_track_dims, target_area_shape, dtype)
        self.assertIsInstance(result, np.ndarray)
        self.assertEqual(result.dtype, np.float32)
        self.assertTupleEqual(result.shape, (5, 10, 2, 3))
