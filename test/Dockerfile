FROM osgeo/gdal:alpine-normal-latest

ARG EDL_USERNAME
ARG EDL_PASSWORD
ENV PYTHONDONTWRITEBYTECODE=1

# Note GIT credentials could have issue if password contains certain characters.
# Escaping may be required
WORKDIR "/home"
RUN pip3 install --upgrade pip \
    && pip3 install requests --user --trusted-host=pypi.python.org --trusted-host=pypi.org --trusted-host=files.pythonhosted.org boto3 \
    && pip3 install coverage \
    && apk add build-base python3-dev \
    && pip3 install pylint safety \
    && apk del build-base python3-dev

# Bundle app source

COPY ./test test
COPY ./reproject reproject

ENTRYPOINT ["/home/test/run"]
