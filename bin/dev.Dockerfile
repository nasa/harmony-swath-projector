#
# Using Conda within ENTRYPOINT was taken from:
# https://pythonspeed.com/articles/activate-conda-dockerfile/
#
# This Dockerfile uses a base image that already contains the Conda and Pip
# requirements, copies updated versions of SwotRepr source code (which is much
# quicker than creating the Python environment), and runs all tests.
#
FROM sds/swot-reproject-env

ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR "/home"

# Bundle app source
COPY ./test test
COPY ./pymods pymods
COPY swotrepr.py .

# Configure a container to be executable via the `docker run` command.
ENTRYPOINT ["/home/test/run"]
