#!/usr/bin/env python

import sys, getpass

import CryptoUtil
from CryptoUtil import KeyLengthError

def usage():
    exit()

def main(args):

    op = args[0]

    if 'encrypt' in op:
        key = getpass.getpass('Please enter the encryption key: ')
        plaintext = getpass.getpass('Please enter the plaintext you wish to encrypt: ')
        try:
            encrypted_value = CryptoUtil.encrypt(plaintext, key)
            print("Encrypted Value: " + encrypted_value)
        except KeyLengthError as ex:
            print (ex)

    if 'decrypt' in op:
        key = getpass.getpass('Please enter the encryption key: ')
        encrypted_value = getpass.getpass('Please enter the encrypted string you wish to decrypt: ')
        try:
            decrypted_value = CryptoUtil.decrypt(encrypted_value, key)
            print("Plaintext Value: " + decrypted_value)
        except KeyLengthError as ex:
            print(ex)

if __name__ == "__main__":
    main(sys.argv)
