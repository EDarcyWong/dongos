; x86-64 UEFI 布局：字段顺序参照 EDK II 的 UefiSpec.h / SimpleTextOut.h。
; struc 自动计算字段偏移；使用者不得复制数字偏移。
%ifndef DONGOS_UEFI_INC
%define DONGOS_UEFI_INC

EFI_SUCCESS equ 0
EFI_INVALID_PARAMETER equ 0x8000000000000002
EFI_BUFFER_TOO_SMALL equ 0x8000000000000005
AllocateMaxAddress equ 1
EfiLoaderCode equ 1
EfiLoaderData equ 2
EFI_FILE_MODE_READ equ 1
EFI_FILE_DIRECTORY equ 0x10

struc EFI_TABLE_HEADER
    .Signature:                 resq 1
    .Revision:                  resd 1
    .HeaderSize:                resd 1
    .CRC32:                     resd 1
    .Reserved:                  resd 1
endstruc

; UEFI 2.10 / EDK II MdePkg/Include/Uefi/UefiSpec.h.
; Keep every field through LocateProtocol, including Reserved, to preserve ABI offsets.
struc EFI_BOOT_SERVICES
    .Hdr:                       resb EFI_TABLE_HEADER_size
    .RaiseTPL:                  resq 1
    .RestoreTPL:                resq 1
    .AllocatePages:             resq 1
    .FreePages:                 resq 1
    .GetMemoryMap:              resq 1
    .AllocatePool:              resq 1
    .FreePool:                  resq 1
    .CreateEvent:               resq 1
    .SetTimer:                  resq 1
    .WaitForEvent:              resq 1
    .SignalEvent:               resq 1
    .CloseEvent:                resq 1
    .CheckEvent:                resq 1
    .InstallProtocolInterface:  resq 1
    .ReinstallProtocolInterface: resq 1
    .UninstallProtocolInterface: resq 1
    .HandleProtocol:            resq 1
    .Reserved:                  resq 1
    .RegisterProtocolNotify:    resq 1
    .LocateHandle:              resq 1
    .LocateDevicePath:          resq 1
    .InstallConfigurationTable: resq 1
    .LoadImage:                 resq 1
    .StartImage:                resq 1
    .Exit:                      resq 1
    .UnloadImage:               resq 1
    .ExitBootServices:          resq 1
    .GetNextMonotonicCount:      resq 1
    .Stall:                     resq 1
    .SetWatchdogTimer:           resq 1
    .ConnectController:         resq 1
    .DisconnectController:      resq 1
    .OpenProtocol:              resq 1
    .CloseProtocol:             resq 1
    .OpenProtocolInformation:   resq 1
    .ProtocolsPerHandle:        resq 1
    .LocateHandleBuffer:        resq 1
    .LocateProtocol:            resq 1
endstruc

struc EFI_LOADED_IMAGE_PROTOCOL
    .Revision:                  resd 1
    .Padding:                   resd 1
    .ParentHandle:              resq 1
    .SystemTable:               resq 1
    .DeviceHandle:              resq 1
    .FilePath:                  resq 1
    .Reserved:                  resq 1
    .LoadOptionsSize:           resd 1
    .LoadOptionsPadding:        resd 1
    .LoadOptions:               resq 1
    .ImageBase:                 resq 1
    .ImageSize:                 resq 1
    .ImageCodeType:             resd 1
    .ImageDataType:             resd 1
    .Unload:                    resq 1
endstruc

struc EFI_SIMPLE_FILE_SYSTEM_PROTOCOL
    .Revision:                  resq 1
    .OpenVolume:                resq 1
endstruc

struc EFI_FILE_PROTOCOL
    .Revision:                  resq 1
    .Open:                      resq 1
    .Close:                     resq 1
    .Delete:                    resq 1
    .Read:                      resq 1
    .Write:                     resq 1
    .GetPosition:               resq 1
    .SetPosition:               resq 1
    .GetInfo:                   resq 1
    .SetInfo:                   resq 1
    .Flush:                     resq 1
endstruc

struc EFI_FILE_INFO
    .Size:                      resq 1
    .FileSize:                  resq 1
    .PhysicalSize:              resq 1
    .CreateTime:                resb 16
    .LastAccessTime:            resb 16
    .ModificationTime:          resb 16
    .Attribute:                 resq 1
    .FileName:                  resw 1
endstruc

struc EFI_GRAPHICS_OUTPUT_PROTOCOL
    .QueryMode:                 resq 1
    .SetMode:                   resq 1
    .Blt:                       resq 1
    .Mode:                      resq 1
endstruc

struc EFI_GRAPHICS_OUTPUT_PROTOCOL_MODE
    .MaxMode:                   resd 1
    .Mode:                      resd 1
    .Info:                      resq 1
    .SizeOfInfo:                resq 1
    .FrameBufferBase:           resq 1
    .FrameBufferSize:           resq 1
endstruc

struc EFI_GRAPHICS_OUTPUT_MODE_INFORMATION
    .Version:                   resd 1
    .HorizontalResolution:      resd 1
    .VerticalResolution:        resd 1
    .PixelFormat:               resd 1
    .RedMask:                   resd 1
    .GreenMask:                 resd 1
    .BlueMask:                  resd 1
    .ReservedMask:              resd 1
    .PixelsPerScanLine:         resd 1
endstruc

struc EFI_CONFIGURATION_TABLE
    .VendorGuid:                resb 16
    .VendorTable:               resq 1
endstruc

struc EFI_MEMORY_DESCRIPTOR
    .Type:                      resd 1
    .Padding:                   resd 1
    .PhysicalStart:             resq 1
    .VirtualStart:              resq 1
    .NumberOfPages:             resq 1
    .Attribute:                 resq 1
endstruc

struc EFI_SYSTEM_TABLE
    .Hdr:                       resb EFI_TABLE_HEADER_size
    .FirmwareVendor:            resq 1
    .FirmwareRevision:          resd 1
    .FirmwareRevisionPadding:   resd 1 ; x64 指针字段按 8 字节对齐。
    .ConsoleInHandle:           resq 1
    .ConIn:                     resq 1
    .ConsoleOutHandle:          resq 1
    .ConOut:                    resq 1
    .StandardErrorHandle:       resq 1
    .StdErr:                    resq 1
    .RuntimeServices:           resq 1
    .BootServices:              resq 1
    .NumberOfTableEntries:      resq 1
    .ConfigurationTable:        resq 1
endstruc

struc EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL
    .Reset:                     resq 1
    .OutputString:              resq 1
    .TestString:                resq 1
    .QueryMode:                 resq 1
    .SetMode:                   resq 1
    .SetAttribute:              resq 1
    .ClearScreen:               resq 1
    .SetCursorPosition:         resq 1
    .EnableCursor:              resq 1
    .Mode:                      resq 1
endstruc

%endif
