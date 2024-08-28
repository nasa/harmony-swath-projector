from logging import Logger
from unittest import TestCase

from harmony.message import Message
from pyproj import Proj

from swath_projector.reproject import CRS_DEFAULT, get_parameters_from_message, rgetattr


class TestReproject(TestCase):

    @classmethod
    def setUpClass(cls):
        """Class properties that only need to be set once."""
        cls.logger = Logger('Reproject test')
        cls.granule = 'tests/data/africa.nc'
        cls.granule_url = 'https://example.com/africa.nc'
        cls.granules = [{'local_filename': cls.granule}]
        cls.default_interpolation = 'ewa-nn'
        cls.height = 1200
        cls.width = 1200
        cls.x_extent = {'min': -180.0, 'max': 180.0}
        cls.y_extent = {'min': -90.0, 'max': 90.0}
        cls.x_res = 1.0
        cls.y_res = -1.0

    def setUp(self):
        """Define properties that should be refreshed on each test."""
        self.default_parameters = {
            'crs': CRS_DEFAULT,
            'granule_url': self.granule_url,
            'height': None,
            'input_file': self.granule,
            'interpolation': self.default_interpolation,
            'projection': Proj(CRS_DEFAULT),
            'width': None,
            'x_min': None,
            'x_max': None,
            'xres': None,
            'y_min': None,
            'y_max': None,
            'yres': None,
        }

    def assert_parameters_equal(self, parameters, expected_parameters):
        """A helper method to check that the parameters retrieved from the
        input Harmony message are all as expected. Note, this does not
        compare the file_data parameter, which probably should not be part
        of the output, (the individual parameters within this dictionary
        are transferred to the top level of the parameters). There is a
        note in the code for clean-up to occur!

        """
        for key, expected_value in expected_parameters.items():
            self.assertEqual(
                parameters[key], expected_value, f'Failing parameter: {key}'
            )

    def test_get_parameters_from_message_interpolation(self):
        """Ensure that various input messages can be correctly parsed, and
        that those missing raise the expected exceptions.

        """
        test_args = [
            ['No interpolation', {}, self.default_interpolation],
            ['Non default', {'interpolation': 'ewa'}, 'ewa'],
            ['None interpolation', {'interpolation': None}, 'ewa-nn'],
            ['String None', {'interpolation': 'None'}, 'ewa-nn'],
            ['Empty string', {'interpolation': ''}, 'ewa-nn'],
        ]

        for description, format_attribute, expected_interpolation in test_args:
            with self.subTest(description):
                message_content = {
                    'format': format_attribute,
                    'granules': self.granules,
                }
                message = Message(message_content)
                parameters = get_parameters_from_message(
                    message, self.granule_url, self.granule
                )

                self.assertEqual(parameters['interpolation'], expected_interpolation)

    def test_get_parameters_error_5(self):
        """Ensure that, if parameters are set for the resolution and the
        dimensions, an exception is raised.

        """
        exception_snippet = 'Insufficient or invalid target grid parameters.'

        test_args = [
            ['height and scaleSize', True, False, True, True],
            ['width and scaleSize', False, True, True, True],
            ['x_res and dimensions', True, True, True, False],
            ['y_res and dimensions', True, True, False, True],
            ['x_res and width', False, True, True, False],
            ['y_res and height', True, False, False, True],
            ['x_res and height', True, False, True, False],
            ['y_res and width', False, True, False, True],
        ]

        for description, has_height, has_width, has_x_res, has_y_res in test_args:
            with self.subTest(description):
                message_content = {'granules': self.granules, 'format': {}}
                if has_height:
                    message_content['format']['height'] = self.height

                if has_width:
                    message_content['format']['width'] = self.width

                if has_x_res or has_y_res:
                    message_content['format']['scaleSize'] = {}
                    if has_x_res:
                        message_content['format']['scaleSize']['x'] = self.x_res

                    if has_y_res:
                        message_content['format']['scaleSize']['y'] = self.y_res

                message = Message(message_content)

                with self.assertRaises(Exception) as context:
                    get_parameters_from_message(message, self.granule_url, self.granule)
                self.assertTrue(
                    str(context.exception).endswith(exception_snippet),
                    f'Test Failed: {description}',
                )

    def test_get_parameters_missing_extents_or_dimensions(self):
        """Ensure that an exception is raised if there is only one of either
        x_extent and y_extent or height and width set.

        """
        test_args = [
            ['height not width', {'height': self.height}],
            ['width not height', {'width': self.width}],
            ['x_extent not y_extent', {'scaleExtent': {'x': self.x_extent}}],
            ['y_extent not x_extent', {'scaleExtent': {'y': self.y_extent}}],
        ]

        for description, format_content in test_args:
            with self.subTest(description):
                message_content = {'granules': self.granules, 'format': format_content}

                message = Message(message_content)

                with self.assertRaises(Exception) as context:
                    get_parameters_from_message(message, self.granule_url, self.granule)

                self.assertTrue('Missing' in str(context.exception))

    def test_get_parameters_from_message_defaults(self):
        """Ensure that if the most minimal Harmony message is supplied to the
        SWOT Reprojection tool, sensible defaults are assigned for the
        extracted message parameters.

        """
        expected_parameters = self.default_parameters

        message = Message({'granules': self.granules, 'format': {}})
        parameters = get_parameters_from_message(
            message, self.granule_url, self.granule
        )
        self.assert_parameters_equal(parameters, expected_parameters)

    def test_get_parameters_from_message_extents(self):
        """Ensure that if the `scaleExtent` is specified in the input
        Harmony message, the non-default extents are used.

        """
        expected_parameters = self.default_parameters
        expected_parameters['x_min'] = self.x_extent['min']
        expected_parameters['x_max'] = self.x_extent['max']
        expected_parameters['y_min'] = self.y_extent['min']
        expected_parameters['y_max'] = self.y_extent['max']

        extents_format = {'scaleExtent': {'x': self.x_extent, 'y': self.y_extent}}
        message = Message({'granules': self.granules, 'format': extents_format})
        expected_parameters['x_extent'] = message.format.scaleExtent.x
        expected_parameters['y_extent'] = message.format.scaleExtent.y

        parameters = get_parameters_from_message(
            message, self.granule_url, self.granule
        )
        self.assert_parameters_equal(parameters, expected_parameters)

    def test_get_parameters_from_message_resolutions(self):
        """Ensure that if the `scaleSize` is specified in the input Harmony
        message, the non-default resolutions are used.

        """
        expected_parameters = self.default_parameters
        expected_parameters['xres'] = self.x_res
        expected_parameters['yres'] = self.y_res

        resolutions_format = {'scaleSize': {'x': self.x_res, 'y': self.y_res}}
        message = Message({'granules': self.granules, 'format': resolutions_format})
        parameters = get_parameters_from_message(
            message, self.granule_url, self.granule
        )
        self.assert_parameters_equal(parameters, expected_parameters)

    def test_get_parameters_from_message_dimensions(self):
        """Ensure that if the `height` and `width` are specified in the input
        Harmony message, the non-default dimensions are used.

        """
        expected_parameters = self.default_parameters
        expected_parameters['height'] = self.height
        expected_parameters['width'] = self.height

        extents_format = {'height': self.height, 'width': self.width}
        message = Message({'granules': self.granules, 'format': extents_format})
        parameters = get_parameters_from_message(
            message, self.granule_url, self.granule
        )
        self.assert_parameters_equal(parameters, expected_parameters)

    def test_rgetattr(self):
        """Ensure the utility function to recursively retrieve a class
        attribute will work as expected.

        """

        class ExampleInnerClass:
            def __init__(self):
                self.interpolation = 'bilinear'

        class ExampleOuterClass:
            def __init__(self):
                self.user = 'jglenn'
                self.inner = ExampleInnerClass()
                self.none = None

        example_object = ExampleOuterClass()
        default = 'default'

        test_args = [
            ['Single depth property', 'user', 'jglenn'],
            ['Nested property', 'inner.interpolation', 'bilinear'],
            ['Property is None, default', 'none', default],
            ['Absent attribute uses default', 'absent', default],
            ['Absent nested attribute uses default', 'inner.absent', default],
            ['Absent outer for nested uses default', 'absent.interpolation', default],
            [
                'Outer present, but not object, uses default',
                'user.interpolation',
                default,
            ],
        ]

        for description, attribute_path, expected_value in test_args:
            with self.subTest(description):
                self.assertEqual(
                    rgetattr(example_object, attribute_path, default), expected_value
                )
