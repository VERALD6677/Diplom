FROM python

WORKDIR /usr/src/netology_pd_diplom

RUN pip install --upgrade pip
COPY ./requirements.txt .
RUN pip install -r requirements.txt

COPY . .