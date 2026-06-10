#ifndef USB_STRING_DESCRIPTORS_GEN_H
#define USB_STRING_DESCRIPTORS_GEN_H

__code uint16_t ProductDescriptor[] = {
    (((12 + 1) * 2) | (DTYPE_String << 8)),
    'K',
    'e',
    'y',
    'p',
    'a',
    'd',
    ' ',
    'C',
    'H',
    '5',
    '5',
    '2'
};

__code uint16_t ManufacturerDescriptor[] = {
    (((14 + 1) * 2) | (DTYPE_String << 8)),
    'T',
    'e',
    'c',
    'h',
    'a',
    'l',
    'c',
    'h',
    'e',
    'm',
    'y',
    ' ',
    'S',
    'I'
};

__code uint16_t SerialDescriptor[] = {
    (((12 + 1) * 2) | (DTYPE_String << 8)),
    'T',
    'C',
    'Y',
    '-',
    'C',
    'H',
    '5',
    '5',
    '2',
    '-',
    'K',
    'B'
};

#endif
