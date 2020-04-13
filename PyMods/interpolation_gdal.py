from logging import Logger
from typing import Dict, List
import os
import subprocess

import xarray

from PyMods.utilities import get_variable_group_and_name


def gdal_resample_all_variables(message_parameters: Dict,
                                science_variables: List[str],
                                temp_directory: str,
                                logger: Logger):
    """ This function opens the specified granule, identifies all variables
        and then iterates through all the variables to run gdalwarp. The
        attempt to reproject each variable is wrapped in its own try/except
        block, ensuring that as mant variables as possible are reprojected.

        Returns:
            output_variables: A list of file paths for the individually
                reprojected variables.
    """
    output_extension = os.path.splitext(message_parameters['input_file'])[-1]
    output_variables = []

    for variable in science_variables:
        try:
            _, variable_name = get_variable_group_and_name(variable)

            variable_output_path = os.sep.join([
                temp_directory, f'{variable_name}{output_extension}'
            ])

            logger.info(f'Reprojecting subdataset "{variable_name}"')
            logger.info(f'Reprojected output "{variable_output_path}"')

            gdal_resample(message_parameters, variable, variable_output_path, logger)

            output_variables.append(variable_name)
        except Exception as err:
            # Assume for now variable cannot be reprojected. TBD add checks for
            # other error conditions.
            logger.info(f'Cannot reproject {variable_name}')
            logger.info(err)

    return output_variables


def gdal_resample(parameters: Dict, variable: str, output_file: str,
                  logger: Logger):
    """ Construct a command for running gdalwarp on a single variable, using
        the input parameters specified by the input message. This command is
        then executed, which results in a saved NetCDF4 file for that single
        variable.

    """
    #TODO: rework to accomodate new parameter handling re. undefined or None
    gdal_cmd = ['gdalwarp', '-geoloc', '-t_srs', parameters.get('crs')]
    if (
            parameters.get('interpolation') and
            parameters.get('interpolation') != 'ewa'
    ):
        gdal_cmd.extend(['-r', parameters.get('interpolation')])
        logger.info(f'Selected interpolation: {parameters.get("interpolation")}')

    if parameters.get('x_extent') and parameters.get('y_extent'):
        gdal_cmd.extend(['-te',
                         str(parameters.get('x_min')),
                         str(parameters.get('y_min')),
                         str(parameters.get('x_max')),
                         str(parameters.get('y_max'))])

        logger.info(f'Selected scale extent: {parameters.get("x_min")} '
                    f'{parameters.get("y_min")} {parameters.get("x_max")} '
                    f'{parameters.get("y_max")}')

    if parameters.get('xres') and parameters.get('yres'):
        gdal_cmd.extend(['-tr',
                         str(parameters.get('xres')),
                         str(parameters.get('yres'))])

        logger.info(f'Selected scale size: {parameters.get("xres")} '
                    f'{parameters.get("yres")}')

    if parameters.get('width') and parameters.get('height'):
        gdal_cmd.extend(['-ts',
                         str(parameters.get('width')),
                         str(parameters.get('height'))])

        logger.info(f'Selected width: {parameters.get("width")}')
        logger.info(f'Selected height: {parameters.get("height")}')

    full_variable = create_gdal_variable_name('NETCDF',
                                              parameters['input_file'],
                                              variable)

    gdal_cmd.extend([full_variable, output_file])
    logger.info(f'Running GDAL command: {" ".join(gdal_cmd)}')
    results_str = subprocess.check_output(gdal_cmd, stderr=subprocess.STDOUT).decode('utf-8')
    logger.info(f'GDAL output:\n{results_str}')


def create_gdal_variable_name(file_format: str, file_name: str,
                              variable_name: str) -> str:
    """ Construct the full variable name required for gdalwarp to process the
    science variable.

    """
    return f'{file_format}:"{file_name}":{variable_name}'
