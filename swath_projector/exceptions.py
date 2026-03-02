"""This module contains custom exceptions specific to the Harmony Swath
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


class NonProjectableVariableError(CustomError):
    """Exception raised when a variable is determined to be non-projectable.

    This is a known/expected condition, not a programming error.
    """

    def __init__(self, variable_name, message):
        super().__init__(
            'NonProjectableVariableError',
            f'Variable {variable_name} is non-projectable: {message}',
        )


class InvalidGranuleList(CustomError):
    """Raised when the granule list is invalid or empty."""

    def __init__(self):
        super().__init__(
            'InvalidGranuleList',
            'Invalid granule list.',
        )


class UnableToParseInputFileVariables(CustomError):
    """Raised when the input file variables cannot be parsed."""

    def __init__(self, message):
        super().__init__(
            'UnableToParseInputFileVariables',
            'Unable to parse input file variables: {message}',
        )


class NoScienceVariablesFound(CustomError):
    """Raised when no science variables are found in the input file."""

    def __init__(self):
        super().__init__(
            'NoScienceVariablesFound',
            'No science variables found in input file.',
        )


class NoReprojectedVariables(CustomError):
    """Raised when no variables could be reprojected."""

    def __init__(self):
        super().__init__(
            'NoReprojectedVariables',
            'No variables could be reprojected.',
        )


class InputFileNotFound(CustomError):
    """Raised when the input file does not exist."""

    def __init__(self):
        super().__init__(
            'InputFileNotFound',
            'Input file does not exist.',
        )


class MissingXExtent(CustomError):
    """Raised when the x extent parameter is missing."""

    def __init__(self):
        super().__init__(
            'MissingXExtent',
            'Missing x extent.',
        )


class MissingYExtent(CustomError):
    """Raised when the y extent parameter is missing."""

    def __init__(self):
        super().__init__(
            'MissingYExtent',
            'Missing y extent.',
        )


class MissingCellHeight(CustomError):
    """Raised when the cell height parameter is missing."""

    def __init__(self):
        super().__init__(
            'MissingCellHeight',
            'Missing cell height.',
        )


class MissingCellWidth(CustomError):
    """Raised when the cell width parameter is missing."""

    def __init__(self):
        super().__init__(
            'MissingCellWidth',
            'Missing cell width.',
        )


class UnsupportedCoordinateShape(CustomError):
    """Raised when coordinate variables have an unsupported shape."""

    def __init__(self):
        super().__init__(
            'UnsupportedCoordinateShape',
            'Unsupported coordinate variable shape.',
        )


class CannotReprojectVariable(CustomError):
    """Raised when a specific variable cannot be reprojected."""

    def __init__(self, variable):
        super().__init__(
            'CannotReprojectVariable',
            f'Cannot reproject {variable}.',
        )
