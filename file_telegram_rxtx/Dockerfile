FROM jrottenberg/ffmpeg:centos
ADD . /home
WORKDIR /home

RUN yum install -y https://centos7.iuscommunity.org/ius-release.rpm
RUN yum update -y
RUN yum install -y python36u python36u-libs python36u-devel python36u-pip

RUN pip3.6 install -U requests[socks]
RUN pip3.6 install --upgrade -r requirements.txt
RUN cd vk_api && python3.6 setup.py install
ENTRYPOINT ["python3.6","worker.py","static.250.19.216.95.clients.your-server.de"]
#CMD ["worker.py","static.250.19.216.95.clients.your-server.de"]
#CMD ["python","worker.py","s1.mediatube.xyz"]
