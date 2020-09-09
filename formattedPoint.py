# this plugin doesn't have any specific options to add
def parser(parser):
    return parser

class plugin():
    def __init__(self, options):
        self.__options = options

    def processMessage(self, method, data):
        parsed = False
        parsedPoint = None
        if (method.routing_key == 'acct') and ('statsType' in data) and (data['statsType'] == 'formatted'):
            try:
                parsedPoint = {}
                parsedPoint['measurement'] = data['measurement']
                parsedPoint['time'] = data['timestamp']
                parsedPoint['fields'] = data['fields']
                parsedPoint['tags'] = data['tags']
                parsed = True

                for key in parsedPoint['fields']:
                    if type(parsedPoint['fields'][key]) == int and parsedPoint['fields'][key] >= 9023372036854775807:
                        parsedPoint = {}
                        parsed = False
                        break
            except:
                pass

        return (parsed, parsedPoint)
