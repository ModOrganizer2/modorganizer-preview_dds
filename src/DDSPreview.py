import struct
import sys
import threading

from PyQt5.QtCore import QCoreApplication, qDebug, Qt
from PyQt5.QtGui import QColor, QOpenGLBuffer, QOpenGLContext, QOpenGLDebugLogger, QOpenGLShader, QOpenGLShaderProgram, QOpenGLTexture, QOpenGLVersionProfile, QOpenGLVertexArrayObject, QSurfaceFormat
from PyQt5.QtWidgets import QCheckBox, QDialog, QGridLayout, QLabel, QOpenGLWidget, QPushButton, QWidget

from DDS.DDSFile import DDSFile

if "mobase" not in sys.modules:
    import mock_mobase as mobase

vertexShader2D = """
#version 150

uniform float aspectRatioRatio;

in vec4 position;
in vec2 texCoordIn;

out vec2 texCoord;

void main()
{
    texCoord = texCoordIn;
    gl_Position = position;
    if (aspectRatioRatio >= 1.0)
        gl_Position.y /= aspectRatioRatio;
    else
        gl_Position.x *= aspectRatioRatio;
}
"""

vertexShaderCube = """
#version 150

uniform float aspectRatioRatio;

in vec4 position;
in vec2 texCoordIn;

out vec2 texCoord;

void main()
{
    texCoord = texCoordIn;
    gl_Position = position;
}
"""

fragmentShaderFloat = """
#version 150

uniform sampler2D aTexture;

in vec2 texCoord;

void main()
{
    gl_FragData[0] = texture(aTexture, texCoord);
}
"""

fragmentShaderUInt = """
#version 150

uniform usampler2D aTexture;

in vec2 texCoord;

void main()
{
    // autofilled alpha is 1, so if we have a scaling factor, we need separate ones for luminance and alpha
    gl_FragData[0] = texture(aTexture, texCoord);
}
"""

fragmentShaderSInt = """
#version 150

uniform isampler2D aTexture;

in vec2 texCoord;

void main()
{
    // autofilled alpha is 1, so if we have a scaling factor and offset, we need separate ones for luminance and alpha
    gl_FragData[0] = texture(aTexture, texCoord);
}
"""

fragmentShaderCube = """
#version 150

uniform samplerCube aTexture;

in vec2 texCoord;

const float PI = 3.1415926535897932384626433832795;

void main()
{
    float theta = -2.0 * PI * texCoord.x;
    float phi = PI * texCoord.y;
    gl_FragData[0] = texture(aTexture, vec3(sin(theta) * sin(phi), cos(theta) * sin(phi), cos(phi)));
}
"""

transparencyVS = """
#version 150

in vec4 position;

void main()
{
    gl_Position = position;
}
"""

transparencyFS = """
#version 150

uniform vec4 backgroundColour;

void main()
{
    float x = gl_FragCoord.x;
    float y = gl_FragCoord.y;
    x = mod(x, 16.0);
    y = mod(y, 16.0);
    gl_FragData[0] = x < 8.0 ^^ y < 8.0 ? vec4(vec3(191.0/255.0), 1.0) : vec4(1.0);
    gl_FragData[0].rgb = backgroundColour.rgb * backgroundColour.a + gl_FragData[0].rgb * (1.0 - backgroundColour.a);
}
"""

vertices = [
    # vertex coordinates        texture coordinates
    -1.0, -1.0, 0.5, 1.0,       0.0, 1.0,
    -1.0,  1.0, 0.5, 1.0,       0.0, 0.0,
     1.0,  1.0, 0.5, 1.0,       1.0, 0.0,
    
    -1.0, -1.0, 0.5, 1.0,       0.0, 1.0,
     1.0,  1.0, 0.5, 1.0,       1.0, 0.0,
     1.0, -1.0, 0.5, 1.0,       1.0, 1.0,
]



glVersionProfile = QOpenGLVersionProfile()
glVersionProfile.setVersion(2, 1)

class DDSWidget(QOpenGLWidget):
    def __init__(self, ddsFile, debugContext = False, parent = None, f = Qt.WindowFlags()):
        super(DDSWidget, self).__init__(parent, f)
        
        self.ddsFile = ddsFile
        
        self.clean = True
        
        self.logger = None
        
        self.program = None
        self.transparecyProgram = None
        self.texture = None
        self.vbo = None
        self.vao = None
        
        self.backgroundColour = None
        
        if debugContext:
            format = QSurfaceFormat()
            format.setOption(QSurfaceFormat.DebugContext)
            self.setFormat(format)
            self.logger = QOpenGLDebugLogger(self)
    
    def __del__(self):
        self.cleanup()
    
    def __dtor__(self):
        self.cleanup()
    
    def initializeGL(self):
        if self.logger:
            self.logger.initialize()
            self.logger.messageLogged.connect(lambda message: qDebug(self.__tr("OpenGL debug message: {0}").fomat(message.message())))
            self.logger.startLogging()
        
        gl = QOpenGLContext.currentContext().versionFunctions(glVersionProfile)
        QOpenGLContext.currentContext().aboutToBeDestroyed.connect(self.cleanup)
        
        self.clean = False
        
        fragmentShader = None
        vertexShader = vertexShader2D
        if self.ddsFile.isCubemap:
            fragmentShader = fragmentShaderCube
            vertexShader = vertexShaderCube
            if QOpenGLContext.currentContext().hasExtension(b"GL_ARB_seamless_cube_map"):
                GL_TEXTURE_CUBE_MAP_SEAMLESS = 0x884F
                gl.glEnable(GL_TEXTURE_CUBE_MAP_SEAMLESS)
        elif self.ddsFile.glFormat.samplerType == "F":
            fragmentShader = fragmentShaderFloat
        elif self.ddsFile.glFormat.samplerType == "UI":
            fragmentShader = fragmentShaderUInt
        else:
            fragmentShader = fragmentShaderSInt
        
        self.program = QOpenGLShaderProgram(self)
        self.program.addShaderFromSourceCode(QOpenGLShader.Vertex, vertexShader)
        self.program.addShaderFromSourceCode(QOpenGLShader.Fragment, fragmentShader)
        self.program.bindAttributeLocation("position", 0)
        self.program.bindAttributeLocation("texCoordIn", 1)
        self.program.link()
        
        self.transparecyProgram = QOpenGLShaderProgram(self)
        self.transparecyProgram.addShaderFromSourceCode(QOpenGLShader.Vertex, transparencyVS)
        self.transparecyProgram.addShaderFromSourceCode(QOpenGLShader.Fragment, transparencyFS)
        self.transparecyProgram.bindAttributeLocation("position", 0)
        self.transparecyProgram.link()
        
        self.vao = QOpenGLVertexArrayObject(self)
        vaoBinder = QOpenGLVertexArrayObject.Binder(self.vao)
        
        self.vbo = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
        self.vbo.create()
        self.vbo.bind()
        
        theBytes = struct.pack("%sf" % len(vertices), *vertices)
        self.vbo.allocate(theBytes, len(theBytes))
        
        gl.glEnableVertexAttribArray(0)
        gl.glEnableVertexAttribArray(1)
        gl.glVertexAttribPointer(0, 4, gl.GL_FLOAT, False, 6 * 4, 0)
        gl.glVertexAttribPointer(1, 2, gl.GL_FLOAT, False, 6 * 4, 4 * 4)
        
        self.texture = self.ddsFile.asQOpenGLTexture(gl, QOpenGLContext.currentContext())
    
    def resizeGL(self, w, h):
        aspectRatioTex = self.texture.width() / self.texture.height() if self.texture else 1.0
        aspectRatioWidget = w / h
        ratioRatio = aspectRatioTex / aspectRatioWidget
        
        self.program.bind()
        self.program.setUniformValue("aspectRatioRatio", ratioRatio)
        self.program.release()
    
    def paintGL(self):
        gl = QOpenGLContext.currentContext().versionFunctions(glVersionProfile)
        
        vaoBinder = QOpenGLVertexArrayObject.Binder(self.vao)
        
        # Draw checkerboard so transparency is obvious
        self.transparecyProgram.bind()
        
        if self.backgroundColour and self.backgroundColour.isValid():
            self.transparecyProgram.setUniformValue("backgroundColour", self.backgroundColour)
        
        gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)
        
        self.transparecyProgram.release()
        
        self.program.bind()
            
        if self.texture:
            self.texture.bind()
        
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        
        gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)
        
        if self.texture:
            self.texture.release()
        self.program.release()
    
    def cleanup(self):
        if not self.clean:
            self.makeCurrent()
            
            self.program = None
            self.transparecyProgram = None
            if self.texture:
                self.texture.destroy()
            self.texture = None
            self.vbo.destroy()
            self.vbo = None
            self.vao.destroy()
            self.vao = None
            
            self.doneCurrent()
            self.clean = True
    
    def setBackgroundColour(self, colour):
        self.backgroundColour = colour
    
    def getBackgroundColour(self):
        return self.backgroundColour
    
    def __tr(self, str):
        return QCoreApplication.translate("DDSWidget", str)


class DDSPreview(mobase.IPluginPreview):
    
    def __init__(self):
        super().__init__()
        self.__organizer = None

    def init(self, organizer):
        self.__organizer = organizer
        return True

    def name(self):
        return "DDS Preview Plugin"

    def author(self):
        return "AnyOldName3"

    def description(self):
        return self.__tr("Lets you preview DDS files by actually uploading them to the GPU.")

    def version(self):
        return mobase.VersionInfo(1, 0, 0, 0)

    def isActive(self):
        return True

    def settings(self):
        return [mobase.PluginSetting("log gl errors", self.__tr("If enabled, log OpenGL errors and debug messages. May decrease performance."), False),
                mobase.PluginSetting("background r", self.__tr("Red channel of background colour"), 0),
                mobase.PluginSetting("background g", self.__tr("Green channel of background colour"), 0),
                mobase.PluginSetting("background b", self.__tr("Blue channel of background colour"), 0),
                mobase.PluginSetting("background a", self.__tr("Alpha channel of background colour"), 0)]
    
    def supportedExtensions(self):
        return ["dds"]
    
    def genFilePreview(self, fileName, maxSize):
        ddsFile = DDSFile(fileName)
        ddsFile.load()
        layout = QGridLayout()
        # Image grows before label and button
        layout.setRowStretch(0, 1)
        # Label grows before button
        layout.setColumnStretch(0, 1)
        layout.addWidget(self.__makeLabel(ddsFile), 1, 0, 1, 1)
        
        ddsWidget = DDSWidget(ddsFile, self.__organizer.pluginSetting(self.name(), "log gl errors"))
        layout.addWidget(ddsWidget, 0, 0, 1, 2)
        
        layout.addWidget(self.__makeColourButton(ddsWidget), 1, 1, 1, 1)
        
        widget = QWidget()
        widget.setLayout(layout)
        return widget
    
    def __tr(self, str):
        return QCoreApplication.translate("DDSPreview", str)
    
    def __makeLabel(self, ddsFile):
        label = QLabel(ddsFile.getDescription())
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return label
    
    def __makeColourButton(self, ddsWidget):
        button = QPushButton(self.__tr("Pick background colour"))
        savedColour = QColor(self.__organizer.pluginSetting(self.name(), "background r"), self.__organizer.pluginSetting(self.name(), "background g"), self.__organizer.pluginSetting(self.name(), "background b"), self.__organizer.pluginSetting(self.name(), "background a"))
        ddsWidget.setBackgroundColour(savedColour)
        
        def pickColour(unused):
            newColour = QColorDialog.getColor(ddsWidget.getBackgroundColour(), button, "Background colour", QColorDialog.ShowAlphaChannel)
            if newColour.isValid():
                ddsWidget.setBackgroundColour(newColour)
                self.__organizer.setPluginSetting(self.name(), "background r", newColour.red())
                self.__organizer.setPluginSetting(self.name(), "background g", newColour.green())
                self.__organizer.setPluginSetting(self.name(), "background b", newColour.blue())
                self.__organizer.setPluginSetting(self.name(), "background a", newColour.alpha())
        
        button.clicked.connect(pickColour)
        return button
    
def createPlugin():
    return DDSPreview()