"""Reprojection support for merging single-dataset NetCDF-4 files, produced by
`pyresample`, back into a single output file with all the necessary
attributes.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional, Set, Tuple, Union

import numpy as np
from netCDF4 import Dataset, Variable
from varinfo import VarInfoFromNetCDF4

from swath_projector.exceptions import MissingReprojectedDataError
from swath_projector.utilities import get_variable_file_path, variable_in_dataset

# Values needed for history_json attribute
HISTORY_JSON_SCHEMA = (
    'https://harmony.earthdata.nasa.gov/schemas/history/0.1.0/history-v0.1.0.json'
)
PROGRAM = 'sds/harmony-swath-projector'
PROGRAM_REF = 'https://cmr.uat.earthdata.nasa.gov/search/concepts/S1237974711-EEDTEST'
VERSION = '0.9.0'


def create_output(
    request_parameters: dict,
    output_file: str,
    temp_dir: str,
    science_variables: Set[str],
    metadata_variables: Set[str],
    logger: logging.Logger,
    var_info: VarInfoFromNetCDF4,
) -> None:
    """Merge the reprojected single-dataset NetCDF-4 files from `pyresample`
    into a single file, copying global attributes and metadata
    variables (those without coordinates, which therefore can't be
    reprojected) from the original input file. Then for each listed science
    variable, retrieve the single-band file and copy the reprojected
    variables, and any accompanying CRS and coordinate variables. Note, the
    coordinate datasets will only be copied once.

    """
    input_file = request_parameters.get('input_file')
    logger.info(f'Creating output file "{output_file}"')

    with (
        Dataset(input_file) as input_dataset,
        Dataset(output_file, 'w', format='NETCDF4') as output_dataset,
    ):

        logger.info('Copying input file attributes to output file.')
        set_output_attributes(input_dataset, output_dataset, request_parameters)

        if 'time' in input_dataset.dimensions:
            copy_time_dimension(input_dataset, output_dataset, logger)

        for metadata_variable in metadata_variables:
            copy_metadata_variable(
                input_dataset, output_dataset, metadata_variable, logger
            )

        output_extension = os.path.splitext(input_file)[1]

        for variable_name in science_variables:
            dataset_file = get_variable_file_path(
                temp_dir, variable_name, output_extension
            )

            if os.path.isfile(dataset_file):
                with Dataset(dataset_file) as data:
                    set_dimensions(data, output_dataset)

                    copy_science_variable(
                        input_dataset,
                        output_dataset,
                        data,
                        variable_name,
                        logger,
                        var_info,
                    )

                    # Copy supporting variables from the single band output:
                    # the grid mapping, reprojected x and reprojected y.
                    for variable_key in data.variables:
                        if (
                            variable_key not in output_dataset.variables
                            and variable_key != variable_name
                        ):
                            copy_metadata_variable(
                                data, output_dataset, variable_key, logger
                            )

            else:
                logger.error(f'Cannot find "{dataset_file}".')
                raise MissingReprojectedDataError(variable_name)


def set_output_attributes(
    input_dataset: Dataset, output_dataset: Dataset, request_parameters: Dict
) -> None:
    """Set the global attributes of the merged output file. These begin as the
    global attributes of the input granule, but are updated to also include
    the provenance data via an updated `history` CF attribute (or `History`
    if that is already present), and a `history_json` attribute that is
    compliant with the schema defined at the URL specified by
    `HISTORY_JSON_SCHEMA`.

    `projection` is not included in the output parameters, as this is not
    an original message parameter. It is a derived `pyproj.Proj` instance
    that is defined by the input `crs` parameter.

    `x_extent` and `y_extent` are not serializable, and are instead
    included by `x_min`, `x_max` and `y_min` `y_max` accordingly.

    """
    output_attributes = read_attrs(input_dataset)

    valid_request_parameters = {
        parameter_name: parameter_value
        for parameter_name, parameter_value in request_parameters.items()
        if parameter_value is not None
    }

    # Remove unnecessary and unserializable request parameters
    for surplus_key in ['projection', 'x_extent', 'y_extent']:
        valid_request_parameters.pop(surplus_key, None)

    # Retrieve `granule_url` and replace the `input_file` attribute. This
    # ensures `history_json` refers to the archived granule location, rather
    # than a temporary file in the Docker container.
    granule_url = valid_request_parameters.pop('granule_url', None)
    valid_request_parameters['input_file'] = granule_url

    # Preferentially use `history`, unless `History` is already present in the
    # input file.
    cf_att_name = 'History' if hasattr(input_dataset, 'History') else 'history'
    input_history = getattr(input_dataset, cf_att_name, None)

    # Create new history_json attribute
    new_history_json_record = create_history_record(
        input_history, valid_request_parameters
    )

    # Extract existing `history_json` from input granule
    if hasattr(input_dataset, 'history_json'):
        old_history_json = json.loads(output_attributes['history_json'])
        if isinstance(old_history_json, list):
            output_history_json = old_history_json
        else:
            # Single `history_record` element.
            output_history_json = [old_history_json]
    else:
        output_history_json = []

    # Append `history_record` to the existing `history_json` array:
    output_history_json.append(new_history_json_record)
    output_attributes['history_json'] = json.dumps(output_history_json)

    # Create history attribute
    history_parameters = {
        parameter_name: parameter_value
        for parameter_name, parameter_value in new_history_json_record[
            'parameters'
        ].items()
        if parameter_name != 'input_file'
    }

    new_history_line = ' '.join(
        [
            new_history_json_record['date_time'],
            new_history_json_record['program'],
            new_history_json_record['version'],
            json.dumps(history_parameters),
        ]
    )

    output_history = '\n'.join(filter(None, [input_history, new_history_line]))
    output_attributes[cf_att_name] = output_history

    output_dataset.setncatts(output_attributes)


def create_history_record(input_history: str, request_parameters: dict) -> Dict:
    """Create a serializable dictionary for the `history_json` global
    attribute in the merged output NetCDF-4 file.

    """
    history_record = {
        '$schema': HISTORY_JSON_SCHEMA,
        'date_time': datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
        'program': PROGRAM,
        'version': VERSION,
        'parameters': request_parameters,
        'derived_from': request_parameters['input_file'],
        'program_ref': PROGRAM_REF,
    }

    if isinstance(input_history, str):
        history_record['cf_history'] = input_history.split('\n')
    elif isinstance(input_history, list):
        history_record['cf_history'] = input_history

    return history_record


def read_attrs(dataset: Union[Dataset, Variable]) -> Dict:
    """Read attributes from either a NetCDF4 Dataset or variable object."""
    return dataset.__dict__


def copy_time_dimension(
    input_dataset: Dataset, output_dataset: Dataset, logger: logging.Logger
) -> None:
    """Add time dimension to the output file. This will first add a dimension,
    before creating the corresponding variable in the output dataset.

    """
    logger.info('Adding "time" dimension.')
    time_variable = input_dataset['time']
    output_dataset.createDimension('time', time_variable.size)
    copy_metadata_variable(input_dataset, output_dataset, 'time', logger)


def set_dimensions(input_dataset: Dataset, output_dataset: Dataset) -> None:
    """Read the dimensions in the single band intermediate file. Add each
    dimension to the output dataset that is not already present.

    """
    for name, dimension in input_dataset.dimensions.items():
        if name not in output_dataset.dimensions:
            output_dataset.createDimension(name, dimension.size)


def set_metadata_dimensions(
    metadata_variable: str, source_dataset: Dataset, output_dataset: Dataset
) -> None:
    """Iterate through the dimensions of the metadata variable, and ensure
    that all are present in the reprojected output file. This function is
    necessary if any of the metadata variables, that aren't to be projected
    use the swath-based dimensions from the input granule.

    """
    for dimension in source_dataset[metadata_variable].dimensions:
        if dimension not in output_dataset.dimensions:
            output_dataset.createDimension(
                dimension, source_dataset.dimensions[dimension].size
            )


def copy_metadata_variable(
    source_dataset: Dataset,
    output_dataset: Dataset,
    variable_name: str,
    logger: logging.Logger,
) -> None:
    """Write a metadata variable directly from either the input dataset or a
    single band dataset. The variables from the input dataset have not been
    reprojected as they contain no references to coordinate datasets. The
    variables from the single band datasets are the non-science variables,
    e.g. the grid mapping and projected coordinates. In both instances, the
    variable should be exactly copied from the source dataset to the
    output.

    """
    logger.info(f'Adding metadata variable "{variable_name}" to the output.')
    set_metadata_dimensions(variable_name, source_dataset, output_dataset)

    attributes = read_attrs(source_dataset[variable_name])
    fill_value = get_fill_value_from_attributes(attributes)

    output_dataset.createVariable(
        variable_name,
        source_dataset[variable_name].datatype,
        dimensions=source_dataset[variable_name].dimensions,
        fill_value=fill_value,
        zlib=True,
        complevel=6,
    )

    output_dataset[variable_name][:] = source_dataset[variable_name][:]
    output_dataset[variable_name].setncatts(attributes)


def copy_science_variable(
    input_dataset: Dataset,
    output_dataset: Dataset,
    single_band_dataset: Dataset,
    variable_name: str,
    logger: logging.Logger,
    var_info: VarInfoFromNetCDF4,
) -> None:
    """Write a reprojected variable from a single-band output file to the
    merged output file. This will first obtain metadata (dimensions,
    data type and  attributes) from either the single-band output, or from
    the original input file dataset. Then the variable values from the
    single-band output are copied into the data arrays. If the dataset
    attributes include a scale and offset, the output values are adjusted
    accordingly.

    """
    logger.info(f'Adding reprojected "{variable_name}" to the output')

    dimensions = get_science_variable_dimensions(
        input_dataset, single_band_dataset, variable_name
    )
    attributes = get_science_variable_attributes(
        input_dataset, single_band_dataset, variable_name, var_info
    )

    fill_value = get_fill_value_from_attributes(attributes)

    variable = output_dataset.createVariable(
        variable_name,
        input_dataset[variable_name].datatype,
        dimensions=dimensions,
        fill_value=fill_value,
        zlib=True,
        complevel=6,
    )

    # Extract the data from the single band image, and ensure it is correctly
    # scaled, so packing occurs correctly on write.
    raw_data = single_band_dataset[variable_name][:].data
    scale_factor = attributes.get('scale_factor', 1)
    add_offset = attributes.get('add_offset', 0)

    packed_data = (raw_data - add_offset) / scale_factor

    # Make sure the fill value is still correctly scaled
    filled_data = np.where(raw_data == fill_value)
    packed_data[filled_data] = fill_value

    if 'time' in variable.dimensions:
        variable[0, :] = packed_data
    else:
        variable[:] = packed_data

    variable.setncatts(attributes)


def get_science_variable_attributes(
    input_dataset: Dataset,
    single_band_dataset: Dataset,
    variable_name: str,
    var_info: VarInfoFromNetCDF4,
) -> Dict:
    """Extract the attributes for a science variable, using a combination of
    the original metadata from the unprojected input variable, and then
    augmenting that with the grid_mapping of the reprojected data. Finally,
    ensure the coordinate metadata are still valid. If not, remove that
    metadata entry.

    """
    variable_attributes = read_attrs(input_dataset[variable_name])
    grid_mapping = single_band_dataset[variable_name].grid_mapping
    variable_attributes['grid_mapping'] = grid_mapping

    if 'coordinates' in variable_attributes and not check_coor_valid(
        var_info, variable_name, input_dataset, single_band_dataset
    ):
        del variable_attributes['coordinates']

    return variable_attributes


def get_science_variable_dimensions(
    input_dataset: Dataset, single_band_dataset: Dataset, variable_name: str
) -> Tuple[str]:
    """Retrieve the dimensions from the single-band reprojected dataset. If
    the original input dataset has a 'time' dimension, then include that as
    a dimension of the reprojected variable.

    """
    if 'time' not in input_dataset.dimensions:
        dimensions = single_band_dataset[variable_name].dimensions
    else:
        dimensions = ('time',) + single_band_dataset[variable_name].dimensions

    return dimensions


def check_coor_valid(
    var_info: VarInfoFromNetCDF4,
    variable_name: str,
    input_dataset: Dataset,
    single_band_dataset: Dataset,
) -> bool:
    """Check if variables listed in the coordinates metadata attributes are
    still valid after reprojection. Invalid coordinate reference cases:

      1) Coordinate variable listed in attribute does not exist in single
         band output dataset.
      2) Coordinate variable array shape in the reprojected, single-band
         dataset does not match the input coordinate array shape.

    """
    coords = var_info.get_variable(variable_name).references.get('coordinates', [])

    all_coordinates_in_single_band = all(
        variable_in_dataset(coord, single_band_dataset) for coord in coords
    )

    if not all_coordinates_in_single_band:
        # Coordinates from original variable aren't all present in reprojected
        # output (single band file).
        valid = False
    else:
        valid = all(
            single_band_dataset[coord].shape == input_dataset[coord].shape
            for coord in coords
        )

    return valid


def get_fill_value_from_attributes(variable_attributes: Dict) -> Optional:
    """Check attributes for _FillValue. If present return the value and
    remove the _FillValue attribute from the input dictionary. Otherwise
    return None.

    """
    return variable_attributes.pop('_FillValue', None)
