# this plugin doesn't have any specific options to add
def parser(parser):
    return parser

class plugin():
    def __init__(self, options):
        self.__options = options

    def processMessage(self, method, data):
        parsed = False
        parsedPoint = None
        if (method.routing_key == 'acct') and ('statsType' in data) and (data['statsType'] == 'scte35'):
            try:
                # the c parser includes the pts which influx doesn't currently like due to size restrictions?
                data['fields'].pop('pts', None)
                data['measurement'] = 'scte35'

                parsedPoint = {}
                parsedPoint['measurement'] = data['measurement']
                parsedPoint['time'] = data['timestamp']
                parsedPoint['fields'] = data['fields']
                parsedPoint['tags'] = data['tags']
                parsed = True
            except:
                pass

        return (parsed, parsedPoint)
