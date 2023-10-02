#!/usr/bin/env python3

from identity import app

if __name__ == '__main__':
    app.run(host="::",port=8000,debug=True)
