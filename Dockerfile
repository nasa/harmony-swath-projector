FROM osgeo/gdal:alpine-normal-latest

ARG EDL_USERNAME
ARG EDL_PASSWORD

# Note GIT credentials could have issue if password contains certain characters.
# Escaping may be required
WORKDIR "/home"
RUN pip3 install -vvv requests==2.18.4 --user --trusted-host=pypi.python.org --trusted-host=pypi.org --trusted-host=files.pythonhosted.org boto3 \
    && apk add git \
    && pip3 install "git+https://${EDL_USERNAME}:${EDL_PASSWORD}@git.earthdata.nasa.gov/scm/harmony/harmony-service-lib-py.git"

# Bundle app source
COPY . .

ENTRYPOINT ["python3", "reproject/reproject.py"]
