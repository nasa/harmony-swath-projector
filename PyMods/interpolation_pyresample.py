""" This module contains functions to perform interpolation on the science
    datasets within a file, using the pyresample Python package.

"""
from logging import Logger
from typing import Dict, List, Tuple
import os

from pyproj import Proj
from pyresample.bilinear import get_bil_info, get_sample_from_bil_info
from pyresample.ewa import fornav, ll2cr
from pyresample.geometry import AreaDefinition, SwathDefinition
from pyresample.kd_tree import get_neighbour_info, get_sample_from_neighbour_info
from xarray.core.dataset import Dataset
import numpy as np
import rasterio
import xarray

from PyMods.utilities import (create_coordinates_key, get_coordinate_variable,
                              get_variable_name, get_variable_values,
                              get_variables, is_coordinate_variable)


EPSILON = 0.5
FILL_VALUE = -9999.0
NEIGHBOURS = 16
RADIUS_OF_INFLUENCE = 50000


def resample_all_variables(message_parameters: Dict,
                           file_information: str,
                           temp_directory: str,
                           logger: Logger) -> List[str]:
    """ NOTE: file_information will likely change to a class from DAS-570.

        Returns:
            output_variables: A list of names of successfully reprojected
                variables.
    """
    output_extension = os.path.splitext(message_parameters['input_file'])[-1]
    reprojection_information = {}
    output_variables = []

    check_for_valid_interpolation(message_parameters, logger)

    target_area = get_target_area(message_parameters)
    dataset = xarray.open_dataset(message_parameters['input_file'], decode_cf=False)

    # TODO: DAS-570 integration: to replace get_variables with class method
    # on file_information, instead.
    for variable in get_variables(file_information):
        try:
            # TODO: DAS-570 integration: file_information will probably return
            # the name of the variable, so this could end up being a call to
            # get the variable, rather than the name.
            variable_name = get_variable_name(variable)

            if is_coordinate_variable(variable_name):
                logger.info(f'Skipping coordinate variable: "{variable_name}".')
                continue

            variable_output_path = os.sep.join([
                temp_directory,
                f'{variable_name.split("/")[-1]}{output_extension}'
            ])

            logger.info(f'Reprojecting subdataset "{variable_name}"')
            logger.info(f'Reprojected output: "{variable_output_path}"')

            resample_variable(message_parameters, dataset, variable_name,
                              reprojection_information, target_area,
                              variable_output_path, logger)

            output_variables.append(variable_name)
        except Exception as error:
            # Assume for now variable cannot be reprojected. TBD add checks for
            # other error conditions.
            logger.error(f'Cannot reproject {variable_name}')
            logger.error(error)

    return output_variables


def resample_variable(message_parameters: Dict, dataset: Dataset,
                      variable_name: str, reprojection_information: Dict,
                      target_area: AreaDefinition, variable_output_path: str,
                      logger: Logger) -> None:
    """ A wrapper function to redirect the variable being reprojected to a
        function specific to the interpolation option.

    """
    resampling_functions = get_resampling_functions()
    resampling_functions[message_parameters['interpolation']](message_parameters,
                                                              dataset,
                                                              variable_name,
                                                              reprojection_information,
                                                              target_area,
                                                              variable_output_path,
                                                              logger)


def pyresample_bilinear(message_parameters: Dict, dataset: Dataset,
                        variable_name: str, reprojection_information: Dict,
                        target_area: AreaDefinition, variable_output_path: str,
                        logger: Logger) -> None:
    """ Use bilinear interpolation to produce the target output. If the same
        source coordinates have been processed for a previous variable, use
        applicable information (from get_bil_info) rather than recreating it.

        Once the variable has been interpolated, output to a new NetCDF file,
        which will be merged with others after all variables have been
        interpolated.

    """
    variable = dataset.variables.get(variable_name)
    variable_values = get_variable_values(dataset, variable)
    coordinates = create_coordinates_key(variable.attrs.get('coordinates'))

    if coordinates in reprojection_information:
        logger.debug(f'Retrieving previous bilinear information for {variable_name}')
        bilinear_information = reprojection_information[coordinates]
    else:
        logger.debug(f'Calculating bilinear information for {variable_name}')
        swath_definition = get_swath_definition(dataset, coordinates)
        bilinear_info = get_bil_info(swath_definition,
                                     target_area,
                                     radius=RADIUS_OF_INFLUENCE,
                                     neighbours=NEIGHBOURS)

        bilinear_information = {'vertical_distances': bilinear_info[0],
                                'horizontal_distances': bilinear_info[1],
                                'valid_input_indices': bilinear_info[2],
                                'valid_point_mapping': bilinear_info[3]}

        reprojection_information[coordinates] = bilinear_information

    results = get_sample_from_bil_info(variable_values.ravel(),
                                       bilinear_information['vertical_distances'],
                                       bilinear_information['horizontal_distances'],
                                       bilinear_information['valid_input_indices'],
                                       bilinear_information['valid_point_mapping'],
                                       output_shape=target_area.shape)

    write_netcdf(variable_output_path,
                 results,
                 message_parameters['projection'],
                 message_parameters['grid_transform'])

    logger.debug(f'Saved {variable_name} output to temporary file: '
                 f'{variable_output_path}')


def pyresample_ewa(message_parameters: Dict, dataset: Dataset, variable_name: str,
                   reprojection_information: Dict, target_area: AreaDefinition,
                   variable_output_path: str, logger: Logger) -> None:
    """ Use Elliptical Weighted Average (EWA) interpolation to produce the
        target output. The `pyresample` EWA algorithm assumes that the data are
        presented one scan row at a time in the input array. If the same
        source coordinates have been processed for a previous variable, use
        applicable information (from ll2cr) rather than recreating it.

        Once the variable has been interpolated, output to a new NetCDF file,
        which will be merged with others after all variables have been
        interpolated.

    """
    variable = dataset.variables.get(variable_name)
    variable_values = get_variable_values(dataset, variable)
    coordinates = create_coordinates_key(variable.attrs.get('coordinates'))

    if coordinates in reprojection_information:
        logger.debug(f'Retrieving previous EWA information for {variable_name}')
        ewa_information = reprojection_information[coordinates]
    else:
        logger.debug(f'Calculating EWA information for {variable_name}')
        swath_definition = get_swath_definition(dataset, coordinates)
        ewa_info = ll2cr(swath_definition, target_area)

        ewa_information = {'columns': ewa_info[1], 'rows': ewa_info[2]}

        reprojection_information[coordinates] = ewa_information

    if np.issubdtype(variable_values.dtype, np.integer):
        variable_values = variable_values.astype(float)

    # This call falls back on the EWA rows_per_scan default of total input rows
    _, results = fornav(ewa_information['columns'], ewa_information['rows'],
                        target_area, variable_values)

    write_netcdf(variable_output_path,
                 results,
                 message_parameters['projection'],
                 message_parameters['grid_transform'])

    logger.debug(f'Saved {variable_name} output to temporary file: '
                 f'{variable_output_path}')


def pyresample_nearest_neighbour(message_parameters: Dict,
                                 dataset: Dataset,
                                 variable_name: str,
                                 reprojection_information: Dict,
                                 target_area: AreaDefinition,
                                 variable_output_path: str,
                                 logger: Logger) -> None:
    """ Use nearest neighbour interpolation to produce the target output. If
        the same source coordinates have been processed for a previous
        variable, use applicable information (from get_neighbour_info) rather
        than recreating it.

        Once the variable has been interpolated, output to a new NetCDF file,
        which will be merged with others after all variables have been
        interpolated.

    """
    variable = dataset.variables.get(variable_name)
    variable_values = get_variable_values(dataset, variable)
    coordinates = create_coordinates_key(variable.attrs.get('coordinates'))

    if coordinates in reprojection_information:
        logger.debug('Retrieving previous nearest neighbour information for '
                     f'{variable_name}')
        near_information = reprojection_information[coordinates]
    else:
        logger.debug('Calculating nearest neighbour information for '
                     f'{variable_name}')
        swath_definition = get_swath_definition(dataset, coordinates)
        near_info = get_neighbour_info(swath_definition, target_area,
                                       RADIUS_OF_INFLUENCE, epsilon=EPSILON,
                                       neighbours=1)

        near_information = {'valid_input_index': near_info[0],
                            'valid_output_index': near_info[1],
                            'index_array': near_info[2],
                            'distance_array': near_info[3]}

        reprojection_information[coordinates] = near_information

    results = get_sample_from_neighbour_info(
        'nn', target_area.shape, variable_values,
        near_information['valid_input_index'],
        near_information['valid_output_index'],
        near_information['index_array'],
        distance_array=near_information['distance_array'],
        fill_value=FILL_VALUE
    )

    write_netcdf(variable_output_path,
                 results,
                 message_parameters['projection'],
                 message_parameters['grid_transform'])

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
    return {'bilinear': pyresample_bilinear,
            'ewa': pyresample_ewa,
            'near': pyresample_nearest_neighbour}


def check_for_valid_interpolation(message_parameters: Dict, logger: Logger) -> None:
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


def get_swath_definition(dataset: Dataset, coordinates: Tuple[str]) -> SwathDefinition:
    """ Define the swath as specified by the root longitude and latitude
        datasets.

    """
    latitudes = get_coordinate_variable(dataset, coordinates, 'lat')
    longitudes = get_coordinate_variable(dataset, coordinates, 'lon')
    return SwathDefinition(lons=longitudes, lats=latitudes)


def get_target_area(parameters: Dict) -> AreaDefinition:
    """ From the provided message parameters, derive the target area being
        interpolated to.

    """
    grid_extent = (parameters['x_min'], parameters['y_min'],
                   parameters['x_max'], parameters['y_max'])

    return AreaDefinition.from_extent('target_grid',
                                      parameters['projection'].definition_string(),
                                      (parameters['height'], parameters['width']),
                                      grid_extent)
