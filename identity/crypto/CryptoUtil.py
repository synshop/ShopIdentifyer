from base64 import b64decode, b64encode
from Crypto.Cipher import AES


IV = 'Md/wgoPzQzL4U2pO'


AES_256_KEY_LEN = 32
AES_256_VAL_BLOCK = 16
AES_256_IV_LEN = 16


def encrypt(plaintext, key):
    if len(key) >= AES_256_KEY_LEN:
        raise KeyLengthError("Encryption key cannot be %s bytes or longer" % AES_256_KEY_LEN)
    padplain = _pad(plaintext, AES_256_VAL_BLOCK)
    algo = _new(key)
    encrypted = algo.encrypt(padplain.encode("utf8"))
    enc64 = b64encode(encrypted)
    return enc64.decode("utf8")


def decrypt(enc64, key):
    encrypted = b64decode(enc64)
    algo = _new(key)
    padplain = algo.decrypt(encrypted)
    plaintext = _unpad(padplain)
    return plaintext


def _new(key):
    padkey = _pad(key, AES_256_KEY_LEN)
    return AES.new(padkey.encode("utf8"), AES.MODE_CBC, IV.encode("utf8"))


def _pad(val, block_size):
    """
    Applies PKCS5 padding.
    """
    padlen = block_size - len(val) % block_size
    return val + padlen * chr(padlen)


def _unpad(val):
    """
    Removes PKCS5 padding.
    """
    return (val.decode('utf-8'))


class KeyLengthError(ValueError):
    pass
