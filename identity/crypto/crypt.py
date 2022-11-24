#!/usr/bin/env python

import sys, getpass

import CryptoUtil
from CryptoUtil import KeyLengthError


def main(args):

    if len(args) > 1 or args[0] == './identity/crypto/crypt.py':
        print('Do not call this directly, use symlinks. See https://github.com/synshop/ShopIdentifyer')
        quit()

    op = args[0]

    if 'encrypt' in op:
        key = getpass.getpass('Please enter the encryption key: ')
        plaintext = getpass.getpass('Please enter the plaintext you wish to encrypt: ')
        if len(key) > 0 or len(plaintext) > 0:
            try:
                encrypted_value = CryptoUtil.encrypt(plaintext, key)
                print("Encrypted Value: " + encrypted_value)
            except KeyLengthError as ex:
                print('ERROR', 'Key Length Error')
                print(ex)
            except Exception as e:
                print('ERROR', 'Error in encrypting. Please check in inputs and try again.')
                print(e)
        else:
            print('Key and plaintext must be at least 1 character long')

        quit()

    if 'decrypt' in op:
        key = getpass.getpass('Please enter the decryption key: ')
        ciphertext = getpass.getpass('Please enter the ciphertext you wish to decrypt: ')

        if len(key) > 0 or len(ciphertext) > 0:
            try:
                decrypted_value = CryptoUtil.decrypt(ciphertext, key)
                print("Plaintext Value: " + decrypted_value)
            except KeyLengthError as ex:
                print('ERROR', 'Key Length Error')
                print(ex)
            except Exception as e:
                print('ERROR', 'Error in decrypting. Please check in inputs and try again.')
                print(e)

        else:
            print('Key and ciphertext must be at least 1 character long')

        quit()

    else:
        print('Valid arguments: "encrypt" or "decrypt". See https://github.com/synshop/ShopIdentifyer')


if __name__ == "__main__":
    main(sys.argv)
