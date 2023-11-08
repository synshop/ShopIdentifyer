import getpass
import os

PASSWORD_KEY = 'ENCRYPTION_KEY'

class EncryptionKey(object):
    _key = None

    @staticmethod
    def get():

        if PASSWORD_KEY in os.environ.keys():
            EncryptionKey._key = os.environ[PASSWORD_KEY]
        
        if EncryptionKey._key is None:
            EncryptionKey._key = getpass.getpass('Please enter the encryption key to unlock this application: ')

        return EncryptionKey._key
