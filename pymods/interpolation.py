""" This module contains functions to perform interpolation on the science
    datasets within a file, using the pyresample Python package.

"""
from logging import Logger
from typing import Dict, List, Optional, Tuple
import os

from pyproj import Proj
from pyresample.bilinear import get_bil_info, get_sample_from_bil_info
from pyresample.ewa import fornav, ll2cr
from pyresample.geometry import AreaDefinition, SwathDefinition
from pyresample.kd_tree import get_neighbour_info, get_sample_from_neighbour_info
from rasterio.transform import Affine
from xarray.core.dataset import Dataset
import numpy as np
import rasterio
import xarray

from pymods.swotrepr_geometry import (get_extents_from_perimeter,
                                      get_projected_resolution)
from pymods.utilities import (create_coordinates_key, get_coordinate_variable,
                              get_variable_file_path,
                              get_variable_group_and_name,
                              get_variable_numeric_fill_value,
                              get_variable_values)


EPSILON = 0.5
NEIGHBOURS = 16
RADIUS_OF_INFLUENCE = 50000


def resample_all_variables(message_parameters: Dict,
                           science_variables: List[str],
                           temp_directory: str,
                           logger: Logger) -> List[str]:
    """ Iterate through all science variables and reproject to the target
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
            variable_output_path = get_variable_file_path(temp_directory,
                                                          variable,
                                                          output_extension)

            logger.info(f'Reprojecting variable "{variable}"')
            logger.info(f'Reprojected output: "{variable_output_path}"')

            resample_variable(message_parameters, variable,
                              reprojection_cache, variable_output_path,
                              logger)

            output_variables.append(variable)
        except Exception as error:
            # Assume for now variable cannot be reprojected. TBD add checks for
            # other error conditions.
            logger.error(f'Cannot reproject {variable}')
            logger.error(error)

    return output_variables


def resample_variable(message_parameters: Dict, full_variable: str,
                      reprojection_cache: Dict, variable_output_path: str,
                      logger: Logger) -> None:
    """ A wrapper function to redirect the variable being reprojected to a
        function specific to the interpolation option.

    """
    resampling_functions = get_resampling_functions()
    resampling_functions[message_parameters['interpolation']](
        message_parameters,
        full_variable,
        reprojection_cache,
        variable_output_path,
        logger
    )


def bilinear(message_parameters: Dict, full_variable: str,
             reprojection_cache: Dict, variable_output_path: str,
             logger: Logger) -> None:
    """ Use bilinear interpolation to produce the target output. If the same
        source coordinates have been processed for a previous variable, use
        applicable information (from get_bil_info) rather than recreating it.

        Once the variable has been interpolated, it is saved to a new NetCDF
        file, which will be merged with others after all variables have been
        interpolated.

    """
    # NOTE: DAS-599 will replace xarray with netCDF4. At that point some of
    # these lines of code can be extracted out into a new function to remove
    # repetition.
    variable_group, variable_name = get_variable_group_and_name(full_variable)
    dataset = xarray.open_dataset(message_parameters['input_file'],
                                  decode_cf=False,
                                  group=variable_group)

    variable = dataset.variables.get(variable_name)
    variable_values = get_variable_values(dataset, variable)
    coordinates_key = create_coordinates_key(variable.attrs.get('coordinates'))

    if coordinates_key in reprojection_cache:
        logger.debug(f'Retrieving previous bilinear information for {variable_name}')
        bilinear_information = reprojection_cache[coordinates_key]
    else:
        logger.debug(f'Calculating bilinear information for {variable_name}')

        if 'harmony_message_target' in reprojection_cache:
            logger.debug('Using target area defined in Harmony message.')
            target_info = reprojection_cache['harmony_message_target']
        else:
            logger.debug('Deriving target area from associated coordinates.')
            target_info = get_target_area(message_parameters, dataset,
                                          coordinates_key, logger)

        swath_definition = get_swath_definition(dataset, coordinates_key)
        bilinear_info = get_bil_info(swath_definition,
                                     target_info['target_area'],
                                     radius=RADIUS_OF_INFLUENCE,
                                     neighbours=NEIGHBOURS)

        bilinear_information = {'vertical_distances': bilinear_info[0],
                                'horizontal_distances': bilinear_info[1],
                                'valid_input_indices': bilinear_info[2],
                                'valid_point_mapping': bilinear_info[3]}

        # Store target area information, too. If the Harmony message has a
        # fully defined target area, the target area information cached within
        # the coordinate key entry will only be a reference to the Harmony
        # message target area objects, not copies of the objects themselves.
        bilinear_information.update(target_info)

        reprojection_cache[coordinates_key] = bilinear_information

    results = get_sample_from_bil_info(
        variable_values.ravel(),
        bilinear_information['vertical_distances'],
        bilinear_information['horizontal_distances'],
        bilinear_information['valid_input_indices'],
        bilinear_information['valid_point_mapping'],
        output_shape=bilinear_information['target_area'].shape
    )

    write_netcdf(variable_output_path,
                 results,
                 message_parameters['projection'],
                 bilinear_information['grid_transform'])

    logger.debug(f'Saved {variable_name} output to temporary file: '
                 f'{variable_output_path}')


def ewa_helper(message_parameters: Dict, full_variable: str,
               reprojection_cache: Dict, variable_output_path: str,
               logger: Logger, maximum_weight_mode: bool) -> None:
    """ Use Elliptical Weighted Average (EWA) interpolation to produce the
        target output. The `pyresample` EWA algorithm assumes that the data are
        presented one scan row at a time in the input array. If the same
        source coordinates have been processed for a previous variable, use
        applicable information (from ll2cr) rather than recreating it.

        If maximum_weight_mode is False, a weighted average of all swath cells
        that map to a particular grid cell is used. If True, the swath cell
        having the maximum weight of all swath cells that map to a particular
        grid cell is used, instead of a weighted average. This is a
        'nearest-neighbour' style interpolation, but accounts for pixels within
        the same scan line being more closely related than those from different
        scans.

        Once the variable has been interpolated, it is saved to a new NetCDF
        file, which will be merged with others after all variables have been
        interpolated.

    """
    # NOTE: See note on DAS-599 in `bilinear` function.
    variable_group, variable_name = get_variable_group_and_name(full_variable)
    dataset = xarray.open_dataset(message_parameters['input_file'],
                                  decode_cf=False,
                                  group=variable_group)

    variable = dataset.variables.get(variable_name)
    variable_values = get_variable_values(dataset, variable)
    coordinates_key = create_coordinates_key(variable.attrs.get('coordinates'))

    if coordinates_key in reprojection_cache:
        logger.debug(f'Retrieving previous EWA information for {variable_name}')
        ewa_information = reprojection_cache[coordinates_key]
    else:
        logger.debug(f'Calculating EWA information for {variable_name}')

        if 'harmony_message_target' in reprojection_cache:
            logger.info('Using target area defined in Harmony message.')
            target_info = reprojection_cache['harmony_message_target']
        else:
            logger.debug('Deriving target area from associated coordinates.')
            target_info = get_target_area(message_parameters, dataset,
                                          coordinates_key, logger)

        swath_definition = get_swath_definition(dataset, coordinates_key)
        ewa_info = ll2cr(swath_definition, target_info['target_area'])

        ewa_information = {'columns': ewa_info[1], 'rows': ewa_info[2]}
        ewa_information.update(target_info)

        # Store target area information, too. If the Harmony message has a
        # fully defined target area, the target area information cached within
        # the coordinate key entry will only be a reference to the Harmony
        # message target area objects, not copies of the objects themselves.
        reprojection_cache[coordinates_key] = ewa_information

    if np.issubdtype(variable_values.dtype, np.integer):
        variable_values = variable_values.astype(float)

    # This call falls back on the EWA rows_per_scan default of total input rows
    # and ignores the quality status return value
    _, results = fornav(ewa_information['columns'], ewa_information['rows'],
                        ewa_information['target_area'], variable_values,
                        maximum_weight_mode=maximum_weight_mode)

    write_netcdf(variable_output_path,
                 results,
                 message_parameters['projection'],
                 ewa_information['grid_transform'])

    logger.debug(f'Saved {variable_name} output to temporary file: '
                 f'{variable_output_path}')


def ewa(message_parameters: Dict, full_variable: str, reprojection_cache: Dict,
        variable_output_path: str, logger: Logger) -> None:
    """ Use Elliptical Weighted Average (EWA) interpolation to produce the
            target output. A weighted average of all swath cells that map
            to a particular grid cell is used.
    """
    ewa_helper(message_parameters, full_variable, reprojection_cache,
               variable_output_path, logger, maximum_weight_mode=False)


def ewa_nn(message_parameters: Dict, full_variable: str,
           reprojection_cache: Dict, variable_output_path: str,
           logger: Logger) -> None:
    """ Use Elliptical Weighted Average (EWA) interpolation to produce the
            target output. The swath cell having the maximum weight of all
            swath cells that map to a particular grid cell is used.
    """
    ewa_helper(message_parameters, full_variable, reprojection_cache,
               variable_output_path, logger, maximum_weight_mode=True)


def nearest_neighbour(message_parameters: Dict, full_variable: str,
                      reprojection_cache: Dict, variable_output_path: str,
                      logger: Logger) -> None:
    """ Use nearest neighbour interpolation to produce the target output. If
        the same source coordinates have been processed for a previous
        variable, use applicable information (from get_neighbour_info) rather
        than recreating it.

        Once the variable has been interpolated, it is saved to a new NetCDF
        file, which will be merged with others after all variables have been
        interpolated.

    """
    # NOTE: See note on DAS-599 in `bilinear` function.
    variable_group, variable_name = get_variable_group_and_name(full_variable)
    dataset = xarray.open_dataset(message_parameters['input_file'],
                                  decode_cf=False, group=variable_group)

    variable = dataset.variables.get(variable_name)
    variable_values = get_variable_values(dataset, variable)
    variable_fill_value = get_variable_numeric_fill_value(variable)
    coordinates_key = create_coordinates_key(variable.attrs.get('coordinates'))

    if coordinates_key in reprojection_cache:
        logger.debug('Retrieving previous nearest neighbour information for '
                     f'{variable_name}')
        near_information = reprojection_cache[coordinates_key]
    else:
        logger.debug('Calculating nearest neighbour information for '
                     f'{variable_name}')

        if 'harmony_message_target' in reprojection_cache:
            logger.debug('Using target area defined in Harmony message.')
            target_info = reprojection_cache['harmony_message_target']
        else:
            logger.debug('Deriving target area from associated coordinates.')
            target_info = get_target_area(message_parameters, dataset,
                                          coordinates_key, logger)

        swath_definition = get_swath_definition(dataset, coordinates_key)
        near_info = get_neighbour_info(swath_definition,
                                       target_info['target_area'],
                                       RADIUS_OF_INFLUENCE, epsilon=EPSILON,
                                       neighbours=1)

        near_information = {'valid_input_index': near_info[0],
                            'valid_output_index': near_info[1],
                            'index_array': near_info[2],
                            'distance_array': near_info[3]}

        # Store target area information, too. If the Harmony message has a
        # fully defined target area, the target area information cached within
        # the coordinate key entry will only be a reference to the Harmony
        # message target area objects, not copies of the objects themselves.
        near_information.update(target_info)

        reprojection_cache[coordinates_key] = near_information

    results = get_sample_from_neighbour_info(
        'nn', near_information['target_area'].shape, variable_values,
        near_information['valid_input_index'],
        near_information['valid_output_index'],
        near_information['index_array'],
        distance_array=near_information['distance_array'],
        fill_value=variable_fill_value
    )

    write_netcdf(variable_output_path,
                 results,
                 message_parameters['projection'],
                 near_information['grid_transform'])

    logger.debug(f'Saved {variable_name} output to temporary file: '
                 f'{variable_output_path}')


def write_netcdf(file_name: str, data: np.ndarray, projection: Proj, transform):
    """ Write the results from reprojecting a single variable to a NetCDF file.

    """
    target_crs_dict = projection.crs.to_dict()
    with rasterio.open(file_name,
                       'w',
                       driver='NetCDF',
                       height=data.shape[0],
                       width=data.shape[1],
                       count=1,
                       dtype=data.dtype,
                       crs=target_crs_dict,
                       transform=transform) as netcdf_container:
        netcdf_container.write(data, 1)  # first (and only) band


def get_resampling_functions() -> Dict:
    """Return a mapping of interpolation options to resampling functions."""
    return {'bilinear': bilinear,
            'ewa': ewa,
            'ewa-nn': ewa_nn,
            'near': nearest_neighbour}


def check_for_valid_interpolation(message_parameters: Dict,
                                  logger: Logger) -> None:
    """ Ensure the interpolation supplied in the message parameters is one of
        the expected options.

    """
    resampling_functions = get_resampling_functions()

    if message_parameters['interpolation'] not in resampling_functions:
        valid_interpolations = ', '.join([f'"{interpolation}"'
                                          for interpolation
                                          in resampling_functions])

        logger.error(f'Interpolation option "{message_parameters["interpolation"]}" '
                     f'must be one of {valid_interpolations}.')
        raise ValueError('Invalid value for interpolation type: '
                         f'"{message_parameters["interpolation"]}".')


def get_swath_definition(dataset: Dataset,
                         coordinates: Tuple[str]) -> SwathDefinition:
    """ Define the swath as specified by the root longitude and latitude
        datasets.

    """
    latitudes = get_coordinate_variable(dataset, coordinates, 'lat')
    longitudes = get_coordinate_variable(dataset, coordinates, 'lon')
    return SwathDefinition(lons=longitudes, lats=latitudes)


def get_reprojection_cache(parameters: Dict) -> Dict:
    """ Return a cache for information to be shared between all variables with
        common coordinates. Additionally, check the input Harmony message for a
        complete definition of the target area. If that is present, return it
        in the initial cache under a key that should not be match a valid
        variable name in the input granule.

    """
    reprojection_cache = {}

    grid_extents = get_parameters_tuple(parameters,
                                        ['x_min', 'y_min', 'x_max', 'y_max'])
    dimensions = get_parameters_tuple(parameters, ['height', 'width'])
    resolutions = get_parameters_tuple(parameters, ['xres', 'yres'])
    projection_string = parameters['projection'].definition_string()

    if grid_extents is not None and (dimensions is not None or
                                     resolutions is not None):
        x_range = grid_extents[2] - grid_extents[0]
        y_range = grid_extents[1] - grid_extents[3]

        if dimensions is not None:
            resolutions = (x_range / dimensions[1], y_range / dimensions[0])
        else:
            width = abs(round(x_range / resolutions[0]))
            height = abs(round(y_range / resolutions[1]))

            dimensions = (height, width)

        # Gdal GeoTransform and Affine matrices are just different ways of
        # capturing the grid extents and resolution in single data object. Gdal
        # GeoTransform is one way, which we can create given our capture of
        # grid_extents and resolution) and then turn into Affine matrix. Grid
        # Transforms are used to compute a projected coordinate set from cell
        # x & y index values"
        grid_transform = Affine.from_gdal(grid_extents[0], resolutions[0], 0.0,
                                          grid_extents[3], 0.0, resolutions[1])

        target_area = AreaDefinition.from_extent('target_grid',
                                                 projection_string,
                                                 dimensions,
                                                 grid_extents)

        reprojection_cache['harmony_message_target'] = {
            'grid_transform': grid_transform,
            'target_area': target_area,
        }

    return reprojection_cache


def get_target_area(parameters: Dict, dataset: Dataset,
                    coordinates: Tuple[str], logger: Logger) -> Dict:
    """ Define the target area as specified by either a complete set of message
        parameters, or supplemented with coordinate variables as refered to in
        the science variable metadata.

    """
    grid_extents = get_parameters_tuple(parameters,
                                        ['x_min', 'y_min', 'x_max', 'y_max'])
    dimensions = get_parameters_tuple(parameters, ['height', 'width'])
    resolutions = get_parameters_tuple(parameters, ['xres', 'yres'])
    projection_string = parameters['projection'].definition_string()
    latitudes = get_coordinate_variable(dataset, coordinates, 'lat')
    longitudes = get_coordinate_variable(dataset, coordinates, 'lon')

    if grid_extents is not None:
        logger.info(f'Message x extent: x_min: {grid_extents[0]}, x_max: '
                    f'{grid_extents[2]}')
        logger.info(f'Message y extent: y_min: {grid_extents[1]}, y_max: '
                    f'{grid_extents[3]}')
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
        x_res = get_projected_resolution(parameters['projection'], longitudes,
                                         latitudes)
        # TODO: Determine sign of y resolution from projected y data.
        y_res = -1.0 * x_res
        resolutions = (x_res, y_res)
        logger.info(f'Calculated projected resolutions: ({x_res}, {y_res})')
    else:
        logger.info(f'Resolutions from message: ({resolutions[0]}, '
                    f'{resolutions[1]})')

    if dimensions is None:
        width = abs(round(x_range / resolutions[0]))
        height = abs(round(y_range / resolutions[1]))
        logger.info(f'Calculated width: {width}')
        logger.info(f'Calculated height: {height}')
        dimensions = (height, width)

    target_area = AreaDefinition.from_extent('target_grid', projection_string,
                                             dimensions, grid_extents)

    grid_transform = Affine.from_gdal(grid_extents[0], resolutions[0], 0.0,
                                      grid_extents[3], 0.0, resolutions[1])

    return {'grid_transform': grid_transform, 'target_area': target_area}


def get_parameters_tuple(input_parameters: Dict,
                         output_parameter_keys: List) -> Optional[Tuple]:
    """ Search the input Harmony message for the listed keys. If all of them
        are valid, return the parameter values, in the order originally listed.
        If any of the parameters are invalid, return `None`.

        This is specifically used to check all extent parameters (e.g. `x_min`,
        `x_max`, `y_min` and `y_max`), dimensions (e.g. `height` and `width`)
        or resolutions (e.g. `xres` and `yres`) are *all* valid.

    """
    output_values = tuple(input_parameters[output_parameter_key]
                          for output_parameter_key in output_parameter_keys)

    if any((output_value is None for output_value in output_values)):
        output_values = None

    return output_values
