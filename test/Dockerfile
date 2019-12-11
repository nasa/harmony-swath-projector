FROM osgeo/gdal:alpine-normal-latest

ARG EDL_USERNAME
ARG EDL_PASSWORD
ENV PYTHONDONTWRITEBYTECODE=1

# Note GIT credentials could have issue if password contains certain characters.
# Escaping may be required
WORKDIR "/home"
RUN pip3 install -vvv requests==2.18.4 --user --trusted-host=pypi.python.org --trusted-host=pypi.org --trusted-host=files.pythonhosted.org boto3 \
    && pip3 install coverage \
    && apk add --no-cache --allow-untrusted --repository http://dl-3.alpinelinux.org/alpine/edge/testing hdf5-dev netcdf-dev \
    && apk add build-base python3-dev py-numpy-dev \
    && pip3 install netCDF4

# Bundle app source

COPY ./test test
COPY ./reproject reproject

ENTRYPOINT ["python", "-m", "unittest", "discover", "-q", "test"]
