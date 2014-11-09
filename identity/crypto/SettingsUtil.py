import getpass
import os
import CryptoUtil

PASSWORD_KEY = 'ENCRYPTION_KEY'

class EncryptionKey(object):
    _key = None

    @staticmethod
    def get(is_dev=True):
        if is_dev:
            print 'WARNING: Running in dev mode'

            if PASSWORD_KEY in os.environ.keys():
                print 'Because this is development mode, importing encryption key from %s' % PASSWORD_KEY
                EncryptionKey._key = os.environ[PASSWORD_KEY]
            else:
                print 'You are running in development mode, but don\'t have the "%s" environment variable set so I will ask you for the password' % PASSWORD_KEY
                print 'You can save yourself some time by setting this environment variable'

        if EncryptionKey._key is None:
            EncryptionKey._key = getpass.getpass('Please enter the enryption key to unlock this application: ')

        if is_dev:
            os.environ[PASSWORD_KEY] = EncryptionKey._key

        return EncryptionKey._key
