FROM python:3.11-slim
  
RUN pip install oci
RUN pip install kubernetes

ADD watchdog.py /app/watchdog.py
ADD new_job.py /app/new_job.py
WORKDIR /app
CMD [ "python3", "./watchdog.py" ]
