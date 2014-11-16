from identity import app

import gevent.monkey
from gevent.pywsgi import WSGIServer
gevent.monkey.patch_all()

if __name__ == '__main__':
    http_server = WSGIServer(('127.0.0.1', 8001), app)
    http_server.serve_forever()
