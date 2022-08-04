#!/usr/bin/env python

import sys, getpass

import CryptoUtil
from CryptoUtil import KeyLengthError

def usage():
    print()
    print("When the web server starts up, it will prompt you for a decryption password.")
    print("Use this tool to encrypt/decrypt the sensitive properties that go in ./identity/config.py")
    print("Make sure you use the same passphrase to encrypt all the values")
    print()
    print('Usage: crypt.py encrypt')
    print('       crypt.py decrypt')
    print()
    exit()

def main(args):

    if len(args) != 2 or args[1] not in ['decrypt','encrypt','enc','dec']:
        usage()

    op = args[1]

    if op in ['enc', 'encrypt']:
        key = getpass.getpass('Please enter the encryption key: ')
        plaintext = getpass.getpass('Please enter the plaintext you wish to encrypt: ')
        try:
            encrypted_value = CryptoUtil.encrypt(plaintext, key)
            print("Encrypted Value: " + encrypted_value)
        except KeyLengthError, ex:
            print (ex)

    if op in ['dec', 'decrypt']:
        key = getpass.getpass('Please enter the encryption key: ')
        encrypted_value = getpass.getpass('Please enter the encrypted string you wish to decrypt: ')
        try:
            decrypted_value = CryptoUtil.decrypt(encrypted_value, key)
            print("Plaintext Value: " + decrypted_value)
        except KeyLengthError, ex:
            print(ex)

if __name__ == "__main__":
    main(sys.argv)
