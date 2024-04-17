from random import shuffle
from shutil import rmtree
from tempfile import mkdtemp
from unittest import TestCase
from uuid import uuid4

import numpy as np
from netCDF4 import Dataset
from pyproj import Proj

from swath_projector.swath_geometry import (
    clockwise_point_sort,
    euclidean_distance,
    get_absolute_resolution,
    get_extents_from_perimeter,
    get_one_dimensional_resolution,
    get_perimeter_coordinates,
    get_polygon_area,
    get_projected_resolution,
    get_slice_edges,
    get_valid_coordinates_mask,
    reproject_coordinates,
    sort_perimeter_points,
    swath_crosses_international_date_line,
)


class TestSwathGeometry(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.ease_projection = Proj('EPSG:6933')
        cls.geographic_projection = Proj('EPSG:4326')

        cls.test_dir = mkdtemp()
        cls.test_path = f'{cls.test_dir}/geometry.nc'

        cls.lat_data = np.array(
            [
                [25.0, 25.0, 25.0, 25.0],
                [20.0, 20.0, 20.0, 20.0],
                [15.0, 15.0, 15.0, 15.0],
            ]
        )
        cls.lon_data = np.array(
            [
                [40.0, 45.0, 50.0, 55.0],
                [40.0, 45.0, 50.0, 55.0],
                [40.0, 45.0, 50.0, 55.0],
            ]
        )

        cls.test_file = Dataset(cls.test_path, 'w')
        cls.test_file.createDimension('nj', size=3)
        cls.test_file.createDimension('ni', size=4)
        cls.test_file.createVariable('lat', float, dimensions=('nj', 'ni'))
        cls.test_file.createVariable('lon', float, dimensions=('nj', 'ni'))
        cls.test_file.createVariable('lat_1d', float, dimensions=('ni',))
        cls.test_file.createVariable('lon_1d', float, dimensions=('ni',))
        cls.test_file['lat'][:] = cls.lat_data
        cls.test_file['lon'][:] = cls.lon_data
        cls.test_file['lat_1d'][:] = np.array([0.0, 3.0, 6.0, 9.0])
        cls.test_file['lon_1d'][:] = np.array([2.0, 6.0, 10.0, 14.0])
        cls.test_file.close()

    def setUp(self):
        self.test_dataset = Dataset(self.test_path)
        self.longitudes = self.test_dataset['lon']
        self.latitudes = self.test_dataset['lat']

    def tearDown(self):
        self.test_dataset.close()

    @classmethod
    def tearDownClass(cls):
        rmtree(cls.test_dir, ignore_errors=True)

    def test_euclidean_distance(self):
        """Ensure the Euclidean distance is correctly calculated."""
        self.assertEqual(euclidean_distance(2.3, 5.3, 6.8, 2.8), 5.0)

    def test_get_projected_resolution(self):
        """Ensure the calculated resolution from the input longitudes and
        latitudes is as expected. Resolution is large for metres, because
        grid is in 5 degree increments.

        """
        test_args = [
            ['Geographic', self.geographic_projection, 3.536],
            ['Projected metres', self.ease_projection, 380302.401],
        ]

        for description, projection, expected_resolution in test_args:
            with self.subTest(description):
                resolution = get_projected_resolution(
                    projection, self.longitudes, self.latitudes
                )
                self.assertAlmostEqual(resolution, expected_resolution, places=3)

    def test_get_projected_resolution_1d(self):
        """Ensure the calculated one-dimensional resolution is correct."""
        resolution = get_projected_resolution(
            self.geographic_projection,
            self.test_dataset['lon_1d'],
            self.test_dataset['lat_1d'],
        )

        self.assertAlmostEqual(resolution, 5.0)

    def test_get_extents_from_perimeter(self):
        """Get the maximum and minimum values from the perimeter data
        points.

        """
        with self.subTest('Geographic coordinates'):
            x_min, x_max, y_min, y_max = get_extents_from_perimeter(
                self.geographic_projection, self.longitudes, self.latitudes
            )
            self.assertAlmostEqual(x_min, 40.0, places=7)
            self.assertAlmostEqual(x_max, 55.0, places=7)
            self.assertAlmostEqual(y_min, 15.0, places=7)
            self.assertAlmostEqual(y_max, 25.0, places=7)

        with self.subTest('Projected metres:'):
            x_min, x_max, y_min, y_max = get_extents_from_perimeter(
                self.ease_projection, self.longitudes, self.latitudes
            )

            self.assertAlmostEqual(x_min, 3859451.210, places=3)
            self.assertAlmostEqual(x_max, 5306745.414, places=3)
            self.assertAlmostEqual(y_min, 1892380.583, places=3)
            self.assertAlmostEqual(y_max, 3091555.561, places=3)

        with self.subTest('Geographic, 1-D'):
            x_min, x_max, y_min, y_max = get_extents_from_perimeter(
                self.geographic_projection,
                self.test_dataset['lon_1d'],
                self.test_dataset['lat_1d'],
            )
            self.assertAlmostEqual(x_min, 2.0, places=7)
            self.assertAlmostEqual(x_max, 14.0, places=7)
            self.assertAlmostEqual(y_min, 0.0, places=7)
            self.assertAlmostEqual(y_max, 9.0, places=7)

    def test_get_perimeter_coordinates(self):
        """Ensure a full list of longitude, latitude points are returned for
        a given coordinate mask. These points will be unordered.

        """
        valid_pixels = [
            [False, True, True, False],
            [True, True, True, True],
            [True, True, False, False],
        ]

        expected_points = [
            (self.longitudes[0][1], self.latitudes[0][1]),
            (self.longitudes[0][2], self.latitudes[0][2]),
            (self.longitudes[1][0], self.latitudes[1][0]),
            (self.longitudes[1][2], self.latitudes[1][2]),
            (self.longitudes[1][3], self.latitudes[1][3]),
            (self.longitudes[2][0], self.latitudes[2][0]),
            (self.longitudes[2][1], self.latitudes[2][1]),
        ]

        mask = np.ma.masked_where(
            np.logical_not(valid_pixels), np.ones(self.longitudes.shape)
        )

        coordinates = get_perimeter_coordinates(
            self.longitudes[:], self.latitudes[:], mask
        )

        self.assertCountEqual(coordinates, expected_points)

    def test_reproject_coordinates(self):
        """Ensure a set of points will be correctly projected."""
        proj = Proj('EPSG:32603')
        input_points = [(10.0, 2.5), (15.0, 3.0), (20.0, 3.5)]
        expected_x = np.array([1056557.724, 500000.000, -56049.659])
        expected_y = np.array([19718541.688, 19664336.706, 19607585.857])

        x_values, y_values = reproject_coordinates(input_points, proj)
        self.assertEqual(len(x_values), len(expected_x))
        self.assertEqual(len(y_values), len(expected_y))
        np.testing.assert_allclose(x_values, expected_x, atol=0.001, rtol=0)
        np.testing.assert_allclose(y_values, expected_y, atol=0.001, rtol=0)

    def test_get_polygon_area(self):
        """Ensure area is correctly calculated for some known shapes."""
        triangle_points_x = [1.0, 3.0, 1.0]
        triangle_points_y = [1.0, 1.0, 3.0]
        triangle_area = get_polygon_area(triangle_points_x, triangle_points_y)
        self.assertEqual(triangle_area, 2.0)

        square_points_x = [1.0, 3.0, 3.0, 1.0]
        square_points_y = [2.0, 2.0, 4.0, 4.0]
        square_area = get_polygon_area(square_points_x, square_points_y)
        self.assertEqual(square_area, 4.0)

    def test_get_absolute_resolution(self):
        """Ensure the expected resolution value is returned."""
        area = 16.0
        n_pixels = 4
        resolution = get_absolute_resolution(area, n_pixels)
        self.assertIsInstance(resolution, float)
        self.assertEqual(resolution, 2.0)

    def test_get_one_dimensional_resolution(self):
        """Ensure the 1-D resolution is calculated as expected from the input
        data.

        """
        x_values = list(self.test_dataset['lon_1d'][:])
        y_values = list(self.test_dataset['lat_1d'][:])
        resolution = get_one_dimensional_resolution(x_values, y_values)
        self.assertAlmostEqual(resolution, 5.0)

    def test_swath_crosses_international_date_line(self):
        """Ensure the International Date Line is correctly identified."""
        not_crossing_lon = np.array([[10, 20, 30], [10, 20, 30]])
        crossing_lon = np.array([[165, 175, -175], [165, 175, -175]])
        crossing_vertical = np.array([[101.0, 101.0], [10.0, 10.0]])

        with self.subTest('Returns False when not crossing'):
            crosses = swath_crosses_international_date_line(not_crossing_lon)
            self.assertFalse(crosses)

        with self.subTest('Returns True when crossing'):
            crosses = swath_crosses_international_date_line(crossing_lon)
            self.assertTrue(crosses)

        with self.subTest('Returns True when crossing between rows'):
            crosses = swath_crosses_international_date_line(crossing_vertical)
            self.assertTrue(crosses)

    def test_clockwise_point_sort(self):
        """Ensure the correct lengths and angles are calculated."""
        test_args = [
            ['Point is at origin', [0, 0], [0, 0], (-np.pi, 0)],
            ['Point is in vertical direction', [0, 0], [0, 30], (0.0, 30)],
            ['Point at 45 degrees', [0, 0], [3, 3], (np.pi / 4.0, np.sqrt(18.0))],
        ]

        for description, origin, point, expected_results in test_args:
            with self.subTest(description):
                self.assertEqual(clockwise_point_sort(origin, point), expected_results)

    def test_sort_perimeter_points(self):
        """Ensure unsorted x and y coordinates are returned in order.
        The points in the `square_points` and `polygon_points` lists are
        ordered to be the expected output.

        """
        square_points = [[0, 0], [0, 1], [0, 2], [1, 2], [2, 2], [2, 1], [2, 0], [1, 0]]
        polygon_points = [
            [20, 10],
            [10, 30],
            [20, 40],
            [10, 50],
            [20, 60],
            [30, 60],
            [40, 50],
            [50, 60],
            [50, 40],
            [60, 40],
            [50, 30],
            [60, 10],
        ]

        test_args = [['Simple square', square_points], ['Polygon', polygon_points]]

        for description, ordered_points in test_args:
            with self.subTest(description):
                expected_x, expected_y = zip(*ordered_points)

                disordered_points = ordered_points.copy()
                shuffle(disordered_points)
                disordered_x, disordered_y = zip(*disordered_points)

                ordered_x, ordered_y = sort_perimeter_points(disordered_x, disordered_y)
                self.assertEqual(ordered_x, expected_x)
                self.assertEqual(ordered_y, expected_y)

    def test_get_valid_coordinates_mask(self):
        """Ensure all logical conditions are respected."""
        fill_value = -9999.0

        valid_lon = np.array([[1.0, 2.0], [3.0, 4.0]])
        valid_lat = np.array([[5.0, 6.0], [7.0, 8.0]])

        nan_lon = np.array([[np.nan, 2.0], [3.0, 4.0]])
        nan_lat = np.array([[5.0, np.nan], [7.0, 8.0]])

        fill_lon = np.array([[1.0, 2.0], [fill_value, 4.0]])
        fill_lat = np.array([[5.0, 6.0], [7.0, fill_value]])

        combined_lon = np.array([[np.nan, 2.0], [fill_value, 4.0]])
        combined_lat = np.array([[5.0, np.nan], [7.0, fill_value]])

        test_args = [
            ['All valid', valid_lon, valid_lat, [[1, 1], [1, 1]]],
            ['Longitude NaN', nan_lon, valid_lat, [[0, 1], [1, 1]]],
            ['Longitude fill', fill_lon, valid_lat, [[1, 1], [0, 1]]],
            ['Latitude NaN', valid_lon, nan_lat, [[1, 0], [1, 1]]],
            ['Latitude fill', valid_lon, fill_lat, [[1, 1], [1, 0]]],
            ['Combination', combined_lon, combined_lat, [[0, 0], [0, 0]]],
        ]

        for description, lon_data, lat_data, expected_mask in test_args:
            with self.subTest(description):
                test_path = f'{self.test_dir}/test_mask_{uuid4()}.nc'
                test_file = Dataset(test_path, 'w')
                test_file.createDimension('nj', size=2)
                test_file.createDimension('ni', size=2)
                test_file.createVariable(
                    'lat', float, dimensions=('nj', 'ni'), fill_value=fill_value
                )
                test_file.createVariable(
                    'lon', float, dimensions=('nj', 'ni'), fill_value=fill_value
                )
                test_file['lat'][:] = lat_data
                test_file['lon'][:] = lon_data
                test_file.close()

                dataset = Dataset(test_path)
                np.testing.assert_array_equal(
                    get_valid_coordinates_mask(dataset['lon'], dataset['lat']),
                    expected_mask,
                )
                dataset.close()

    def test_get_slice_edges(self):
        """Ensure the pixel coordinates for exterior points are returned,
        this should order the elements based on whether the input slice
        is a row or a column.

        """
        data_slice = np.array([2, 3, 4, 5, 6, 7, 8, 9])
        slice_index = 6

        expected_row_results = [(6, 2), (6, 9)]
        expected_column_results = [(2, 6), (9, 6)]

        test_args = [
            ['Row', True, expected_row_results],
            ['Column', False, expected_column_results],
        ]

        for description, is_row, expected_results in test_args:
            with self.subTest(description):
                self.assertEqual(
                    get_slice_edges(data_slice, slice_index, is_row=is_row),
                    expected_results,
                )

        with self.subTest('Default (to row)'):
            self.assertEqual(
                get_slice_edges(data_slice, slice_index), expected_row_results
            )
