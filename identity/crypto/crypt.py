#!/bin/env python

import sys

import CryptoUtil
from CryptoUtil import KeyLengthError

def main(args):
    if len(args) != 4 or args[1] not in ['dec', 'enc']:
        print 'Usage: crypt.py enc <plaintext> <passphrase>'
        print '       crypt.py dec <encrypted> <passphrase>'
        return

    op = args[1]
    key = args[3]

    if op == 'enc':
        plain = args[2]
        try:
            print CryptoUtil.encrypt(plain, key)
        except KeyLengthError, ex:
            print ex
    elif op == 'dec':
        encrypted = args[2]
        try:
            print CryptoUtil.decrypt(encrypted, key)
        except KeyLengthError, ex:
            print ex

if __name__ == "__main__":
    main(sys.argv)
