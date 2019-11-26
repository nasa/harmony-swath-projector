FROM osgeo/gdal:alpine-normal-latest

ARG EDL_USERNAME
ARG EDL_PASSWORD
ENV PYTHONDONTWRITEBYTECODE=1

# Note GIT credentials could have issue if password contains certain characters.
# Escaping may be required
WORKDIR "/home"
RUN pip3 install -vvv requests==2.18.4 --user --trusted-host=pypi.python.org --trusted-host=pypi.org --trusted-host=files.pythonhosted.org boto3 \
    && pip3 install coverage

# Bundle app source

COPY ./test test
COPY ./reproject reproject

ENTRYPOINT ["python", "-m", "unittest", "discover", "-q", "test"]
