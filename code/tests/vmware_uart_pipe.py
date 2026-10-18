"""Local Windows duplex named-pipe client; no VM or subprocess control."""
from __future__ import annotations
import ctypes as C
from ctypes import wintypes as W
import os
import re
import time

PIPE_RE=re.compile(r'\\\\\.\\pipe\\DongOS-storage-[0-9a-f]{16}\Z')
RETIRED=[]  # Keep OVERLAPPED storage alive if cancellation cannot be confirmed.


def validate_name(name):
    if not isinstance(name,str) or not PIPE_RE.fullmatch(name):
        raise ValueError('only this run\'s unique local DongOS pipe name is allowed')


class OVERLAPPED(C.Structure):
    _fields_=[('Internal',C.c_size_t),('InternalHigh',C.c_size_t),
              ('Offset',W.DWORD),('OffsetHigh',W.DWORD),('hEvent',W.HANDLE)]


class WindowsPipe:
    def __init__(self,name):
        validate_name(name)
        if os.name!='nt':raise OSError('real UART pipe execution requires Windows')
        self.name=name;self.handle=None;self.pending=None
        self.api=C.WinDLL('kernel32',use_last_error=True)
        definitions={
          'CreateFileW':([W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE],W.HANDLE),
          'CreateEventW':([C.c_void_p,W.BOOL,W.BOOL,W.LPCWSTR],W.HANDLE),
          'ReadFile':([W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.POINTER(OVERLAPPED)],W.BOOL),
          'WriteFile':([W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.POINTER(OVERLAPPED)],W.BOOL),
          'GetOverlappedResult':([W.HANDLE,C.POINTER(OVERLAPPED),C.POINTER(W.DWORD),W.BOOL],W.BOOL),
          'WaitForSingleObject':([W.HANDLE,W.DWORD],W.DWORD),
          'CancelIoEx':([W.HANDLE,C.POINTER(OVERLAPPED)],W.BOOL),
          'CloseHandle':([W.HANDLE],W.BOOL),
        }
        for name,(arguments,result) in definitions.items():
            function=getattr(self.api,name);function.argtypes=arguments;function.restype=result

    def connect(self,deadline,stop,clock=time.monotonic):
        while not stop.is_set() and clock()<deadline:
            handle=self.api.CreateFileW(self.name,0xc0000000,0,None,3,0x40000000,None)
            if handle!=C.c_void_p(-1).value:
                self.handle=handle;return
            error=C.get_last_error()
            if error not in (2,231):raise C.WinError(error)
            stop.wait(min(.025,max(0,deadline-clock())))
        raise TimeoutError('local VMware UART pipe did not become available')

    def _start(self,data=None):
        if self.handle is None:raise ConnectionError('UART pipe is not connected')
        event=self.api.CreateEventW(None,True,False,None)
        if not event:raise C.WinError(C.get_last_error())
        buffer=C.create_string_buffer(4096) if data is None else C.create_string_buffer(data,len(data))
        ov=OVERLAPPED();ov.hEvent=event;count=W.DWORD()
        operation=dict(buffer=buffer,overlapped=ov,event=event)
        function=self.api.ReadFile if data is None else self.api.WriteFile
        ok=function(self.handle,buffer,len(buffer),C.byref(count),C.byref(ov))
        if ok:
            self.api.CloseHandle(event)
            if not count.value:raise ConnectionError('UART pipe completed zero bytes')
            return operation,count.value
        error=C.get_last_error()
        if error!=997:
            self.api.CloseHandle(event);raise C.WinError(error)
        return operation,None

    def _poll(self,operation,milliseconds):
        status=self.api.WaitForSingleObject(operation['event'],milliseconds)
        if status==258:return None
        if status!=0:
            error=C.get_last_error();self._cancel(operation);raise C.WinError(error)
        count=W.DWORD()
        if not self.api.GetOverlappedResult(self.handle,C.byref(operation['overlapped']),C.byref(count),False):
            error=C.get_last_error()
            if error==996:self._cancel(operation)
            else:self.api.CloseHandle(operation['event'])
            raise C.WinError(error)
        self.api.CloseHandle(operation['event'])
        if not count.value:raise ConnectionError('UART pipe reached EOF')
        return count.value

    def _cancel(self,operation):
        self.api.CancelIoEx(self.handle,C.byref(operation['overlapped']))
        if self.api.WaitForSingleObject(operation['event'],1000)==0:
            self.api.CloseHandle(operation['event'])
        else:
            # An asynchronous kernel operation may still reference both objects.
            # Keep them and the event until process exit instead of freeing them.
            RETIRED.append(operation)

    def receive(self):
        if self.pending is None:
            operation,count=self._start()
            if count is not None:return operation['buffer'].raw[:count]
            self.pending=operation
        operation=self.pending
        try:count=self._poll(operation,25)
        except BaseException:
            self.pending=None;raise
        if count is None:return b''
        self.pending=None;return operation['buffer'].raw[:count]

    def write(self,data,deadline,clock=time.monotonic):
        offset=0
        while offset<len(data):
            if clock()>=deadline:raise TimeoutError('UART transmit deadline expired')
            operation,count=self._start(data[offset:])
            try:
                while count is None:
                    if clock()>=deadline:
                        self._cancel(operation);raise TimeoutError('UART overlapped write deadline expired')
                    count=self._poll(operation,max(1,min(25,int((deadline-clock())*1000))))
            except BaseException:
                # _poll closes completed failures; an outstanding timed-out
                # operation was explicitly cancelled above and safely retained.
                raise
            offset+=count
        return offset

    def close(self):
        if self.handle is not None:
            if self.pending is not None:
                self._cancel(self.pending);self.pending=None
            self.api.CloseHandle(self.handle);self.handle=None
