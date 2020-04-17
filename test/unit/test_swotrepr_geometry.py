from pyproj import Proj
import numpy as np

from PyMods.swotrepr_geometry import (get_absolute_resolution,
                                      get_extents_from_perimeter,
                                      get_perimeter_points, get_polygon_area,
                                      get_projected_resolution,
                                      reproject_perimeter_points,
                                      swath_crosses_international_date_line)
from test.test_utils import TestBase


class TestSwotReprGeometry(TestBase):

    @classmethod
    def setUpClass(cls):
        cls.ease_projection = Proj('EPSG:6933')
        cls.geographic_coordinates = Proj('EPSG:4326')
        cls.latitudes = np.array([[25.0, 25.0, 25.0, 25.0],
                                  [20.0, 20.0, 20.0, 20.0],
                                  [15.0, 15.0, 15.0, 15.0]])
        cls.longitudes = np.array([[40.0, 45.0, 50.0, 55.0],
                                   [40.0, 45.0, 50.0, 55.0],
                                   [40.0, 45.0, 50.0, 55.0]])

    def test_get_projected_resolution(self):
        """ Ensure the calculated resolution from the input longitudes and
            latitudes is as expected. Resolution is large for metres, because
            grid is in 5 degree increments.

        """
        test_args = [['Geographic', self.geographic_coordinates, 3.536],
                     ['Projected metres', self.ease_projection, 380302.401]]

        for description, projection, expected_resolution in test_args:
            with self.subTest(description):
                resolution = get_projected_resolution(projection,
                                                      self.longitudes,
                                                      self.latitudes)
                self.assertAlmostEqual(resolution, expected_resolution, places=3)

    def test_get_extents_from_perimeter(self):
        """ Get the maximum and minimum values from the perimeter data
            points.

        """
        with self.subTest('Geographic coordinates'):
            x_min, x_max, y_min, y_max = get_extents_from_perimeter(
                self.geographic_coordinates, self.longitudes, self.latitudes
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

    def test_get_perimeter_points(self):
        """ Given two supplied numpy arrays, ensure that pairs of coordinates
            for each point on the perimeter are returned. Note, one of the
            corners should be present twice, to ensure an enclosed polygon.

        """
        expected_points = [(40.0, 25.0), (40.0, 20.0), (40.0, 15.0),
                           (45.0, 15.0), (50.0, 15.0), (55.0, 15.0),
                           (55.0, 20.0), (55.0, 25.0), (50.0, 25.0),
                           (45.0, 25.0)]

        perimeter_points = get_perimeter_points(self.longitudes,
                                                self.latitudes)

        self.assertCountEqual(perimeter_points, expected_points,
                              'Correct number of points')
        self.assertCountEqual(perimeter_points, set(perimeter_points),
                              'All points unique')
        self.assertEqual(perimeter_points, expected_points)

    def test_reproject_perimeter_points(self):
        """ Ensure a set of points will be correctly projected. """
        proj = Proj('EPSG:32603')
        input_points = [(10.0, 2.5), (15.0, 3.0), (20.0, 3.5)]
        expected_x = np.array([1056557.724, 500000.000, -56049.659])
        expected_y = np.array([19718541.688, 19664336.706, 19607585.857])

        x_values, y_values = reproject_perimeter_points(input_points, proj)
        np.testing.assert_allclose(x_values, expected_x, atol=0.001, rtol=0)
        np.testing.assert_allclose(y_values, expected_y, atol=0.001, rtol=0)

    def test_get_polygon_area(self):
        """ Ensure area is correctly calculated for some known shapes. """
        triangle_points_x = [1.0, 3.0, 1.0]
        triangle_points_y = [1.0, 1.0, 3.0]
        triangle_area = get_polygon_area(triangle_points_x, triangle_points_y)
        self.assertEqual(triangle_area, 2.0)

        square_points_x = [1.0, 3.0, 3.0, 1.0]
        square_points_y = [2.0, 2.0, 4.0, 4.0]
        square_area = get_polygon_area(square_points_x, square_points_y)
        self.assertEqual(square_area, 4.0)

    def test_get_absolute_resolution(self):
        """ Ensure the expeted resolution value is returned. """
        area = 16.0
        n_pixels = 4
        resolution = get_absolute_resolution(area, n_pixels)
        self.assertIsInstance(resolution, float)
        self.assertEqual(resolution, 2.0)

    def test_swath_crosses_international_date_line(self):
        """ Ensure the International Date Line is correctly identified. """
        not_crossing_lon = np.array([[10, 20, 30], [10, 20, 30]])
        crossing_lon = np.array([[165, 175, -175], [165, 175, -175]])
        crossing_vertical = np.array([[101.0, 101.0], [10.0, 10.0]])

        not_cross_diff = np.diff(not_crossing_lon, n=1, axis=1)
        cross_diff = np.diff(crossing_lon, n=1, axis=1)

        with self.subTest('Returns False when not crossing'):
            crosses = swath_crosses_international_date_line(not_crossing_lon)
            self.assertFalse(crosses)

        with self.subTest('Returns True when crossing'):
            crosses = swath_crosses_international_date_line(crossing_lon)
            self.assertTrue(crosses)

        with self.subTest('Returns True when crossing between rows'):
            crosses = swath_crosses_international_date_line(crossing_vertical)
            self.assertTrue(crosses)
