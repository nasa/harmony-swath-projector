from logging import Logger
from typing import Dict
from unittest.mock import patch

from numpy.testing import assert_array_equal
from pyproj import Proj
from xarray import Variable

from pymods.reproject import (CRS_DEFAULT, get_input_file_data,
                              get_params_from_msg, rgetattr)
from swotrepr import HarmonyAdapter
from test.test_utils import TestBase


def create_message(test_data: Dict):
    """ A helper function to create a Harmony message from an input dictionary.
        Note, there is no validation of the message content (beyond anything
        internal to the Harmony Message class.

    """
    reprojector = HarmonyAdapter(test_data)
    return reprojector.message


class TestReproject(TestBase):

    @classmethod
    def setUpClass(cls):
        """ Class properties that only need to be set once. """
        cls.logger = Logger('Reproject test')
        cls.granule = 'test/data/africa.nc'
        cls.granules = [{'local_filename': cls.granule}]
        cls.file_data = get_input_file_data(cls.granule, '')
        cls.default_interpolation = 'ewa-nn'
        cls.height = 1200
        cls.width = 1200
        cls.x_extent = {'min': -180.0, 'max': 180.0}
        cls.y_extent = {'min': -90.0, 'max': 90.0}
        cls.x_res = 1.0
        cls.y_res = -1.0

    def assert_parameters_equal(self, parameters, expected_parameters):
        """ A helper method to check that the parameters retrieved from the
            input Harmony message are all as expected. Note, this does not
            compare the file_data parameter, which probably should not be part
            of the output, (the individual parameters within this dictionary
            are transferred to the top level of the parameters). There is a
            note in the code for clean-up to occur!

        """
        for key, expected_value in expected_parameters.items():
            if not isinstance(expected_value, Variable):
                self.assertEqual(parameters[key], expected_value)
            else:
                assert_array_equal(parameters[key][:], expected_value[:])

    def test_get_params_from_msg_interpolation(self):
        """ Ensure that various input messages can be correctly parsed, and
            that those missing raise the expected exceptions.

        """
        test_args = [['No interpolation', {}, self.default_interpolation],
                     ['Non default', {'interpolation': 'ewa'}, 'ewa'],
                     ['None interpolation', {'interpolation': None}, 'ewa-nn'],
                     ['String None', {'interpolation': 'None'}, 'ewa-nn'],
                     ['Empty string', {'interpolation': ''}, 'ewa-nn']]

        for description, format_attribute, expected_interpolation in test_args:
            with self.subTest(description):
                message_content = {'format': format_attribute,
                                   'granules': self.granules}
                message = create_message(message_content)
                parameters = get_params_from_msg(message, self.logger)

                self.assertEqual(parameters['interpolation'],
                                 expected_interpolation)

    def test_get_params_error_5(self):
        """ Ensure that, if parameters are set for the resolution and the
            dimensions, an exception is raised.

        """
        exception_snippet = 'cannot be used at the same time in the message.'

        test_args = [['height and scaleSize', True, False, True, True],
                     ['width and scaleSize', False, True, True, True],
                     ['x_res and dimensions', True, True, True, False],
                     ['y_res and dimensions', True, True, False, True],
                     ['x_res and width', False, True, True, False],
                     ['y_res and height', True, False, False, True],
                     ['x_res and height', True, False, True, False],
                     ['y_res and width', False, True, False, True]]

        for description, has_height, has_width, has_x_res, has_y_res in test_args:
            with self.subTest(description):
                with self.assertRaises(Exception) as exception:
                    message_content = {'granules': self.granules}
                    if has_height:
                        message_content['height'] = self.height

                    if has_width:
                        message_content['width'] = self.width

                    if has_x_res or has_y_res:
                        message_content['scaleSize'] = {}
                        if has_x_res:
                            message_content['scaleSize']['x'] = self.x_res

                        if has_y_res:
                            message_content['scaleSize']['y'] = self.y_res

                    message = create_message(message_content)
                    get_params_from_msg(message, self.logger)
                    self.assertTrue(exception_snippet in str(exception))

    def test_get_params_missing_extents_or_dimensions(self):
        """ Ensure that an exception is raised if there is only on of either
            x_extent and y_extent or height and width set.

        """
        test_args = [
            ['height not width', {'height': self.height}],
            ['width not height', {'width': self.width}],
            ['x_extent not y_extent', {'scaleExtent': {'x': self.x_extent}}],
            ['y_extent not x_extent', {'scaleExtent': {'y': self.y_extent}}]
        ]

        for description, format_content in test_args:
            with self.subTest(description):
                with self.assertRaises(Exception) as exception:
                    message_content = {'granules': self.granules,
                                       'format': format_content}

                    message = create_message(message_content)
                    get_params_from_msg(message, self.logger)
                    self.assertTrue('Missing' in str(exception))

    @patch('pymods.reproject.REPR_MODE', 'gdal')
    def test_get_params_from_msg_gdal(self):
        """ Ensure that default parameters are set, when things are largely
            unspecified for resampling to use gdalwarp.

            Note, the file_data parameter is not checked. This probably
            shouldn't be included in the output anyway, and is a result of
            using the `locals()` function.
        """


        with self.subTest('Message relying on defaults'):
            message_content = {'granules': self.granules}
            message = create_message(message_content)
            expected_parameters = {'crs': CRS_DEFAULT,
                                   'data_group': '',
                                   'granule': message.granules[0],
                                   'height': None,
                                   'input_file': self.granule,
                                   'interpolation': self.default_interpolation,
                                   'latlon_group': '',
                                   'latitudes': self.file_data['latitudes'],
                                   'lat_res': self.file_data['lat_res'],
                                   'logger': self.logger,
                                   'longitudes': self.file_data['longitudes'],
                                   'lon_res': self.file_data['lon_res'],
                                   'message': message,
                                   'projection': Proj(CRS_DEFAULT),
                                   'width': None,
                                   'x_extent': None,
                                   'xres': None,
                                   'y_extent': None,
                                   'yres': None}
            parameters = get_params_from_msg(message, self.logger)
            self.assert_parameters_equal(parameters, expected_parameters)

    @patch('pymods.reproject.get_projected_resolution')
    @patch('pymods.reproject.get_extents_from_perimeter')
    @patch('pymods.reproject.REPR_MODE', 'pyresample')
    def test_get_params_from_msg_pyresample(self, mock_get_extents,
                                            mock_get_resolution):
        """ Ensure that default parameters are set, when things are largely
            unspecified for resampling to use pyresample.

        """
        mock_get_extents.return_value = (self.x_extent['min'],
                                         self.x_extent['max'],
                                         self.y_extent['min'],
                                         self.y_extent['max'])
        mock_get_resolution.return_value = self.x_res
        height = 180  # (90 - -90) / 1
        width = 360  # (180 - -180) / 1

        expected_parameters = {'crs': CRS_DEFAULT,
                               'data_group': '',
                               'height': height,
                               'input_file': self.granule,
                               'interpolation': self.default_interpolation,
                               'latlon_group': '',
                               'latitudes': self.file_data['latitudes'],
                               'lat_res': self.file_data['lat_res'],
                               'logger': self.logger,
                               'longitudes': self.file_data['longitudes'],
                               'lon_res': self.file_data['lon_res'],
                               'projection': Proj(CRS_DEFAULT),
                               'width': width,
                               'x_min': self.x_extent['min'],
                               'x_max': self.x_extent['max'],
                               'xres': self.x_res,
                               'y_min': self.y_extent['min'],
                               'y_max': self.y_extent['max'],
                               'yres': self.y_res}


        empty_format = {}
        extents_format = {'scaleExtent': {'x': self.x_extent,
                                          'y': self.y_extent}}
        resolutions_format = {'scaleSize': {'x': self.x_res, 'y': self.y_res}}
        dimensions_format = {'height': height, 'width': width}

        test_args = [['Message relying on defaults', empty_format],
                     ['Message contains extents', extents_format],
                     ['Message contains resolutions', resolutions_format],
                     ['Message contains dimensions', dimensions_format]]

        for description, format_contents in test_args:
            with self.subTest(description):
                message_content = {'granules': self.granules,
                                   'format': format_contents}
                message = create_message(message_content)

                parameters = get_params_from_msg(message, self.logger)
                self.assert_parameters_equal(parameters, expected_parameters)

    def test_rgetattr(self):
        """ Ensure the utility function to recursively retrieve a class
            attribute will work as expected.

        """
        class ExampleInnerClass:
            def __init__(self):
                self.interpolation = 'bilinear'

        class ExampleOuterClass:
            def __init__(self):
                self.user = 'jglenn'
                self.inner = ExampleInnerClass()

        example_object = ExampleOuterClass()
        default = 'default'

        test_args = [['Single depth property', 'user', 'jglenn'],
                     ['Nested property', 'inner.interpolation', 'bilinear'],
                     ['Absent attribute uses default', 'absent', default],
                     ['Absent nested attribute uses default', 'inner.absent', default],
                     ['Absent outer for nested uses default', 'absent.interpolation', default],
                     ['Outer present, but not object, uses default', 'user.interpolation', default]]

        for description, attribute_path, expected_value in test_args:
            with self.subTest(description):
                self.assertEqual(
                    rgetattr(example_object, attribute_path, default),
                    expected_value
                )
