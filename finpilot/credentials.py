"""Windows-account-bound encrypted connection settings; no plaintext key on disk."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path

DEFAULT_MODEL = 'thinkingmachines/inkling:free'


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def crypt(data, decrypt=False):
    if os.name != 'nt':
        raise OSError('Persistent key storage requires Windows. No plaintext fallback is used.')
    buf=ctypes.create_string_buffer(data)
    source=Blob(len(data),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)))
    result=Blob()
    dll=ctypes.WinDLL('crypt32',use_last_error=True)
    fn=dll.CryptUnprotectData if decrypt else dll.CryptProtectData
    fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    fn.restype=wintypes.BOOL
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(result)):
        raise OSError('Windows could not access the encrypted connection settings.')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    try:return ctypes.string_at(result.data,result.size)
    finally:kernel.LocalFree(result.data)


def connection_path(storage_path):
    path=Path(storage_path)
    return path.with_name(path.stem+'_connection.dpapi')


def save_connection(path,key,model):
    if not key.strip():raise ValueError('Enter an API key before saving.')
    if not (model.endswith(':free') or model=='openrouter/free'):
        raise ValueError('Choose a free model ID ending in :free, or openrouter/free.')
    encrypted=crypt(json.dumps(dict(key=key.strip(),model=model.strip())).encode())
    path=Path(path);temp=path.with_suffix('.dpapi.tmp')
    try:
        temp.write_bytes(encrypted);temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def load_connection(path):
    path=Path(path)
    if not path.exists():return '',DEFAULT_MODEL
    result=json.loads(crypt(path.read_bytes(),True))
    if not isinstance(result.get('key'),str) or not isinstance(result.get('model'),str):
        raise ValueError('Invalid saved connection.')
    return result['key'],result['model']
