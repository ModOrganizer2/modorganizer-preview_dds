import struct
import sys
import threading

from PyQt6.QtCore import QCoreApplication, qDebug, Qt
from PyQt6.QtGui import QColor, QOpenGLContext, QSurfaceFormat, QWindow
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtWidgets import QCheckBox, QDialog, QGridLayout, QLabel, QPushButton, QWidget, QColorDialog
from PyQt6.QtOpenGL import QOpenGLBuffer, QOpenGLDebugLogger, QOpenGLShader, QOpenGLShaderProgram, QOpenGLTexture, \
    QOpenGLVersionProfile, QOpenGLVertexArrayObject, QOpenGLFunctions_4_1_Core, QOpenGLVersionFunctionsFactory

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
    -1.0, -1.0, 0.5, 1.0, 0.0, 1.0,
    -1.0, 1.0, 0.5, 1.0, 0.0, 0.0,
    1.0, 1.0, 0.5, 1.0, 1.0, 0.0,

    -1.0, -1.0, 0.5, 1.0, 0.0, 1.0,
    1.0, 1.0, 0.5, 1.0, 1.0, 0.0,
    1.0, -1.0, 0.5, 1.0, 1.0, 1.0,
]

glVersionProfile = QOpenGLVersionProfile()
glVersionProfile.setVersion(2, 1)


class DDSWidget(QOpenGLWidget):
    def __init__(self, ddsPreview, ddsFile, debugContext=False, parent=None, flags=Qt.WindowType(0)):
        super(DDSWidget, self).__init__(parent, flags=flags)

        self.ddsPreview = ddsPreview
        self.ddsFile = ddsFile

        self.clean = True

        self.logger = None

        self.program = None
        self.transparecyProgram = None
        self.texture = None
        self.vbo = None
        self.vao = None


        if debugContext:
            format = QSurfaceFormat()
            format.setOption(QSurfaceFormat.FormatOption.DebugContext)
            self.setFormat(format)
            self.logger = QOpenGLDebugLogger(self)

    def __del__(self):
        self.cleanup()

    def __dtor__(self):
        self.cleanup()

    def initializeGL(self):
        if self.logger:
            self.logger.initialize()
            self.logger.messageLogged.connect(
                lambda message: qDebug(self.tr("OpenGL debug message: {0}").fomat(message.message())))
            self.logger.startLogging()

        gl = QOpenGLVersionFunctionsFactory.get(glVersionProfile)
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
        self.program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, vertexShader)
        self.program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, fragmentShader)
        self.program.bindAttributeLocation("position", 0)
        self.program.bindAttributeLocation("texCoordIn", 1)
        self.program.link()

        self.transparecyProgram = QOpenGLShaderProgram(self)
        self.transparecyProgram.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, transparencyVS)
        self.transparecyProgram.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, transparencyFS)
        self.transparecyProgram.bindAttributeLocation("position", 0)
        self.transparecyProgram.link()

        self.vao = QOpenGLVertexArrayObject(self)
        vaoBinder = QOpenGLVertexArrayObject.Binder(self.vao)

        self.vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
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
        gl = QOpenGLVersionFunctionsFactory.get(glVersionProfile)

        vaoBinder = QOpenGLVertexArrayObject.Binder(self.vao)

        # Draw checkerboard so transparency is obvious
        self.transparecyProgram.bind()

        backgroundColour = self.ddsPreview.getBackgroundColour()
        if backgroundColour and backgroundColour.isValid():
            self.transparecyProgram.setUniformValue("backgroundColour", backgroundColour)

        gl.glDrawArrays(gl.GL_TRIANGLES, 0, 6)

        self.transparecyProgram.release()

        self.program.bind()

        if self.texture:
            self.texture.bind()

        if self.ddsPreview.getTransparency():
            gl.glEnable(gl.GL_BLEND)
            gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        else:
            gl.glDisable(gl.GL_BLEND)

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

    def tr(self, str):
        return QCoreApplication.translate("DDSWidget", str)


class DDSPreview(mobase.IPluginPreview):

    def __init__(self):
        super().__init__()
        self.__organizer = None

    def init(self, organizer):
        self.__organizer = organizer
        return True

    def pluginSetting(self, name):
        return self.__organizer.pluginSetting(self.name(), name)

    def setPluginSetting(self, name, value):
        self.__organizer.setPluginSetting(self.name(), name, value)

    def name(self):
        return "DDS Preview Plugin"

    def author(self):
        return "AnyOldName3"

    def description(self):
        return self.tr("Lets you preview DDS files by actually uploading them to the GPU.")

    def version(self):
        return mobase.VersionInfo(1, 0, 0, 0)

    def settings(self):
        return [mobase.PluginSetting("log gl errors", self.tr(
            "If enabled, log OpenGL errors and debug messages. May decrease performance."), False),
                mobase.PluginSetting("background r", self.tr("Red channel of background colour"), 0),
                mobase.PluginSetting("background g", self.tr("Green channel of background colour"), 0),
                mobase.PluginSetting("background b", self.tr("Blue channel of background colour"), 0),
                mobase.PluginSetting("background a", self.tr("Alpha channel of background colour"), 0),
                mobase.PluginSetting("transparency", self.tr("If enabled, transparency will be displayed."), True)]

    def supportedExtensions(self):
        return {"dds"}

    def genFilePreview(self, fileName, maxSize):
        ddsFile = DDSFile(fileName)
        ddsFile.load()
        layout = QGridLayout()
        # Image grows before label and button
        layout.setRowStretch(0, 1)
        # Label grows before button
        layout.setColumnStretch(0, 1)
        layout.addWidget(self.__makeLabel(ddsFile), 1, 0, 1, 1)

        ddsWidget = DDSWidget(self, ddsFile, self.__organizer.pluginSetting(self.name(), "log gl errors"))
        layout.addWidget(ddsWidget, 0, 0, 1, 3)

        layout.addWidget(self.__makeColourButton(ddsWidget), 1, 2, 1, 1)
        layout.addWidget(self.__makeToggleTransparencyButton(ddsWidget), 1, 1, 1, 1)

        widget = QWidget()
        widget.setLayout(layout)
        return widget

    def tr(self, str):
        return QCoreApplication.translate("DDSPreview", str)

    def __makeLabel(self, ddsFile):
        label = QLabel(ddsFile.getDescription())
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def __makeColourButton(self, ddsWidget):
        button = QPushButton(self.tr("Pick background colour"))

        def pickColour(unused):
            newColour = QColorDialog.getColor(self.getBackgroundColour(), button, "Background colour", QColorDialog.ColorDialogOption.ShowAlphaChannel)
            if newColour.isValid():
                self.setPluginSetting("background r", newColour.red())
                self.setPluginSetting("background g", newColour.green())
                self.setPluginSetting("background b", newColour.blue())
                self.setPluginSetting("background a", newColour.alpha())
                ddsWidget.update()

        button.clicked.connect(pickColour)
        return button

    def __makeToggleTransparencyButton(self, ddsWidget):
        checkbox = QCheckBox("Disable Transparency")
        checkbox.setChecked(not self.getTransparency())
        checkbox.showEvent = lambda _: checkbox.setChecked(not self.getTransparency())
        checkbox.setToolTip(self.tr("Some games use the alpha channel for other purposes such as specularity, so viewing textures with transparency "
                                    "enabled makes them appear different than in the game."))

        def toggleTransparency(unused):
            transparency = not checkbox.isChecked()
            self.setPluginSetting("transparency", transparency)
            ddsWidget.update()

        checkbox.stateChanged.connect(toggleTransparency)
        return checkbox

    def getBackgroundColour(self):
        return QColor(self.pluginSetting("background r"), self.pluginSetting("background g"), self.pluginSetting("background b"),
                      self.pluginSetting("background a"))

    def getTransparency(self):
        return self.pluginSetting("transparency")


def createPlugin():
    return DDSPreview()