from unittest import TestCase
from unittest.mock import MagicMock, Mock

import numpy as np
from netCDF4 import Dataset, Variable
from varinfo import VarInfoFromNetCDF4

from swath_projector.exceptions import MissingCoordinatesError
from swath_projector.utilities import (
    apply_fill,
    construct_absolute_path,
    coordinate_requires_transpose,
    create_coordinates_key,
    get_axes_permutation,
    get_coordinate_data,
    get_coordinate_matching_substring,
    get_ordered_track_dims,
    get_preferred_ordered_dimensions_info,
    get_rows_per_scan,
    get_scale_and_offset,
    get_variable_file_path,
    get_variable_numeric_fill_value,
    get_variable_values,
    make_array_two_dimensional,
    qualify_reference,
    variable_in_dataset,
)


class TestUtilities(TestCase):

    def test_create_coordinates_key(self):
        """Extract the coordinates from a `VariableFromNetCDF4` instance and
        return an alphabetically sorted tuple. The ordering prevents any
        shuffling due to earthdata-varinfo storing CF-Convention attribute
        references as a Python Set.

        """
        data = np.ones((2, 4))
        dimensions = ('lat', 'lon')
        expected_output = ('/lat', '/lon')

        test_args = [['comma-space', ['/lon, /lat']], ['reverse order', ['/lat, /lon']]]

        for description, coordinates in test_args:
            with self.subTest(description):
                with Dataset('test.nc', 'w') as dataset:
                    dataset.createDimension('lat', size=2)
                    dataset.createDimension('lon', size=4)

                    nc4_variable = dataset.createVariable(
                        '/group/variable', data.dtype, dimensions=dimensions
                    )
                    dataset.createVariable('/lat', data.dtype, dimensions=dimensions)
                    dataset.createVariable('/lon', data.dtype, dimensions=dimensions)

                    nc4_variable.setncattr('coordinates', coordinates)

                varinfo = VarInfoFromNetCDF4('test.nc')
                varinfo_variable = varinfo.get_variable('/group/variable')
                self.assertEqual(
                    create_coordinates_key(varinfo_variable), expected_output
                )

    def test_get_variable_values(self):
        """Ensure values for a variable are retrieved and transposed if the provided
        dimension order requires it.

        """

        with self.subTest('Masked values are set to fill value.'):
            fill_value = 210
            input_data = np.array([[220, 210], [240, 234]])

            with Dataset('mock_data.nc', 'w', diskless=True) as dataset:
                dataset.createDimension('y', size=2)
                dataset.createDimension('x', size=2)
                dataset.createVariable(
                    'data', np.uint8, dimensions=('y', 'x'), fill_value=fill_value
                )
                dataset['data'][:] = input_data

                # Ensure the raw variable data is masked in the expected cell.
                self.assertTrue(dataset['data'][:].mask[0, 1])

                returned_data = get_variable_values(
                    dataset['data'], fill_value, dataset['data'].dimensions
                )

                # Check the output is an array, not a masked array.
                self.assertIsInstance(returned_data, np.ndarray)
                # Check the output matches all the input data
                np.testing.assert_array_equal(input_data, returned_data)

        with self.subTest('2-D variable, no reordering required'):
            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dataset.createDimension('mirror_step', size=3)
                dataset.createDimension('xtrack', size=2)
                input_data = np.ones((3, 2))
                variable = dataset.createVariable(
                    'data', input_data.dtype, dimensions=('mirror_step', 'xtrack')
                )
                variable[:] = input_data[:]

                reordered_dims = ('mirror_step', 'xtrack')
                returned_data = get_variable_values(variable, None, reordered_dims)

                self.assertIsInstance(returned_data, np.ndarray)
                self.assertEqual(returned_data.shape, (3, 2))

        with self.subTest('2-D variable, reordering required'):
            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dataset.createDimension('mirror_step', size=2)
                dataset.createDimension('xtrack', size=3)
                input_data = np.ones((2, 3))
                variable = dataset.createVariable(
                    'data',
                    input_data.dtype,
                    dimensions=('mirror_step', 'xtrack'),
                )
                variable[:] = input_data[:]

                reordered_dims = ('xtrack', 'mirror_step')
                returned_data = get_variable_values(variable, None, reordered_dims)

                self.assertIsInstance(returned_data, np.ndarray)
                self.assertEqual(returned_data.shape, (3, 2))

        with self.subTest('3-D variable, no reordering required'):
            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dataset.createDimension('mirror_step', size=2)
                dataset.createDimension('xtrack', size=3)
                dataset.createDimension('layer', size=5)
                input_data = np.ones((5, 3, 2))
                variable = dataset.createVariable(
                    'data',
                    input_data.dtype,
                    dimensions=('layer', 'xtrack', 'mirror_step'),
                )
                variable[:] = input_data[:]

                reordered_dims = ('layer', 'xtrack', 'mirror_step')
                returned_data = get_variable_values(variable, None, reordered_dims)

                self.assertIsInstance(returned_data, np.ndarray)
                self.assertEqual(returned_data.shape, (5, 3, 2))

        with self.subTest('3-D variable, reordering required'):
            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dataset.createDimension('mirror_step', size=2)
                dataset.createDimension('xtrack', size=3)
                dataset.createDimension('layer', size=5)
                input_data = np.ones((2, 3, 5))
                variable = dataset.createVariable(
                    'data',
                    input_data.dtype,
                    dimensions=('mirror_step', 'xtrack', 'layer'),
                )
                variable[:] = input_data[:]

                reordered_dims = ('layer', 'xtrack', 'mirror_step')
                returned_data = get_variable_values(variable, None, reordered_dims)

                self.assertIsInstance(returned_data, np.ndarray)
                self.assertEqual(returned_data.shape, (5, 3, 2))

    def test_apply_fill(self):
        """Ensure fill is applied correctly based on the given data type."""
        test_args = [
            ["float16", np.float64],
            ["float32", np.float64],
            ["float64", np.float64],
            ["int8", np.int8],
            ["int16", np.int16],
            ["int32", np.int32],
        ]
        test_fill_value = 2
        for description, dtype in test_args:
            with self.subTest(description):
                variable_data = np.ma.array(
                    [1, 2, 3],
                    mask=[False, True, False],
                    fill_value=test_fill_value,
                    dtype=dtype,
                )
                result = apply_fill(variable_data, test_fill_value)

                self.assertIsInstance(result, np.ndarray)
                self.assertFalse(isinstance(result, np.ma.MaskedArray))

                # Unmasked values
                self.assertEqual(result[0], 1)
                self.assertEqual(result[2], 3)

                # Masked value filled correctly
                if dtype == np.float64:
                    self.assertTrue(np.isnan(result[1]))
                else:
                    self.assertEqual(result[1], test_fill_value)

        with self.subTest("Given fill value is applied for Float-32"):
            pass

        with self.subTest("Given fill value is applied for Integer t"):
            pass

    def test_get_coordinate_matching_substring(self):
        """Ensure the longitude or latitude coordinate variable, is retrieved
        when requested.

        """
        dataset = Dataset('tests/data/africa.nc')
        coordinates_tuple = ['lat', 'lon']

        for coordinate in coordinates_tuple:
            with self.subTest(coordinate):
                coordinates = get_coordinate_matching_substring(
                    dataset, coordinates_tuple, coordinate
                )

                self.assertIsInstance(coordinates, Variable)

        with self.subTest(
            'Non existent coordinate variable "latitude" returns MissingCoordinatesError'
        ):
            absent_coordinates_tuple = ['latitude']
            with self.assertRaises(MissingCoordinatesError):
                coordinates = get_coordinate_matching_substring(
                    dataset, absent_coordinates_tuple, absent_coordinates_tuple[0]
                )

    def test_get_variable_numeric_fill_value(self):
        """Ensure a fill value is retrieved from a variable that has a vaild
        numeric value, and is cast as either an integer or a float. If no
        fill value is present on the variable, or the fill value is non-
        numeric, the function should return None. This is because
        pyresample explicitly checks for float or int fill values in
        get_sample_from_neighbour_info.

        """
        variable = Mock(spec=Variable)

        test_args = [
            ['np.float128', np.float128, 4.0, 4.0],
            ['np.float16', np.float16, 4.0, 4.0],
            ['np.float32', np.float32, 4.0, 4.0],
            ['np.float64', np.float64, 4.0, 4.0],
            ['np.float_', np.float_, 4.0, 4.0],
            ['int', int, 5, 5],
            ['np.int0', np.int0, 5, 5],
            ['np.int16', np.int16, 5, 5],
            ['np.int32', np.int32, 5, 5],
            ['np.int64', np.int64, 5, 5],
            ['np.int8', np.int8, 5, 5],
            ['np.uint', np.uint, 5, 5],
            ['np.uint0', np.uint0, 5, 5],
            ['np.uint16', np.uint16, 5, 5],
            ['np.uint32', np.uint32, 5, 5],
            ['np.uint64', np.uint64, 5, 5],
            ['np.uint8', np.uint8, 5, 5],
            ['np.uintc', np.uintc, 5, 5],
            ['np.uintp', np.uintp, 5, 5],
            ['np.longlong', np.longlong, 5, 5],
            ['float', float, 4.0, 4.0],
            ['int', int, 5, 5],
            ['str', str, '1235', None],
        ]

        for description, caster, fill_value, expected_output in test_args:
            with self.subTest(description):
                variable.ncattrs.return_value = ['_FillValue']
                variable.getncattr.return_value = caster(fill_value)
                self.assertEqual(
                    get_variable_numeric_fill_value(variable), expected_output
                )

        with self.subTest('Missing fill value attribute returns `None`.'):
            variable.ncattrs.return_value = ['other_attribute']
            self.assertEqual(get_variable_numeric_fill_value(variable), None)

        with self.subTest('Variable with fill value is scaled.'):
            raw_fill_value = 1
            add_offset = 210
            scale_factor = 2
            variable.ncattrs.return_value = ['add_offset', '_FillValue', 'scale_factor']
            variable.getncattr.side_effect = [raw_fill_value, add_offset, scale_factor]

            self.assertEqual(get_variable_numeric_fill_value(variable), 212)

    def test_get_variable_file_path(self):
        """Ensure that a file path is correctly constructed from a variable
        name. This should also handle a variable within a group, not just
        at the root level of the dataset.

        """
        temporary_directory = '/tmp_dir'
        file_extension = '.nc'

        test_args = [
            ['Root variable', 'var_one', '/tmp_dir/var_one.nc'],
            ['Nested variable', '/group/var_two', '/tmp_dir/group_var_two.nc'],
        ]

        for description, variable_name, expected_path in test_args:
            with self.subTest(description):
                variable_path = get_variable_file_path(
                    temporary_directory, variable_name, file_extension
                )
            self.assertEqual(variable_path, expected_path)

    def test_get_scale_and_offset(self):
        """Ensure that the scaling attributes can be correctly returned from
        the input variable attributes, or an empty dictionary if both
        add_offset` and `scale_factor` are not present.

        """
        variable = Mock(spec=Variable)
        false_tests = [
            ['Neither attribute present.', {'other_key': 123}],
            ['Only scale_factor is present.', {'scale_factor': 0.01}],
            ['Only add_offset is present.', {'add_offset': 123.456}],
        ]

        for description, attributes in false_tests:
            variable.ncattrs.return_value = set(attributes.keys())
            with self.subTest(description):
                self.assertDictEqual(get_scale_and_offset(variable), {})

                variable.getncattr.assert_not_called()

        with self.subTest('Contains both required attributes'):
            attributes = {
                'add_offset': 123.456,
                'scale_factor': 0.01,
                'other_key': 'abc',
            }

            variable.ncattrs.return_value = set(attributes.keys())
            variable.getncattr.side_effect = [123.456, 0.01]
            self.assertDictEqual(
                get_scale_and_offset(variable),
                {'add_offset': 123.456, 'scale_factor': 0.01},
            )

    def test_construct_absolute_path(self):
        """Ensure that an absolute path can be constructed from a relative one
        and the supplied group path.

        """
        test_args = [
            ['Reference in group', 'variable', '/group', '/group/variable'],
            ['Reference in parent', '../variable', '/group', '/variable'],
            ['Reference in grandparent', '../../var', '/g1/g2', '/var'],
        ]

        for description, reference, group_path, abs_reference in test_args:
            with self.subTest(description):
                self.assertEqual(
                    construct_absolute_path(reference, group_path), abs_reference
                )

    def test_qualify_reference(self):
        """Ensure that a reference within a variable's metadata is correctly
        qualified to an absolute variable path, using the nature of the
        reference (e.g. prefix of "../" or "./") and the group of the
        referee variable.

        """
        dataset = Dataset('test.nc', 'w', diskless=True)
        dataset.createDimension('lat', size=2)
        dataset.createDimension('lon', size=4)

        data = np.ones((2, 4))
        variable = dataset.createVariable(
            '/group/variable', data.dtype, dimensions=('lat', 'lon')
        )

        dataset.createVariable('/group/sibling', data.dtype, dimensions=('lat', 'lon'))

        test_args = [
            ['In /group/variable, ref /base_var', '/base_var', '/base_var'],
            ['In /group/variable, ref ../base_var', '../base_var', '/base_var'],
            ['In /group/variable, ref ./group_var', './group_var', '/group/group_var'],
            ['In /group/variable, ref sibling', 'sibling', '/group/sibling'],
            ['In /group/variable, ref non-sibling', 'non_sibling', '/non_sibling'],
        ]

        for description, raw_reference, absolute_reference in test_args:
            with self.subTest(description):
                self.assertEqual(
                    qualify_reference(raw_reference, variable), absolute_reference
                )

        dataset.close()

    def test_variable_in_dataset(self):
        """Ensure that a variable will be correctly identified as belonging
        to the dataset. Also, the function should successfully handle
        absent intervening groups.

        """
        dataset = Dataset('test.nc', 'w', diskless=True)
        dataset.createDimension('lat', size=2)
        dataset.createDimension('lon', size=4)

        data = np.ones((2, 4))

        dataset.createVariable('/group/variable', data.dtype, dimensions=('lat', 'lon'))
        dataset.createVariable(
            '/group/group_two/variable_two', data.dtype, dimensions=('lat', 'lon')
        )
        dataset.createVariable('/base_variable', data.dtype, dimensions=('lat', 'lon'))

        test_args = [
            ['Root variable', '/base_variable', True],
            ['Root variable, no leading slash', 'base_variable', True],
            ['Singly nested variable', '/group/variable', True],
            ['Doubly nested variable', '/group/group_two/variable_two', True],
            ['Non existant base variable', '/missing', False],
            ['Non existant nested variable', '/group/missing', False],
            ['Non existant group', '/group_three/variable', False],
            ['Over nested variable', '/group/group_two/group_three/var', False],
        ]

        for description, variable_name, expected_result in test_args:
            with self.subTest(description):
                self.assertEqual(
                    variable_in_dataset(variable_name, dataset), expected_result
                )

        dataset.close()

    def test_make_array_two_dimensional(self):
        """Ensure a 1-D array is expaned to be a 2-D array with elements all
        in the same column,

        """
        input_array = np.array([1, 2, 3])
        expected_output = np.array([[1], [2], [3]])
        output_array = make_array_two_dimensional(input_array)

        self.assertEqual(len(output_array.shape), 2)
        np.testing.assert_array_equal(output_array, expected_output)

    def test_coordinate_requires_transpose(self):
        """Ensure correct determination of when a coordinate requires transposition"""

        test_args = [
            ['Tall swath (no transpose)', (10, 5), False],
            ['Wide swath (needs transpose)', (5, 10), True],
            ['Square swath (no transpose)', (5, 5), False],
        ]

        for description, shape, expected_result in test_args:
            with self.subTest(description):
                mock_coordinate = MagicMock()
                mock_coordinate.shape = shape
                self.assertEqual(
                    coordinate_requires_transpose(mock_coordinate), expected_result
                )
        return

    def test_get_axes_permutation(self):
        """Ensure that axis permutations are computed correctly when reordering dimensions"""
        test_args = [
            [
                'simple reordering',
                ('xtrack', 'mirror_step', 'layer'),
                ('layer', 'xtrack', 'mirror_step'),
                [2, 0, 1],
            ],
            [
                'no reorder',
                ('xtrack', 'mirror_step', 'layer'),
                ('xtrack', 'mirror_step', 'layer'),
                [0, 1, 2],
            ],
            [
                'includes duplicate dimension',
                ('xtrack', 'mirror_step', 'layer', 'layer'),
                ('layer', 'layer', 'xtrack', 'mirror_step'),
                [2, 3, 0, 1],
            ],
        ]

        for description, old_dims, new_dims, expected_result in test_args:
            with self.subTest(description):
                self.assertEqual(
                    get_axes_permutation(old_dims, new_dims), expected_result
                )

    def test_get_coordinate_data(self):
        """Ensure coordinate data can be retrieved and is transposed when required."""

        with self.subTest('2D coordinate, transpose not required'):
            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dataset.createDimension('xtrack', size=3)
                dataset.createDimension('mirror_step', size=2)
                lat_var = dataset.createVariable(
                    'latitude', float, ('xtrack', 'mirror_step')
                )
                lat_var[:] = np.ones((3, 2))

                expected_data = lat_var[:]
                result = get_coordinate_data(dataset, ('latitude',), 'lat')
                np.testing.assert_array_equal(result, expected_data)

        with self.subTest('2D coordinate, transpose required'):
            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dataset.createDimension('xtrack', size=2)
                dataset.createDimension('mirror_step', size=3)
                lat_var = dataset.createVariable(
                    'latitude', float, ('xtrack', 'mirror_step')
                )
                lat_var[:] = np.ones((2, 3))

                expected_data = np.ma.transpose(lat_var[:])
                result = get_coordinate_data(dataset, ('latitude',), 'lat')
                np.testing.assert_array_equal(result, expected_data)

    def test_get_ordered_track_dims(self):
        """Ensure track dimensions are returned in the correct order depending on
        whether transpose is required, and errors are raised for invalid shapes"""

        with self.subTest('transpose required'):
            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dataset.createDimension('mirror_step', size=2)
                dataset.createDimension('xtrack', size=3)
                dataset.createDimension('time', size=5)
                values = np.ones((2, 3))
                dims = ('mirror_step', 'xtrack')
                var = dataset.createVariable('/test-coordinate', float, dimensions=dims)
                var[:] = values
                expected_results = ('xtrack', 'mirror_step')
                results = get_ordered_track_dims(var)
                self.assertEqual(results, expected_results)

        with self.subTest('transpose not required'):
            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dataset.createDimension('mirror_step', size=3)
                dataset.createDimension('xtrack', size=2)
                dataset.createDimension('time', size=5)
                values = np.ones((3, 2))
                dims = ('mirror_step', 'xtrack')
                var = dataset.createVariable('/test-coordinate', float, dimensions=dims)
                var[:] = values
                expected_results = ('mirror_step', 'xtrack')
                results = get_ordered_track_dims(var)
                self.assertEqual(results, expected_results)

        with self.subTest('invalid number of dimensions'):
            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dataset.createDimension('mirror_step', size=3)
                dataset.createDimension('xtrack', size=2)
                dataset.createDimension('time', size=5)
                values = np.ones((3,))
                dims = 'mirror_step'
                var = dataset.createVariable('/test-coordinate', float, dimensions=dims)
                var[:] = values
                with self.assertRaises(Exception):
                    get_ordered_track_dims(var)

    def test_get_preferred_ordered_dimensions_info(self):
        """Ensure variable dimensions are reordered correctly."""
        with self.subTest('correct order track dims, no non-track dims'):
            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dataset.createDimension('xtrack', 3)
                dataset.createDimension('mirror_step', 2)
                dataset.createVariable('latitude', float, ('xtrack', 'mirror_step'))
                dataset.createVariable('longitude', float, ('xtrack', 'mirror_step'))
                var = dataset.createVariable(
                    'science_var', float, ('xtrack', 'mirror_step')
                )
                result = get_preferred_ordered_dimensions_info(
                    var, ('latitude', 'longitude'), dataset
                )
                expected = (('xtrack', 'mirror_step'), [])
                self.assertEqual(result, expected)

        with self.subTest('reverse order track dims, no non-track dims'):
            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dataset.createDimension('xtrack', 2)
                dataset.createDimension('mirror_step', 3)
                dataset.createVariable('latitude', float, ('xtrack', 'mirror_step'))
                dataset.createVariable('longitude', float, ('xtrack', 'mirror_step'))
                var = dataset.createVariable(
                    'science_var', float, ('xtrack', 'mirror_step')
                )
                result = get_preferred_ordered_dimensions_info(
                    var, ('latitude', 'longitude'), dataset
                )
                expected = (('mirror_step', 'xtrack'), [])
                self.assertEqual(result, expected)

        with self.subTest('correct order track dims, non-track dim at end'):
            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dataset.createDimension('xtrack', 3)
                dataset.createDimension('mirror_step', 2)
                layer_dim = dataset.createDimension('layer', 5)
                dataset.createVariable('latitude', float, ('xtrack', 'mirror_step'))
                dataset.createVariable('longitude', float, ('xtrack', 'mirror_step'))
                var = dataset.createVariable(
                    'science_var', float, ('xtrack', 'mirror_step', 'layer')
                )
                result = get_preferred_ordered_dimensions_info(
                    var, ('latitude', 'longitude'), dataset
                )
                expected = (('layer', 'xtrack', 'mirror_step'), [layer_dim])
                self.assertEqual(result, expected)

        with self.subTest('reverse order track dims, non-track dims on both ends'):
            with Dataset('test.nc', 'w', diskless=True) as dataset:
                dataset.createDimension('xtrack', 2)
                dataset.createDimension('mirror_step', 3)
                time_dim = dataset.createDimension('time', 5)
                layer_dim = dataset.createDimension('layer', 5)
                dataset.createVariable('latitude', float, ('xtrack', 'mirror_step'))
                dataset.createVariable('longitude', float, ('xtrack', 'mirror_step'))
                var = dataset.createVariable(
                    'science_var', float, ('time', 'xtrack', 'mirror_step', 'layer')
                )
                result = get_preferred_ordered_dimensions_info(
                    var, ('latitude', 'longitude'), dataset
                )
                expected = (
                    ('time', 'layer', 'mirror_step', 'xtrack'),
                    [time_dim, layer_dim],
                )
                self.assertEqual(result, expected)


class TestGetRowsPerScan(TestCase):
    def test_number_less_than_2(self):
        self.assertEqual(get_rows_per_scan(1), 1)

    def test_even_composite_number(self):
        self.assertEqual(get_rows_per_scan(4), 2)

    def test_odd_composite_number(self):
        self.assertEqual(get_rows_per_scan(9), 3)

    def test_prime_number(self):
        self.assertEqual(get_rows_per_scan(3), 3)
