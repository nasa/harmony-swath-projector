FROM osgeo/gdal:alpine-normal-latest

ARG EDL_USERNAME
ARG EDL_PASSWORD

# Note GIT credentials could have issue if password contains certain characters.
# URL encoding additional characters besides '@' may be required
WORKDIR "/home"
RUN pip3 install -vvv requests==2.18.4 --user --trusted-host=pypi.python.org --trusted-host=pypi.org --trusted-host=files.pythonhosted.org boto3 \
    && apk add git \
    && EDL_PASSWORD=$(echo $EDL_PASSWORD | sed -e 's/@/%40/g') \
    && pip3 install "git+https://${EDL_USERNAME}:${EDL_PASSWORD}@git.earthdata.nasa.gov/scm/harmony/harmony-service-lib-py.git" \
    && apk add --no-cache --allow-untrusted --repository http://dl-3.alpinelinux.org/alpine/edge/testing hdf5-dev netcdf-dev \
    && apk add build-base python3-dev py-numpy-dev \
    && pip3 install netCDF4 \
    && apk del py-numpy-dev python3-dev build-base

# Bundle app source
COPY ./reproject reproject

ENTRYPOINT ["python3", "reproject/reproject.py"]
