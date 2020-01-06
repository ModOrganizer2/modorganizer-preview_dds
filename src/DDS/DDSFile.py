from pathlib import Path

from PyQt5.QtCore import QCoreApplication, qCritical
from PyQt5.QtGui import QOpenGLTexture

from . import DDSDefinitions

class DDSReadException(Exception):
    """Thrown if there was an error reading a DDS file"""
    pass

ddsCubemapFaces = { DDSDefinitions.DDS_HEADER.Caps2.DDSCAPS2_CUBEMAP_POSITIVEX: QOpenGLTexture.CubeMapPositiveX,
                    DDSDefinitions.DDS_HEADER.Caps2.DDSCAPS2_CUBEMAP_NEGATIVEX: QOpenGLTexture.CubeMapNegativeX,
                    DDSDefinitions.DDS_HEADER.Caps2.DDSCAPS2_CUBEMAP_POSITIVEY: QOpenGLTexture.CubeMapPositiveY,
                    DDSDefinitions.DDS_HEADER.Caps2.DDSCAPS2_CUBEMAP_NEGATIVEY: QOpenGLTexture.CubeMapNegativeY,
                    DDSDefinitions.DDS_HEADER.Caps2.DDSCAPS2_CUBEMAP_POSITIVEZ: QOpenGLTexture.CubeMapPositiveZ,
                    DDSDefinitions.DDS_HEADER.Caps2.DDSCAPS2_CUBEMAP_NEGATIVEZ: QOpenGLTexture.CubeMapNegativeZ }

class DDSFile:
    def __init__(self, fileName):
        self.fileName = fileName
        self.header = DDSDefinitions.DDS_HEADER()
        self.dxt10Header = None
        self.glFormat = None
        self.data = None
        self.isCubemap = None
        
    def load(self):
        with Path(self.fileName).open('rb') as file:
            magicNumber = file.read(4)
            if magicNumber != DDSDefinitions.DDS_MAGIC_NUMBER:
                qCritical(self.__tr("Magic number mismatch."))
                raise DDSReadException()
            
            self.header.fromStream(file)
            
            if self.header.ddspf.dwFlags & DDSDefinitions.DDS_PIXELFORMAT.Flags.DDPF_FOURCC:
                fourCC = self.header.ddspf.dwFourCC
                if fourCC == b"DX10":
                    self.dxt10Header = DDSDefinitions.DDS_HEADER_DXT10()
                    self.dxt10Header.fromStream(file)
            else:
                fourCC = None
            
            self.glFormat = DDSDefinitions.getGLFormat(self.header.ddspf, self.dxt10Header)
            self.data = []
            # Do this once per layer/mip level whatever, (times one per scanline if uncompressed). Also, potentially recompute this based on the format and size in case writers lie.
            #self.data.append(file.read(self.header.dwPitchOrLinearSize))
            
            layerCount = 1
            if self.header.dwCaps2 & DDSDefinitions.DDS_HEADER.Caps2.DDSCAPS2_CUBEMAP:
                self.isCubemap = True
                layerCount = 0
                for face in ddsCubemapFaces:
                    if self.header.dwCaps2 & face:
                        layerCount += 1
            else:
                self.isCubemap = False
            
            for layer in range(layerCount):
                nextWidth = self.header.dwWidth
                nextHeight = self.header.dwHeight
                mipCount = self.mipLevels()
                for level in range(mipCount):
                    if self.header.ddspf.dwFlags & (DDSDefinitions.DDS_PIXELFORMAT.Flags.DDPF_ALPHA | DDSDefinitions.DDS_PIXELFORMAT.Flags.DDPF_RGB | DDSDefinitions.DDS_PIXELFORMAT.Flags.DDPF_YUV | DDSDefinitions.DDS_PIXELFORMAT.Flags.DDPF_LUMINANCE):
                        size = nextWidth * nextHeight * ((self.header.ddspf.dwRGBBitCount + 7) // 8)
                    elif fourCC:
                        if self.dxt10Header:
                            dxgiFormat = self.dxt10Header.dxgiFormat
                        else:
                            dxgiFormat = DDSDefinitions.fourCCToDXGI(fourCC)
                        size = DDSDefinitions.sizeFromFormat(dxgiFormat, nextWidth, nextHeight)
                    self.data.append(file.read(size))
                    nextWidth = max(nextWidth // 2, 1)
                    nextHeight = max(nextHeight // 2, 1)
                
    def getDescription(self):
        format = ""
        # DX10 header says the format enum
        if self.dxt10Header != None:
            format = self.dxt10Header.dxgiFormat.name.replace("DXGI_FORMAT_", "")
        # Pixel Format says the FourCC
        elif self.header.ddspf.dwFlags & DDSDefinitions.DDS_PIXELFORMAT.Flags.DDPF_FOURCC:
            fourCC = self.header.ddspf.dwFourCC
            format = self.__tr("{0} (equivalent to {1})").format(fourCC.decode('ascii'), DDSDefinitions.fourCCToDXGI(fourCC).name.replace("DXGI_FORMAT_", ""))
        # We've got bitmasks for the colour channels
        else:
            # This could be prettier if there was logic to detect that certain common bitmasks represented things more easily represented, like RGBA8
            if self.header.ddspf.dwFlags & (DDSDefinitions.DDS_PIXELFORMAT.Flags.DDPF_RGB | DDSDefinitions.DDS_PIXELFORMAT.Flags.DDPF_YUV):
                format += self.__tr("Red bitmask {0}, Green bitmask {1}, Blue bitmask {2}").format(self.header.ddspf.dwRBitMask.hex().upper(), self.header.ddspf.dwGBitMask.hex().upper(), self.header.ddspf.dwBBitMask.hex().upper())
            if self.header.ddspf.dwFlags & DDSDefinitions.DDS_PIXELFORMAT.Flags.DDPF_LUMINANCE:
                if format != "":
                    format += ", "
                format += self.__tr("Luminance bitmask {0}").format(self.header.ddspf.dwRBitMask.hex().upper())
            if self.header.ddspf.dwFlags & (DDSDefinitions.DDS_PIXELFORMAT.Flags.DDPF_ALPHA | DDSDefinitions.DDS_PIXELFORMAT.Flags.DDPF_ALPHAPIXELS):
                if format != "":
                    format += ", "
                format += self.__tr("Alpha bitmask {0}").format(self.header.ddspf.dwABitMask.hex().upper())
        
        size = self.__tr("{0}×{1}").format(self.header.dwWidth, self.header.dwHeight)
        
        dimensions = self.__tr("Cubemap") if self.isCubemap else self.__tr("2D")
        
        mipmaps = self.__tr("Mipmapped") if self.mipLevels() != 1 else self.__tr("No mipmaps")
        
        return self.__tr("{0}, {1} {2}, {3}").format(format, size, dimensions, mipmaps)
    
    def mipLevels(self):
        if self.header.dwFlags & DDSDefinitions.DDS_HEADER.Flags.DDSD_MIPMAPCOUNT:
            return self.header.dwMipMapCount
        else:
            return 1
    
    def asQOpenGLTexture(self, gl, context):
        if not self.data:
            return
        
        if self.glFormat.requirements:
            minVersion, extensions = self.glFormat.requirements
            glVersion = (gl.glGetIntegerv(gl.GL_MAJOR_VERSION), gl.glGetIntegerv(gl.GL_MINOR_VERSION))
            if glVersion < minVersion or minVersion < (1, 0):
                compatible = False
                for extension in extensions:
                    if context.hasExtension(extension):
                        compatible = True
                        break
                if not compatible:
                    qCritical(self.__tr("OpenGL driver incompatible with texture format."))
                    return None
        
        if self.header.dwCaps2 & DDSDefinitions.DDS_HEADER.Caps2.DDSCAPS2_CUBEMAP:
            texture = QOpenGLTexture(QOpenGLTexture.TargetCubeMap)
            if self.header.dwWidth != self.header.dwHeight:
                qCritical(self.__tr("Cubemap faces must be square"))
                return None
        else:
            # Assume GL_TEXTURE_2D for now
            texture = QOpenGLTexture(QOpenGLTexture.Target2D)
        # Assume single layer for now
        # self.texture.setLayers(1)
        mipCount = self.mipLevels()
        texture.setAutoMipMapGenerationEnabled(False)
        texture.setMipLevels(mipCount)
        texture.setMipLevelRange(0, mipCount - 1)
        texture.setSize(self.header.dwWidth, self.header.dwHeight)
        texture.setFormat(self.glFormat.internalFormat)
        texture.allocateStorage()
        
        if self.header.dwCaps2 & DDSDefinitions.DDS_HEADER.Caps2.DDSCAPS2_CUBEMAP:
            # Lisa hasn't whipped David Wang into shape yet. At least there are fewer bugs than under Raja.
            # The specific bug has been reported and AMD "will try to reproduce it soon"
            noDSA = "Radeon" in gl.glGetString(gl.GL_RENDERER) and self.glFormat.compressed
            if noDSA:
                texture.bind()
            faceIndex = 0
            for face in ddsCubemapFaces:
                if self.header.dwCaps2 & face:
                    for i in range(mipCount):
                        if self.glFormat.compressed:
                            if not noDSA:
                                texture.setCompressedData(i, 0, ddsCubemapFaces[face], len(self.data[faceIndex * mipCount + i]), self.data[faceIndex * mipCount + i])
                            else:
                                gl.glCompressedTexSubImage2D(ddsCubemapFaces[face], i, 0, 0, max(self.header.dwWidth // 2 ** i, 1), max(self.header.dwHeight // 2 ** i, 1), self.glFormat.internalFormat, len(self.data[faceIndex * mipCount + i]), self.data[faceIndex * mipCount + i])
                        else:
                            texture.setData(i, 0, ddsCubemapFaces[face], self.glFormat.format, self.glFormat.type, self.glFormat.converter(self.data[faceIndex * mipCount + i]))
                    faceIndex += 1
            if noDSA:
                texture.release()
        else:
            for i in range(mipCount):
                if self.glFormat.compressed:
                    texture.setCompressedData(i, 0, len(self.data[i]), self.data[i])
                else:
                    texture.setData(i, 0, self.glFormat.format, self.glFormat.type, self.glFormat.converter(self.data[i]))
        
        texture.setWrapMode(QOpenGLTexture.ClampToEdge)
        
        if self.glFormat.samplerType != "F":
            # integer textures can't be filtered
            texture.setMinMagFilters(QOpenGLTexture.NearestMipMapNearest, QOpenGLTexture.Nearest)
        
        return texture
    
    def __tr(self, str):
        return QCoreApplication.translate("DDSFile", str)