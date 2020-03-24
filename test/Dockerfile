FROM python:3.8-slim
# FROM osgeo/gdal:alpine-normal-3.0.2
# FROM osgeo/gdal:alpine-normal-latest

ARG EDL_USERNAME
ARG EDL_PASSWORD
ENV PYTHONDONTWRITEBYTECODE=1

# Note GIT credentials could have issue if password contains certain characters.
# Escaping may be required
WORKDIR "/home"

RUN pip3 install --upgrade pip \
    && pip3 install requests --user --trusted-host=pypi.python.org --trusted-host=pypi.org --trusted-host=files.pythonhosted.org boto3 \
    && pip3 install coverage \
    && pip3 install netCDF4 pyresample==1.13.1 pylint safety

#    && apk add build-base python3-dev py-numpy-dev \
#    && apk add --no-cache --allow-untrusted --repository http://dl-3.alpinelinux.org/alpine/edge/testing hdf5-dev netcdf-dev \
#    && pip3 install netCDF4 pylint safety
#    && apk del py-numpy-dev python3-dev build-base


# Bundle app source

COPY ./test test
COPY ./PyMods PyMods
COPY swotrepr.py .

ENTRYPOINT ["/home/test/run"]
