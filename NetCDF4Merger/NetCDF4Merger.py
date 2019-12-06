import os
import netCDF4
import logging
import argparse

GDAL_DATASET_NAME = 'Band1'

""" Merging reprojected single-dataset netCDF4 files from GDAL into one, and copy attributes from the original input
    file
"""
def create_output(inputfile, outputfile, temp_dir, logger):

    logger.info("Creating output file '%s'" % outputfile)
    with netCDF4.Dataset(inputfile) as inf, netCDF4.Dataset(outputfile, 'w', format='NETCDF4') as out:

        out.setncatts(read_attrs(inf))

        files = [f for f in os.listdir(temp_dir) if f != os.path.basename(outputfile)]
        if has_time_dimension(inf): copy_time_dimension(inf, out)

        for file in files:
            logger.info("Adding '%s' to the output" % file)
            data = netCDF4.Dataset(temp_dir+'/'+file)
            set_dimension(data, out)

            for name, var in data.variables.items():
                if name not in list(out.variables.keys()):
                    dataset_name = os.path.splitext(file)[0]
                    if name != GDAL_DATASET_NAME: copy_variable(inf, out, data, name, logger)
                    else: copy_variable(inf, out, data, dataset_name, logger)

# read attribute from a file/dataset
def read_attrs(inf): return inf.__dict__

# check if time dimension exists
def has_time_dimension(inf): return 'time' in list(inf.dimensions.keys())

# add time dimension to the output file
def copy_time_dimension(inf, out):

    out.createDimension('time', len(inf.dimensions['time']))

# set dimension in the output
def set_dimension(inf, out):

    for name, dimension in inf.dimensions.items():
        if not (dimension.isunlimited() or name in list(out.dimensions.keys())):
            out.createDimension(name, len(dimension))

# get dataset data type, dimensions, and attributes from input
def get_dataset_meta(inf, rep, dataset_name):

    if dataset_name in rep.variables.keys():
        data_type = get_data_type(rep, dataset_name)
        dims = get_dimensions(rep, dataset_name)
        #attrs = read_attrs(rep[dataset_name])
        attrs = read_attrs(inf[dataset_name]) if dataset_name in inf.variables.keys() else read_attrs(rep[dataset_name])
    else:
        data_type = get_data_type(inf, dataset_name)
        dims = get_dimensions(rep, dataset_name, inf)
        attrs = read_attrs(inf[dataset_name])
    return dims, data_type, attrs

# get dimensions from input
def get_dimensions(rep, dataset_name, inf=None):

    if inf:
        if 'time' in list(inf.dimensions.keys()): return ('time',) + rep[GDAL_DATASET_NAME].dimensions
        else: return rep[dataset_name].dimensions
    else:
        if rep[dataset_name].size > 1: return (dataset_name,)
        else: return None

# get data type
def get_data_type(inf, dataset_name):
    return inf[dataset_name].datatype

# write dataset value to the output
def copy_variable(inf, out, rep, dataset_name, logger):

    # set data type, dimensions, and attributes
    dims, data_type, attrs = get_dataset_meta(inf, rep, dataset_name)

    if dims: out.createVariable(dataset_name, data_type, dims, zlib=True, complevel=6)
    else: out.createVariable(dataset_name, data_type, zlib=True, complevel=6)

    out[dataset_name].setncatts(attrs)

    if dataset_name not in rep.variables.keys(): ori_dataset_name = GDAL_DATASET_NAME
    else: ori_dataset_name = dataset_name

    # manually compute the data value if offset and scale_factor exist for integers
    if rep[ori_dataset_name][:].shape != out[dataset_name].shape:
        reshaped = rep[ori_dataset_name][:].reshape(out[dataset_name].shape)
        if data_type == 'int16' and 'add_offset' in attrs and 'scale_factor' in attrs:
            reshaped = reshaped * out[dataset_name].scale_factor + out[dataset_name].add_offset
        out[dataset_name][:] = reshaped
    else:
        out[dataset_name][:] = rep[ori_dataset_name][:]

# main program
if __name__ == "__main__":
    print('Main')
    parser = argparse.ArgumentParser(prog='NetCDF4Merger', description='Merged reprojected netcdf4 files into one')
    parser.add_argument('--ori-inputfile', dest='ori_inputfile',
                        help='Original input netcdf4 file(before reprojection)')
    parser.add_argument('--output-filename', dest='output_filename',
                        help='Merged netcdf4 output file')
    parser.add_argument('--proj-dir', dest='proj_dir',
                        help='Output directory where projected netcdf4 files are')
    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
    logger = logging.getLogger(__name__)

    create_output(args.ori_inputfile, args.output_filename, args.proj_dir, logger)
