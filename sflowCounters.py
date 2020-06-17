import ssl
# getEAPIData()
from jsonrpclib import Server
from jsonrpclib.jsonrpc import SafeTransport
from jsonrpclib import config
import http.client
# getVDXData
import requests
from requests.auth import HTTPBasicAuth
import xml.etree.ElementTree as etree
# getSNMNPData
from pysnmp.hlapi import *
from pysnmp.proto.rfc1905 import endOfMibView


# this plugin doesn't have any specific options to add
def parser(parser):
    parser.add_argument("--eapiUser", default="root",
        help="EAPI user, default is root")
    parser.add_argument("--eapiPassword", default="root",
        help="EAPI password, default is root")
    parser.add_argument("--snmpCommunity", default="root",
        help="EAPI user, default is root")

    return parser

class timeoutTransport(SafeTransport):
    def __init__(self):
        self.timeout = 1
        self.__context = ssl._create_unverified_context()
        self._connection = None
        SafeTransport.__init__(self, config.DEFAULT, self.__context)

    def set_timeout(self, timeout):
        self.timeout = timeout

    def make_connection(self, host):
        chost, self._extra_headers, x509 = self.get_host_info(host)
        self._connection = host, http.client.HTTPSConnection(chost, timeout=self.timeout, context=self.__context)
        return self._connection[1]

class plugin():
    def __init__(self, options):
        self.__options = options

        self.__cache = {}
        self.transport = timeoutTransport()

        '''
{"seq": 6422303609, "timestamp": "2020-05-07 17:44:24.96704", "peer_ip_src": "10.124.132.41", "event_type": "log", "source_id_index": 403308563, "sflow_seq": 8686552, "sflow_cnt_seq": 371847, "sf_cnt_type": "sflow_cnt_generic", "ifIndex": 403537946, "ifType": 6, "ifSpeed": 10000000000, "ifDirection": 1, "ifStatus": 3, "ifInOctets": 115974710457, "ifInUcastPkts": 1117816322, "ifInMulticastPkts": 3916328, "ifInBroadcastPkts": 1032238, "ifInDiscards": 0, "ifInErrors": 0, "ifInUnknownProtos": 0, "ifOutOctets": 13391976617200, "ifOutUcastPkts": 558703860, "ifOutMulticastPkts": 142308805, "ifOutBroadcastPkts": 1176750, "ifOutDiscards": 0, "ifOutErrors": 0, "ifPromiscuousMode": 0} '''
    def getEAPIData(self, ip):
        if self.__options.verbosity > 1:
            print("trying to fetch {} via eapi".format(ip), flush=True)
        try:
            uri = "https://{}:{}@{}:443/command-api".format(self.__options.eapiUser, self.__options.eapiPassword, ip)
            switch = Server(uri, transport=self.transport)
            try:
                response = switch.runCmds(1, ['enable', 'show hostname', 'show snmp mib ifmib ifindex'])
                hBase = 1
                iBase = 2
            except:
                response = switch.runCmds(1, ['show hostname', 'show snmp mib ifmib ifindex'])
                hBase = 0
                iBase = 1
            host = {
                'hostname':response[hBase]['hostname'],
                'interfaces':{}
            }
            # for the cache to work right in need to re-index the result set inverted
            for iface, index in response[iBase]['ifIndex'].items():
                host['interfaces'][str(index)] = iface

            # save the cache
            self.__cache[ip] = host
        except Exception as e:
            if self.__options.verbosity > 1:
                print("getEAPIData had a failure fetching from {}".format(ip))
            return (False, None)
        return (True, host)

    def getSNMPData(self, ip):
        if self.__options.verbosity > 1:
            print("trying to fetch {} via snmp".format(ip), flush=True)

        s = SnmpEngine()
        c = CommunityData(self.__options.snmpCommunity, mpModel=1)
        u = UdpTransportTarget((ip, 161), timeout=1)
        context = ContextData()

        errorIndication, errorStatus, errorIndex, varBinds = next(
            getCmd(s, c, u, c, ObjectType(ObjectIdentity('SNMPv2-MIB', 'sysName', 0)))
        )
        if errorIndication:
            return (False, None)

        host = {
            'hostname': varBinds[0][1].prettyPrint(),
            'interfaces': {}
        }

        try:
            for (errorIndication, errorStatus, errorIndex, varBinds) in bulkCmd(
                s, c, u, context, 1, 25,
                ObjectType(ObjectIdentity('IF-MIB', 'ifDescr')),
                lexicographicMode=False):
                
                if errorIndication:
                    break
                elif errorStatus:
                    break
                else:
                    if varBinds[0][1].isSameTypeWith(endOfMibView):
                        break
                    s = varBinds[0][0].prettyPrint().split(".")
                    host['interfaces'][s[len(s)-1]] = varBinds[0][1].prettyPrint()
        except:
            return False, None

        self.__cache[ip] = host
        return True, host

    def getData(self, ip, ifIndex):
        # we cache data.  presently for the lifetime of the app.  maybe we should put a refresh timer?
        found = False
        try:
            host = self.__cache[ip]
            try:
                iface = host['interfaces'][ifIndex]
                found = True
            except KeyError:
                pass
        except KeyError:
            pass

        # we didn't find it.  we need to fetch it.  let's try any APIs first
        if not found:
            (found, host) = self.getEAPIData(ip)

        if not found:
            (found, host) = self.getSNMPData(ip)

        if not found:
            # we failed!
            if self.__options.verbosity > 1:
                print("failed getting interface names for {}".format(ip), flush=True)
            return (None, None)

        if self.__options.verbosity > 1:
            print("successful host fetch")
            if self.__options.verbosity > 2:
                print(host)

        self.__cache[ip] = host

        try:
            return (host['hostname'], host['interfaces'][ifIndex])
        except:
            return (None, None)

    def processMessage(self, method, data):
        parsed = False
        parsedPoint = None
        # these datapoints come from pmacct so they are formatted funny
        if (method.routing_key == 'acct') and ('sf_cnt_type' in data) and (data['sf_cnt_type'] == 'sflow_cnt_generic'):
            # some datapoints may come in with all the information we need.  perhaps we have an out of bandscript
            #   we have written that uses this model instead of a formatted datapoint.  we should deprecate that model
            #   for a formatted point
            hostname = iface = None
            try:
                hostname = data['hostname']
                iface = data['ifName']
            except:
                pass

            if hostname == None or iface == None:
                (hostname, iface) = self.getData(data['peer_ip_src'], str(data['ifIndex']))

            # if we still don't have the hostname/interface then we have a problem and should abort
            if (hostname == None or iface == None):
                return (parsed, parsedPoint)

            # we have had cases where the sflow counters are larger than what we can safely send to influx.
            #  this prevents crashing in that case
            counterList = ['ifInOctets', 'ifOutOctets', 'ifInUcastPkts', 'ifOutUcastPkts']
            for counter in counterList:
                try:
                    data[counter] = int(data[counter])
                    if data[counter] > sys.maxsize:
                        data[counter] = 0
                except:
                    pass 

            try:
                parsedPoint = {
                    'measurement':'sflow',
                    'tags': {
                        'hostname':hostname,
                        'interface':iface
                    },
                    'time': data['timestamp'],
                    'fields': {
                        'traffic_in' :data.get('ifInOctets', 0),
                        'traffic_out':data.get('ifOutOctets', 0),
                        'packets_in' :data.get('ifInUcastPkts', 0),
                        'packets_out':data.get('ifOutUcastPkts', 0)
                    }
                }
                parsed = True
                for key in parsedPoint['fields']:
                    if type(parsedPoint['fields'][key]) == int and parsedPoint['fields'][key] >= 9023372036854775807:
                        parsedPoint = {}
                        parsed = False
                        break
            except:
                pass

        return (parsed, parsedPoint)

