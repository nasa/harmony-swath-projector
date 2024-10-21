""" This module contains custom exceptions specific to the Harmony Swath
    Projector. These exceptions are intended to allow for easier debugging of
    the expected errors that may occur during an invocation of the service.

"""


class CustomError(Exception):
    """Base class for exceptions in the Swath Projector. This base class could
    be extended in the future to assign exit codes, for example.

    """

    def __init__(self, exception_type, message):
        self.exception_type = exception_type
        self.message = message
        super().__init__(self.message)


class MissingReprojectedDataError(CustomError):
    """This exception is raised when an expected single-band output file
    containing reprojected data for a science variable is not found by
    the `create_output` function in `nc_merge.py`.

    """

    def __init__(self, missing_variable):
        super().__init__(
            'MissingReprojectedDataError',
            ('Could not find reprojected output file for ' f'{missing_variable}.'),
        )


class MissingCoordinatesError(CustomError):
    """This exception is raised when for science variables an coordinate
    variable is not found in dataset by the `get_coordinate_variable`
    function in `utilities.py`.

    """

    def __init__(self, missing_coordinate):
        super().__init__(
            'MissingCoordinatesError',
            f'Could not find coordinate {missing_coordinate}.',
        )


class InvalidTargetGrid(CustomError):
    """Raised when a request specifies an incomplete or invalid grid."""

    def __init__(self):
        super().__init__(
            'InvalidTargetGrid', 'Insufficient or invalid target grid parameters.'
        )
