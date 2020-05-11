import datetime, json, importlib, argparse, pika
from influxdb import InfluxDBClient

class emptyClass():
    pass

class main():
    def __rabbitInit(self):
        if self.__options.verbosity > 0:
            print("initializing rabbit configuration", flush=True)

        # rabbit configuration we only support a single rabbit queue atm.
        self.__rabbit = emptyClass()
        self.__rabbit.connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.__options.rabbitHost))
        self.__rabbit.channel = self.__rabbit.connection.channel()
        self.__rabbit.channel.queue_declare(queue=self.__options.rabbitRouting)
        self.__rabbit.channel.exchange_declare(exchange=self.__options.rabbitExchange, exchange_type='direct')
        self.__rabbit.channel.queue_bind(exchange=self.__options.rabbitExchange, routing_key=self.__options.rabbitRouting, queue=self.__options.rabbitRouting)

        # set up the callbacks and start pulling rabbit messages
        if self.__options.verbosity > 0:
            print("starting to consume", flush=True)

        self.__rabbit.channel.basic_consume(self.__options.rabbitRouting, self.consumeData)
        self.__rabbit.channel.start_consuming()

    def __influxInit(self):
        if self.__options.verbosity > 0:
            print("initializing influx configuration", flush=True)

        self.__influx = InfluxDBClient(self.__options.influxHost, self.__options.influxPort, self.__options.influxUser, self.__options.influxPassword, self.__options.influxDatabase, timeout=2)

    def __init__(self, options):
        self.__options = options

        self.__plugins = options.plugins

        self.__points = emptyClass()
        # max number of buffered points
        self.__points.maxPoints = 10000
        # swap memory for cpu
        self.__points.currentPoints = 0
        # we don't flush points individually to reduce db load.  buffer them up for N seconds
        self.__points.nextFlush = datetime.datetime.now() + datetime.timedelta(seconds=options.seconds)
        # these are datapoints that are formatted and ready to go to the database
        self.__points.formattedPoints = []
        # these are delivery tags for all unacknowledged rabbit messages
        self.__points.rawPoints = []
        # we can bulk ack based on the maxUnAckTag
        self.__points.maxUnAckTag = 0

        self.__influxInit()
        self.__rabbitInit()

    def __flushPoints(self, channel):
        if self.__options.verbosity > 0:
            print("flushing {} datapoints".format(self.__points.currentPoints), flush=True)

        try:
            if not self.__options.debug:
                self.__influx.write_points(self.__points.formattedPoints, time_precision='u')
            else:
                print(self.__points.formattedPoints, flush=True)
        except:
            print("{}, failed saving {} points to the database. attempting to reconnect".format(datetime.datetime.now(), self.__points.currentPoints), flush=True)
            self.__influxInit()
            return False
        else:
            print("{}, flushed {} points to the database".format(datetime.datetime.now(), self.__points.currentPoints), flush=True)
            
            # ack all flushed points
            if not self.__options.debug:
                for point in self.__points.rawPoints:
                    channel.basic_ack(delivery_tag=point)

            self.__points.formattedPoints = []
            self.__points.rawPoints = []
            self.__points.currentPoints = 0
            return True

    # prototype here is defined by pika
    def consumeData(self, channel, method, properties, body):
        # the datapoint should be json formatted
        try:
            data = json.loads(body.decode('utf-8'))
            tsCurrentPoint = datetime.datetime.strptime(data['timestamp'], '%Y-%m-%d %H:%M:%S.%f')
        except:
            # 1) the datapoint isn't decodable
            # 2) the datapoint is missing a timestamp field
            # 3) the datapoint timestamp is malformatted
            # we should just ack it so that we don't keep choking on it
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        if self.__options.verbosity > 1:
            print("consuming a datapoint: currentTS: {}, currentPoints: {}".format(tsCurrentPoint, self.__points.currentPoints), flush=True)
            if self.__options.verbosity > 2:
                print(data, flush=True)

        # let's cache this point.
        #  plugins can each parse the point and create a new point for it.  pass it through each plugin and let them decide
        pointSaved = False
        for plugin in self.__plugins:
            (result, processedPoint) = plugin.processMessage(method, data)
            if result:
                if self.__options.verbosity > 1:
                    print("point saved", flush=True)

                pointSaved = True
                self.__points.currentPoints += 1
                self.__points.formattedPoints.append(processedPoint)
                self.__points.rawPoints.append(method.delivery_tag)
                if method.delivery_tag > self.__points.maxUnAckTag:
                    self.__points.maxUnAckTag = method.delivery_tag

        if not pointSaved:
            if self.__options.verbosity > 1:
                print("nobody was interested in this datapoint", flush=True)

            # apparently no plugins were interesting in this datapoint.  just ack it
            channel.basic_ack(delivery_tag = method.delivery_tag)

        # let's see if we need to flush points.
        #  1) we just pushed past maxTags
        #  2) delivery time has just been exceeded
        if (tsCurrentPoint > self.__points.nextFlush) or (self.__points.currentPoints > self.__points.maxPoints):
            result = self.__flushPoints(channel)
            if result:
                self.__points.nextFlush = tsCurrentPoint + datetime.timedelta(seconds=self.__options.seconds)

if __name__ == "__main__":
    description = \
"""Pull datapoints out of rabbit and push them to an influxdb database"""

    parser = argparse.ArgumentParser(description=description)

    # rabbit settings
    parser.add_argument("--rabbitHost", default="localhost",
        help="rabbitmq host, default is localhost")
    parser.add_argument("--rabbitExchange", default="pmacct",
        help="rabbitmq exchange, default is pmacct")
    parser.add_argument("--rabbitRouting", default="acct",
        help="rabbitmq routing key, default is acct")

    # influx settings
    parser.add_argument("--influxHost", default="localhost",
        help="influxdb host, default is localhost")
    parser.add_argument("--influxPort", default=8086, type=int,
        help="influxdb port, default is 8086")
    parser.add_argument("--influxUser", default="root",
        help="influxdb user, default is root")
    parser.add_argument("--influxPassword", default="root",
        help="influxdb password, default is root")
    parser.add_argument("--influxDatabase", default="stats",
        help="influxdb database, default is stats")

    # generic options
    parser.add_argument("-p", "--plugins", nargs="*", 
        help="we automatically load sflow and formattedpoints, additional plugins to load, do not include .py")
    parser.add_argument("--seconds", default=10,
        help="max seconds to buffer datapoints, default is 10")
    parser.add_argument("-d", "--debug", action='store_true',
        help="debug, print points, but don't push them to the database")
    parser.add_argument("-v", "--verbosity", action='count', default=0,
        help="verbosity can be specified multiple times")

    # i don't have a good plugin model.  this is a bit ghetto
    # first let's load all the modules and append to the parser if needed
    pluginNames = ['sflowCounters', 'formattedPoint']

    # let's preparse the commandline to see if we have a -p
    options, t = parser.parse_known_args()
    try:
        for option in options.plugins:
            pluginNames.append(option)
    except:
        pass
    
    plugins = {}
    try:
        for plugin in pluginNames:
            plugins[plugin] = importlib.import_module(plugin)
            parser = plugins[plugin].parser(parser)

        options = parser.parse_args()

        options.plugins = []
        for plugin in plugins:
            options.plugins.append(plugins[plugin].plugin(options))
    except:
        print("there was an error loading the plugins {}.".format(pluginNames), flush=True)
        exit(-1)

    #TODO REMOVE THIS!
#    options.debug = True
#    options.verbosity = 3

    if options.verbosity > 0:
        print(options, flush=True)

    main = main(options)

