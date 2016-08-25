'''
CoG application-level constants.
'''

SECTION_DEFAULT = 'DEFAULT'
SECTION_ESGF = 'ESGF'
SECTION_EMAIL = 'EMAIL'
SECTION_GLOBUS = 'GLOBUS'

# note: use lower case
VALID_MIME_TYPES = { '.bmp':  ['image/bmp', 'image/x-windows-bmp'],
                     '.csv':  ['text/plain'],
                     '.doc':  ['application/msword'],
                     '.docx': ['application/msword','application/zip'],
                     '.gif':  ['image/gif'],
                     '.jpg':  ['image/jpeg','image/pjpeg'],
                     '.jpeg': ['image/jpeg', 'image/pjpeg' ],
                     '.pdf':  ['application/pdf'],
                     '.png':  ['image/png'],
                     '.ppt':  ['application/mspowerpoint', 'application/powerpoint', 'application/vnd.ms-powerpoint', 'application/x-mspowerpoint'],
                     '.pptx': ['application/mspowerpoint', 'application/powerpoint', 'application/vnd.ms-powerpoint', 'application/x-mspowerpoint','application/zip'],
                     '.tif':  ['image/tiff', 'image/x-tiff'],
                     '.tiff': ['image/tiff', 'image/x-tiff'],
                     '.txt':  ['text/plain'],
                     '.xls':  ['application/excel', 'application/vnd.ms-excel', 'application/x-msexcel'],
                     '.xlsx': ['application/excel', 'application/vnd.ms-excel', 'application/x-msexcel','application/zip'],
                     }
