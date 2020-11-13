""" Reprojection support for merging single-dataset NetCDF-4 files, produced by
    `pyresample`, back into a single output file with all the necessary
    attributes.
"""
from argparse import ArgumentParser
from typing import Dict, Optional, Set, Tuple, Union
import logging
import os
import re
import warnings

import netCDF4
import numpy as np

from pymods.exceptions import MissingReprojectedDataError
from pymods.utilities import get_variable_file_path

GDAL_VARIABLE_NAME = 'Band1'

STD_COOR_ATTRS = {  # only for non-geographic projection case, i.e. not lat/lon
    'x': {'long_name': 'x coordinate of projection',
          'units': 'm',
          'standard_name': 'projection_x_coordinate'},
    'y': {'long_name': 'y coordinate of projection',
          'units': 'm',
          'standard_name': 'projection_y_coordinate'}
}


def create_output(input_file: str, output_file: str, temp_dir: str,
                  science_variables: Set[str],
                  metadata_variables: Set[str],
                  logger: Optional[logging.Logger] = None) -> None:
    """ Merging the reprojected single-dataset netCDF4 files from `pyresample`
        into a NETCDF-4 file, copying global attributes and metadata
        variables (those without coordinates, which therefore can't be
        reprojected) from the original input file. Then for each listed science
        variable, retrieve the single-band file and copy the reprojected
        variables, and any accompanying CRS and coordinate datasets. Note, the
        coordinate datasets will only be copied once.

    """

    if not logger:
        logger = logging.getLogger(__name__)

    logger.info(f'Creating output file "{output_file}"')

    with netCDF4.Dataset(input_file) as input_dataset, \
         netCDF4.Dataset(output_file, 'w', format='NETCDF4') as output_dataset:

        logger.info('Copying input file attributes to output file.')
        output_dataset.setncatts(read_attrs(input_dataset))

        if has_time_dimension(input_dataset):
            copy_time_dimension(input_dataset, output_dataset, logger)

        for metadata_variable in metadata_variables:
            copy_metadata_variable(input_dataset, output_dataset,
                                   metadata_variable, logger)

        output_extension = os.path.splitext(input_file)[1]

        for variable_name in science_variables:
            dataset_file = get_variable_file_path(temp_dir, variable_name,
                                                  output_extension)

            if os.path.isfile(dataset_file):
                with netCDF4.Dataset(dataset_file) as data:
                    set_dimension(data, output_dataset)

                    # TODO: DAS-599, when single band output has proper variable
                    # name, can use a single loop over all data.variables,
                    # only checking the variable isn't already present in the
                    # output.
                    copy_variable(input_dataset, output_dataset, data,
                                  variable_name, logger)

                    # Note: This assumes single band output files contain
                    # coordinates and CRS information in the root of the dataset.
                    for variable_key in data.variables:
                        if (
                                variable_key not in output_dataset.variables and
                                variable_key != GDAL_VARIABLE_NAME
                        ):
                            copy_variable(input_dataset, output_dataset, data,
                                          variable_key, logger)

            else:
                logger.error(f'Cannot find "{dataset_file}".')
                raise MissingReprojectedDataError(variable_name)

        # if 'crs' exists in output, rename it to the grid_mapping_name
        # and update grid_mapping attributes
        if 'crs' in output_dataset.variables:
            new_crs_name = output_dataset['crs'].grid_mapping_name
            output_dataset.renameVariable('crs', new_crs_name)
            for name, var in output_dataset.variables.items():
                # avoid the new crs var itself, replace grid_mapping attribute
                if name != new_crs_name and hasattr(var, 'grid_mapping'):
                    var.grid_mapping = new_crs_name


def read_attrs(dataset: Union[netCDF4.Dataset, netCDF4.Variable]) -> Dict:
    """ Read attributes from either a NetCDF4 Dataset or variable object. """
    return dataset.__dict__


def has_time_dimension(dataset: netCDF4.Dataset) -> bool:
    """check if time dimension exists"""
    return 'time' in dataset.dimensions


def copy_time_dimension(input_dataset: netCDF4.Dataset,
                        output_dataset: netCDF4.Dataset,
                        logger: logging.Logger) -> None:
    """add time dimension to the output file"""
    logger.info('Adding "time" dimension.')
    time_variable = input_dataset['time']
    output_dataset.createDimension('time', len(time_variable))
    copy_metadata_variable(input_dataset, output_dataset, 'time', logger)


def set_dimension(input_dataset: netCDF4.Dataset,
                  output_dataset: netCDF4.Dataset) -> None:
    """ Check single band intermediate file dimensions, and add them to the
        output dataset, if they are not already present.

    """
    for name, dimension in input_dataset.dimensions.items():
        if not (dimension.isunlimited() or name in output_dataset.dimensions):
            output_dataset.createDimension(name, len(dimension))


def copy_metadata_variable(input_dataset: netCDF4.Dataset,
                           output_dataset: netCDF4.Dataset, variable_name: str,
                           logger: logging.Logger) -> None:
    """ Write a metadata variable directly from the input dataset. These
        variables have not been reprojected as they contain no references to
        dimensions or coordinate datasets.

    """
    # TODO: Account for dimensions - potential conflicts between original and
    # reprojected dimension names.
    logger.info(f'Adding input file variable "{variable_name}" to the output.')
    variable = input_dataset[variable_name]
    data_type = input_dataset[variable_name].datatype
    attributes = read_attrs(variable)
    fill_value = get_fill_value_from_attributes(attributes)

    output_dataset.createVariable(variable_name, data_type,
                                  fill_value=fill_value, zlib=True,
                                  complevel=6)

    output_dataset[variable_name][:] = variable[:]
    output_dataset[variable_name].setncatts(attributes)


def copy_variable(input_dataset: netCDF4.Dataset,
                  output_dataset: netCDF4.Dataset,
                  single_band_output: netCDF4.Dataset,
                  variable_name: str, logger: logging.Logger) -> None:
    """ Write a reprojected variable from a single-band output file to the
        merged output file. This will first obtain metadata (dimensions,
        data type and  attributes) from either the single-band output, or from
        the original input file dataset. Then the variable values from the
        single-band output are copied into the data arrays. If the dataset
        attributes include a scale and offset, the output values are adjusted
        accordingly.

    """
    logger.info(f'Adding reprojected "{variable_name}" to the output')

    # set data type, dimensions, and attributes
    dims, data_type, attrs = get_dataset_meta(input_dataset,
                                              single_band_output,
                                              variable_name)
    fill_value = get_fill_value_from_attributes(attrs)

    # NOTE: DAS-599 will probably make variable name the actual name in the
    # single band output (instead of "Band1"), so this logic may be removable.
    if variable_name not in single_band_output.variables:
        ori_variable_name = GDAL_VARIABLE_NAME
    else:
        ori_variable_name = variable_name

    output_dataset.createVariable(variable_name, data_type, dimensions=dims,
                                  fill_value=fill_value, zlib=True,
                                  complevel=6)

    output_dataset[variable_name].setncatts(attrs)

    # Manually compute the data value if offset and scale_factor exist for
    # integers. This is necessary so that the netCDF4 library can recompute the
    # integer value from the science value. The library does not support
    # directly providing the integer value when offset and scale_factor are
    # defined.

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', category=UserWarning)
        if (
                single_band_output[ori_variable_name].shape !=
                output_dataset[variable_name].shape
        ):
            reshaped = single_band_output[ori_variable_name][:].reshape(
                output_dataset[variable_name].shape
            )
            if 'add_offset' in attrs and 'scale_factor' in attrs:
                reshaped = np.add(
                    np.multiply(reshaped,
                                output_dataset[variable_name].scale_factor),
                    output_dataset[variable_name].add_offset
                )

            output_dataset[variable_name][:] = reshaped
        else:
            output_dataset[variable_name][:] = single_band_output[ori_variable_name][:]


def get_dataset_meta(input_dataset: netCDF4.Dataset,
                     single_band_output: netCDF4.Dataset,
                     variable_name: str) -> Tuple[Tuple, np.dtype, Dict]:
    """ Extract variable metadata. If a variable with the science variable's
        name is present in the single band, reprojected output file, then use
        the data type, dimensions and attributes from that output, otherwise
        use the same information from the un-projected variable in the input
        granule.

        Prior to DAS-599, it is expected that the reprojected science variable
        will be called `GDAL_VARIABLE_NAME` (Band1) in the single band file.

    """
    # NOTE: DAS-599 will probably make variable name the actual name in the
    # single band output (instead of "Band1"), so this logic will be removable.
    if GDAL_VARIABLE_NAME in single_band_output.variables:
        single_band_name = GDAL_VARIABLE_NAME
    else:
        single_band_name = variable_name

    # TODO: refactor to properly address merging dimensions and reprojected dimensions ?
    # TODO: at least add commentary
    # NOTE: This condition below will become true when addressing DAS-599.
    # Should decide which file should take precedence: input or single band output?
    if variable_name in single_band_output.variables:
        data_type = single_band_output[variable_name].datatype
        dims = get_dimensions(single_band_output, variable_name)

        if variable_name in input_dataset.variables:
            attrs = read_attrs(input_dataset[variable_name])
        else:
            attrs = read_attrs(single_band_output[variable_name])

        if variable_name in STD_COOR_ATTRS:
            attrs.update(STD_COOR_ATTRS[variable_name])

    else:
        data_type = input_dataset[variable_name].datatype
        dims = get_dimensions(single_band_output, single_band_name,
                              input_dataset)
        attrs = read_attrs(input_dataset[variable_name])

        if single_band_output[single_band_name].grid_mapping:
            attrs['grid_mapping'] = single_band_output[single_band_name].grid_mapping

    # remove coordinates attribute if it is no longer valid
    if 'coordinates' in attrs and not check_coor_valid(attrs, input_dataset,
                                                       single_band_output):
        del attrs['coordinates']

    return dims, data_type, attrs


def get_dimensions(single_band_dataset: netCDF4.Dataset, variable_name: str,
                   input_dataset: netCDF4.Dataset = None) -> Tuple[str]:
    """ Retrieve the dimensions from the single-band reprojected dataset. If
        the original input dataset is included in the function call, then check
        that dataset for the time dimension, too.

        If the variable has no dimensions (e.g. is a scalar), an empty tuple
        will be returned, which is the default value for the `dimensions`
        keyword argument in the `netCDF4.createVariable` function.

    """
    # TODO: refactor to properly address merging dimensions and reprojected dimensions ?
    # NOTE: DAS-599 will remove GDAL_VARIABLE_NAME, so will become variable_name
    if input_dataset is None or 'time' not in input_dataset.dimensions:
        dimensions = single_band_dataset[variable_name].dimensions
    else:
        dimensions = ('time',) + single_band_dataset[variable_name].dimensions

    if len(dimensions) == 0 and single_band_dataset[variable_name].size > 1:
        # This variable is a dimension variable, and should refer to itself.
        dimensions = (variable_name,)

    return dimensions


def check_coor_valid(attrs: Dict, input_dataset: netCDF4.Dataset,
                     single_band_dataset: netCDF4.Dataset) -> bool:
    """ Check if variables listed in the coordinates metadata attributes are
        still valid after reprojection. Invalid coordinate reference cases:

          1) Coordinate variable listed in attribute does not exist in single
             band output dataset.
          2) Coordinate variable array shape in the reprojected, single-band
             dataset does not match the input coordinate array shape.

    """
    coordinates_attribute = attrs.get('coordinates')

    if coordinates_attribute is not None:
        # TODO: DAS-900 Fully qualify these coordinate paths
        coors = re.split(r'\s+|,\s*', coordinates_attribute)
    else:
        coors = []

    if not set(coors).issubset(single_band_dataset.variables.keys()):
        # Coordinates from original variable aren't all present in reprojected
        # output (single band file).
        valid = False
    else:
        valid = all(single_band_dataset[coord].shape == input_dataset[coord].shape
                    for coord in coors)

    return valid


def get_fill_value_from_attributes(variable_attributes: Dict) -> Optional:
    """ Check attributes for _FillValue. If present return the value and
        remove the _FillValue attribute from the input dictionary. Otherwise
        return None.

    """
    return variable_attributes.pop('_FillValue', None)


# main program
if __name__ == "__main__":
    PARSER = ArgumentParser(prog='nc_merge',
                            description='Merge reprojected NetCDF4 files into one')
    PARSER.add_argument('--ori-inputfile', dest='ori_inputfile',
                        help='Source NetCDF4 file (before reprojection)')
    PARSER.add_argument('--output-filename', dest='output_filename',
                        help='Merged NetCDF4 output file')
    PARSER.add_argument('--proj-dir', dest='proj_dir',
                        help='Output directory with projected NetCDF4 files')
    PARSER.add_argument('--science-variables', dest='science_variables',
                        help='Variables to include in the merged output file')
    PARSER.add_argument('--metadata-variables', dest='metadata_variables',
                        help='Variables without coordinate references',
                        default=set())
    ARGS = PARSER.parse_args()

    logging.basicConfig(format='%(asctime)s %(message)s',
                        datefmt='%m/%d/%Y %I:%M:%S %p')

    create_output(ARGS.ori_inputfile, ARGS.output_filename, ARGS.proj_dir,
                  ARGS.science_variables, ARGS.metadata_variables)
