# this plugin doesn't have any specific options to add
def parser(parser):
    return parser

class plugin():
    def __init__(self, options):
        self.__options = options

    def processMessage(self, method, data):
        parsedPoint = None
        if (method.routing_key == 'acct') and ('statsType' in data) and (data['statsType'] == 'formatted'):
            try:
                if len(data['fields']) == 0 or len(data['tags']) == 0:
                    return(False, {})

                parsedPoint = {}
                parsedPoint['measurement'] = data['measurement']
                parsedPoint['time'] = data['timestamp']
                parsedPoint['fields'] = data['fields']
                parsedPoint['tags'] = data['tags']

                for key in parsedPoint['fields']:
                    if type(parsedPoint['fields'][key]) == int and parsedPoint['fields'][key] >= 9023372036854775807:
                        parsedPoint = None
                        break
            except:
                pass

        return parsedPoint
