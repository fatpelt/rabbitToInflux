# rabbitToInflux
this code is licensed under the MIT license.

this script moves data out of a rabbit queue and into the internal influxdb database.  in our environment we run a rabbitmq (non-clustered) server in each datacenter facility.  this box also runs sfacct to collect sflow counters, and this script to push all parsed datapoints to an influxdb instance in a remote datacenter.  this allows for intermittency on the wan connectivity without losing datapoints as they are queued in rabbit.  rabbit was chosen as pmacct already supported amqp, it's easy to set up and configure, and reliable.

the provided sfacct config is basic and minimal.  should you choose to change the amqp config in that file you'll need to ensure your rabbitToInflux configuration matches it.

# installation
* make sure to load the requirements.txt file into your python3 environment

copy the systemd service into place
```sh
cp rabbitToInflux.service /etc/systemd/system/
systemctl daemon-reload
```
set up configuration
```sh
mkdir /etc/rabbitToInflux
cp EXAMPLE.conf /etc/rabbitToInflux/main.conf
vi /etc/rabbitToInflux/main.conf
```

enable and start the service
```sh
systemctl enable rabbitToInflux.service
systemctl start rabbitToInflux.service
```
# dependencies
* python3
* install the python requirements in requirements.txt
* a working rabbit installation on the local host.
* a working influx somewhere
* a nice graphing engine like grafana

# sample configurations
Currently the system supports SNMP fetching of interface names as sflow samples reference the ifIndex and we probably want to more useful name than just an ifIndex.  This is currently fetched automatically when the system sees the first datapoint from the host.  We also currently support the arista EAPI. Consult your documentation for setup instructions.

* arista (though this will likely work with minimal changes on other platforms)
```
! we only support snmpv2 currently
snmp-server community public ro
snmp-server vrf Management

sflow enable
sflow destination IP_OF_SFACCT_BOX
! this determines how often interfaces report statistics
sflow polling-interval 10
! we don't yet look at flow data, so set the flow sampling at a high value
sflow sample 4294967295

! now enable sflow on all interfaces
int e1-48
 sflow enable
```


