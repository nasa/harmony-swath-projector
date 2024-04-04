""" This module contains functions to perform interpolation on the science
    datasets within a file, using the pyresample Python package.

"""

from functools import partial
from logging import Logger
from typing import Dict, List, Optional, Tuple
import os

from netCDF4 import Dataset
from pyresample.bilinear import get_bil_info, get_sample_from_bil_info
from pyresample.ewa import fornav, ll2cr
from pyresample.geometry import AreaDefinition, SwathDefinition
from pyresample.kd_tree import get_neighbour_info, get_sample_from_neighbour_info
from pyresample.utils import check_and_wrap
from varinfo import VarInfoFromNetCDF4
import numpy as np

from swath_projector.nc_single_band import HARMONY_TARGET, write_single_band_output
from swath_projector.swath_geometry import (
    get_extents_from_perimeter,
    get_projected_resolution,
)
from swath_projector.utilities import (
    create_coordinates_key,
    get_coordinate_variable,
    get_scale_and_offset,
    get_variable_file_path,
    get_variable_numeric_fill_value,
    get_variable_values,
    make_array_two_dimensional,
)

# In nearest neighbour interpolation, the distance to a found value is
# guaranteed to be no further than (1 + EPSILON) times the distance to the
# correct neighbour.
EPSILON = 0.5
# The number of closest locations considered when selecting the four data
# points around the target location. A smaller number reduces runtime, but this
# value needs to be large enough to ensure the target is surrounded.
NEIGHBOURS = 16
# The radius, in metres, around each grid pixel to search for swath neighbours.
# This is used in both the bilinear and nearest-neighbour interpolation
# methods, and is set to the default value from `pyresample`.
RADIUS_OF_INFLUENCE = 50000


def resample_all_variables(
    message_parameters: Dict,
    science_variables: List[str],
    temp_directory: str,
    logger: Logger,
    var_info: VarInfoFromNetCDF4,
) -> List[str]:
    """Iterate through all science variables and reproject to the target
    coordinate grid.

    Returns:
        output_variables: A list of names of successfully reprojected
            variables.
    """
    output_extension = os.path.splitext(message_parameters['input_file'])[-1]
    reprojection_cache = get_reprojection_cache(message_parameters)
    output_variables = []

    check_for_valid_interpolation(message_parameters, logger)

    for variable in science_variables:
        try:
            variable_output_path = get_variable_file_path(
                temp_directory, variable, output_extension
            )

            logger.info(f'Reprojecting variable "{variable}"')
            logger.info(f'Reprojected output: "{variable_output_path}"')

            resample_variable(
                message_parameters,
                variable,
                reprojection_cache,
                variable_output_path,
                logger,
                var_info,
            )

            output_variables.append(variable)
        except Exception as error:
            # Assume for now variable cannot be reprojected. TBD add checks for
            # other error conditions.
            logger.error(f'Cannot reproject {variable}')
            logger.exception(error)

    return output_variables


def resample_variable(
    message_parameters: Dict,
    full_variable: str,
    reprojection_cache: Dict,
    variable_output_path: str,
    logger: Logger,
    var_info: VarInfoFromNetCDF4,
) -> None:
    """A function to perform the reprojection of a single variable. The
    reprojection information for each will be derived using interpolation
    method specific functions, as will the calculation of reprojected
    results.

    Reprojection information will be stored in a cache, enabling it to be
    recalled, rather than re-derived for subsequent science variables that
    share the same coordinate variables.

    """
    interpolation_functions = get_resampling_functions()[
        message_parameters['interpolation']
    ]
    dataset = Dataset(message_parameters['input_file'])
    variable = dataset[full_variable]
    # get variable with CF_Overrides and get real coordinates
    variable_cf = var_info.get_variable(full_variable)
    coordinates_key = create_coordinates_key(variable_cf)

    if coordinates_key in reprojection_cache:
        logger.debug(
            'Retrieving previous interpolation information for ' f'{full_variable}'
        )
        reprojection_information = reprojection_cache[coordinates_key]
    else:
        logger.debug(f'Deriving interpolation information for {full_variable}')

        if HARMONY_TARGET in reprojection_cache:
            logger.debug('Using target area defined in Harmony message.')
            target_area = reprojection_cache[HARMONY_TARGET]['target_area']
        else:
            logger.debug('Deriving target area from associated coordinates.')
            target_area = get_target_area(
                message_parameters, dataset, coordinates_key, logger
            )

        swath_definition = get_swath_definition(dataset, coordinates_key)

        reprojection_information = interpolation_functions['get_information'](
            swath_definition, target_area
        )

        # This entry stores target area information, too. If the Harmony
        # message has a fully defined target area, the target area information
        # cached within the coordinate key entry will only be a reference to
        # the Harmony message target area objects, not copies of the objects
        # themselves.
        reprojection_cache[coordinates_key] = reprojection_information

    # Use a dictionary to store input variable values and fill value. This
    # allows the same function signature to retrieve results from all
    # interpolation methods.
    fill_value = get_variable_numeric_fill_value(variable)
    variable_information = {
        'values': get_variable_values(dataset, variable, fill_value),
        'fill_value': fill_value,
    }

    results = interpolation_functions['get_results'](
        variable_information, reprojection_information
    )
    results = results.astype(variable.dtype)

    attributes = get_scale_and_offset(variable)
    write_single_band_output(
        reprojection_information['target_area'],
        results,
        full_variable,
        variable_output_path,
        reprojection_cache,
        attributes,
    )

    dataset.close()

    logger.debug(
        f'Saved {full_variable} output to temporary file: ' f'{variable_output_path}'
    )


def get_bilinear_information(
    swath_definition: SwathDefinition, target_area: AreaDefinition
) -> Dict:
    """Return the necessary information to reproject a swath using the
    bilinear interpolation method. This information will be stored in the
    reprojection cache, for use with other science variables that share the
    same coordinate variables.

    """
    bilinear_information = get_bil_info(
        swath_definition, target_area, radius=RADIUS_OF_INFLUENCE, neighbours=NEIGHBOURS
    )

    return {
        'vertical_distances': bilinear_information[0],
        'horizontal_distances': bilinear_information[1],
        'valid_input_indices': bilinear_information[2],
        'valid_point_mapping': bilinear_information[3],
        'target_area': target_area,
    }


def get_bilinear_results(variable: Dict, bilinear_information: Dict) -> np.ndarray:
    """Use the derived information from the input swath and target area to
    reproject variable data in the target area using the bilinear
    interpolation method. Any pixels with NaN values after reprojection are
    set to the fill value for the variable.

    """
    results = get_sample_from_bil_info(
        variable['values'].ravel(),
        bilinear_information['vertical_distances'],
        bilinear_information['horizontal_distances'],
        bilinear_information['valid_input_indices'],
        bilinear_information['valid_point_mapping'],
        output_shape=bilinear_information['target_area'].shape,
    )

    if variable['fill_value'] is not None:
        np.nan_to_num(results, nan=variable['fill_value'], copy=False)

    return results


def get_ewa_information(
    swath_definition: SwathDefinition, target_area: AreaDefinition
) -> Dict:
    """Return the necessary information to reproject a swath using the
    Elliptically Weighted Average interpolation method. This information
    will be stored in the reprojection cache, for use with other science
    variables that share the same coordinate variables.

    """
    ewa_info = ll2cr(swath_definition, target_area)

    return {'columns': ewa_info[1], 'rows': ewa_info[2], 'target_area': target_area}


def get_ewa_results(
    variable: Dict, ewa_information: Dict, maximum_weight_mode: bool
) -> np.ndarray:
    """Use the derived information from the input swath and target area to
    reproject variable data in the target area using the Elliptically
    Weighted Average interpolation. This also includes the flag for whether
    to use the maximum weight mode.

    If maximum_weight_mode is False, a weighted average of all swath cells
    that map to a particular grid cell is used. If True, the swath cell
    having the maximum weight of all swath cells that map to a particular
    grid cell is used, instead of a weighted average. This is a
    'nearest-neighbour' style interpolation, but accounts for pixels within
    the same scan line being more closely related than those from different
    scans.

    """
    if np.issubdtype(variable['values'].dtype, np.integer):
        variable['values'] = variable['values'].astype(float)

    # This call falls back on the EWA rows_per_scan default of total input rows
    # and ignores the quality status return value
    _, results = fornav(
        ewa_information['columns'],
        ewa_information['rows'],
        ewa_information['target_area'],
        variable['values'],
        maximum_weight_mode=maximum_weight_mode,
    )

    if variable['fill_value'] is not None:
        np.nan_to_num(results, nan=variable['fill_value'], copy=False)

    return results


def get_near_information(
    swath_definition: SwathDefinition, target_area: AreaDefinition
) -> Dict:
    """Return the necessary information to reproject a swath using the
    nearest neighbour interpolation method. This information will be stored
    in the reprojection cache, for use with other science variables that
    share the same coordinate variables.

    """
    near_information = get_neighbour_info(
        swath_definition,
        target_area,
        RADIUS_OF_INFLUENCE,
        epsilon=EPSILON,
        neighbours=1,
    )

    return {
        'valid_input_index': near_information[0],
        'valid_output_index': near_information[1],
        'index_array': near_information[2],
        'distance_array': near_information[3],
        'target_area': target_area,
    }


def get_near_results(variable: Dict, near_information) -> np.ndarray:
    """Use the derived information from the input swath and target area to
    reproject variable data in the target area using the nearest neighbour
    interpolation method.

    """
    results = get_sample_from_neighbour_info(
        'nn',
        near_information['target_area'].shape,
        variable['values'],
        near_information['valid_input_index'],
        near_information['valid_output_index'],
        near_information['index_array'],
        distance_array=near_information['distance_array'],
        fill_value=variable['fill_value'],
    )

    if len(results.shape) == 3:
        # Occurs when pyresample thinks the results are banded.
        results = np.squeeze(results, axis=2)

    return results


def get_resampling_functions() -> Dict:
    """Return a mapping of interpolation options to resampling functions. This
    dictionary is an alternative to using a four branched if, elif, else
    condition for both retrieving reprojection information and reprojected
    data.

    """
    return {
        'bilinear': {
            'get_information': get_bilinear_information,
            'get_results': get_bilinear_results,
        },
        'ewa': {
            'get_information': get_ewa_information,
            'get_results': partial(get_ewa_results, maximum_weight_mode=False),
        },
        'ewa-nn': {
            'get_information': get_ewa_information,
            'get_results': partial(get_ewa_results, maximum_weight_mode=True),
        },
        'near': {
            'get_information': get_near_information,
            'get_results': get_near_results,
        },
    }


def check_for_valid_interpolation(message_parameters: Dict, logger: Logger) -> None:
    """Ensure the interpolation supplied in the message parameters is one of
    the expected options.

    """
    resampling_functions = get_resampling_functions()

    if message_parameters['interpolation'] not in resampling_functions:
        valid_interpolations = ', '.join(
            [f'"{interpolation}"' for interpolation in resampling_functions]
        )

        logger.error(
            f'Interpolation option "{message_parameters["interpolation"]}" '
            f'must be one of {valid_interpolations}.'
        )
        raise ValueError(
            'Invalid value for interpolation type: '
            f'"{message_parameters["interpolation"]}".'
        )


def get_swath_definition(dataset: Dataset, coordinates: Tuple[str]) -> SwathDefinition:
    """Define the swath as specified by the associated longitude and latitude
    datasets. Note, the longitudes must be wrapped to the range:
    -180 < longitude < 180.

    """
    latitudes = get_coordinate_variable(dataset, coordinates, 'lat')
    longitudes = get_coordinate_variable(dataset, coordinates, 'lon')

    wrapped_lons, wrapped_lats = check_and_wrap(longitudes[:], latitudes[:])

    # EWA ll2cr requires 2-dimensional arrays for the swath coordinates:
    if len(wrapped_lons.shape) == 1:
        wrapped_lons = make_array_two_dimensional(wrapped_lons)
        wrapped_lats = make_array_two_dimensional(wrapped_lats)

    return SwathDefinition(lons=wrapped_lons, lats=wrapped_lats)


def get_reprojection_cache(parameters: Dict) -> Dict:
    """Return a cache for information to be shared between all variables with
    common coordinates. Additionally, check the input Harmony message for a
    complete definition of the target area. If that is present, return it
    in the initial cache under a key that should not be match a valid
    variable name in the input granule.

    """
    reprojection_cache = {}

    grid_extents = get_parameters_tuple(
        parameters, ['x_min', 'y_min', 'x_max', 'y_max']
    )
    dimensions = get_parameters_tuple(parameters, ['height', 'width'])
    resolutions = get_parameters_tuple(parameters, ['xres', 'yres'])
    projection_string = parameters['projection'].definition_string()

    if grid_extents is not None and (dimensions is not None or resolutions is not None):
        x_range = grid_extents[2] - grid_extents[0]
        y_range = grid_extents[1] - grid_extents[3]

        if dimensions is not None:
            resolutions = (x_range / dimensions[1], y_range / dimensions[0])
        else:
            width = abs(round(x_range / resolutions[0]))
            height = abs(round(y_range / resolutions[1]))

            dimensions = (height, width)

        target_area = AreaDefinition.from_extent(
            HARMONY_TARGET, projection_string, dimensions, grid_extents
        )

        reprojection_cache[HARMONY_TARGET] = {'target_area': target_area}

    return reprojection_cache


def get_target_area(
    parameters: Dict, dataset: Dataset, coordinates: Tuple[str], logger: Logger
) -> AreaDefinition:
    """Define the target area as specified by either a complete set of message
    parameters, or supplemented with coordinate variables as referred to in
    the science variable metadata.

    """
    grid_extents = get_parameters_tuple(
        parameters, ['x_min', 'y_min', 'x_max', 'y_max']
    )
    dimensions = get_parameters_tuple(parameters, ['height', 'width'])
    resolutions = get_parameters_tuple(parameters, ['xres', 'yres'])
    projection_string = parameters['projection'].definition_string()
    latitudes = get_coordinate_variable(dataset, coordinates, 'lat')
    longitudes = get_coordinate_variable(dataset, coordinates, 'lon')

    if grid_extents is not None:
        logger.info(
            f'Message x extent: x_min: {grid_extents[0]}, x_max: ' f'{grid_extents[2]}'
        )
        logger.info(
            f'Message y extent: y_min: {grid_extents[1]}, y_max: ' f'{grid_extents[3]}'
        )
    else:
        x_min, x_max, y_min, y_max = get_extents_from_perimeter(
            parameters['projection'], longitudes, latitudes
        )

        grid_extents = (x_min, y_min, x_max, y_max)
        logger.info(f'Calculated x extent: x_min: {x_min}, x_max: {x_max}')
        logger.info(f'Calculated y extent: y_min: {y_min}, y_max: {y_max}')

    x_range = grid_extents[2] - grid_extents[0]
    y_range = grid_extents[1] - grid_extents[3]

    if resolutions is None and dimensions is not None:
        resolutions = (x_range / dimensions[1], y_range / dimensions[0])
    elif resolutions is None:
        x_res = get_projected_resolution(
            parameters['projection'], longitudes, latitudes
        )
        # TODO: Determine sign of y resolution from projected y data.
        y_res = -1.0 * x_res
        resolutions = (x_res, y_res)
        logger.info(f'Calculated projected resolutions: ({x_res}, {y_res})')
    else:
        logger.info(
            f'Resolutions from message: ({resolutions[0]}, ' f'{resolutions[1]})'
        )

    if dimensions is None:
        width = abs(round(x_range / resolutions[0]))
        height = abs(round(y_range / resolutions[1]))
        logger.info(f'Calculated width: {width}')
        logger.info(f'Calculated height: {height}')
        dimensions = (height, width)

    return AreaDefinition.from_extent(
        ', '.join(coordinates), projection_string, dimensions, grid_extents
    )


def get_parameters_tuple(
    input_parameters: Dict, output_parameter_keys: List
) -> Optional[Tuple]:
    """Search the input Harmony message for the listed keys. If all of them
    are valid, return the parameter values, in the order originally listed.
    If any of the parameters are invalid, return `None`.

    This is specifically used to check all extent parameters (e.g. `x_min`,
    `x_max`, `y_min` and `y_max`), dimensions (e.g. `height` and `width`)
    or resolutions (e.g. `xres` and `yres`) are *all* valid.

    """
    output_values = tuple(
        input_parameters[output_parameter_key]
        for output_parameter_key in output_parameter_keys
    )

    if any((output_value is None for output_value in output_values)):
        output_values = None

    return output_values
